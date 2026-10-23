"""System Dynamics analysis + simulation — pure functions, no file I/O, no commits.

:func:`analyse` is the single source of truth for whether an SD model is
well-formed. It returns typed problems; each readiness validator in
``operations/readiness.py`` reports one category of them, and
:func:`build_model` refuses to compile while any remain. Integration is
delegated to ``_sd_engine`` (the scipy chokepoint) and equation evaluation to
``_sd_eval`` (the simpleeval chokepoint).

Units flow through as pint quantities: every stock, constant and equation
result carries its declared unit, so ``stock units = flow units × time`` and
every other dimensional rule is enforced by ordinary arithmetic rather than by
special-case checks.
"""

from __future__ import annotations

import contextlib
import math
from dataclasses import dataclass, field
from typing import Any

from latris.operations import _sd_engine
from latris.operations._sd_eval import (
    TIME,
    EquationError,
    Evaluator,
    ParsedEquation,
    parse,
    slugify,
)
from latris.operations._units import Quantity, UnitError, describe, is_compatible, parse_unit
from latris.schema import Substrate
from latris.schema.roles import RoleSet
from latris.schema.sd import SDConstantSet, SDEquationSet, SDStockSet, SDTableEntry, SDTableSet
from latris.schema.settings import SDSettings

ROLES: tuple[str, ...] = ("stock", "flow", "auxiliary", "constant", "source_sink")
_COMPUTED = ("flow", "auxiliary")  # roles with an equation
_NAMED = ("stock", "flow", "auxiliary", "constant")  # roles an equation can reference
_MAX_LOOPS_REPORTED = 20

# Problem categories — one per readiness validator.
CLASSIFICATION_GAPS = frozenset({"unclassified", "no_stocks"})
FLOW_GAPS = frozenset({"flow_not_connected", "flow_edge_invalid", "flow_ambiguous", "stock_causal_input"})
LOOP_GAPS = frozenset({"algebraic_loop"})
EQUATION_GAPS = frozenset({
    "missing_equation", "equation_invalid", "unknown_reference", "self_reference",
    "name_collision", "missing_information_link", "unused_information_link",
})
VALUE_GAPS = frozenset({"missing_initial_value", "missing_constant_value"})
TABLE_GAPS = frozenset({"missing_table", "unused_table"})
UNIT_GAPS = frozenset({
    "units_invalid", "flow_units_incompatible", "units_mismatch", "evaluation_error", "settings_invalid",
})


@dataclass(frozen=True)
class SDProblem:
    target_id: str
    gap_type: str
    message: str


@dataclass(frozen=True)
class _Link:
    id: str
    from_id: str
    to_id: str


class _UnitsMismatch(EquationError):
    pass


@dataclass
class SDModel:
    """A compiled, validated SD model ready to evaluate."""

    settings: SDSettings
    time_unit: Any
    labels: dict[str, str]
    roles: dict[str, str]
    slugs: dict[str, str]
    stocks: list[str]
    stock_units: dict[str, Any]
    initial: dict[str, float]
    non_negative: set[str]
    constants: dict[str, Any]
    order: list[str]
    equations: dict[str, ParsedEquation]
    eq_units: dict[str, Any]
    unit_text: dict[str, str]  # units as the modeller declared them, for display
    tables: dict[str, SDTableEntry]
    inflows: dict[str, list[str]]
    outflows: dict[str, list[str]]
    evaluator: Evaluator = field(default_factory=Evaluator)


@dataclass(frozen=True)
class SDSimulationResult:
    times: list[float]
    series: dict[str, list[float]]  # variable id → magnitudes in its declared unit
    units: dict[str, str]
    roles: dict[str, str]
    labels: dict[str, str]
    time_units: str
    method: str
    algorithm: str
    library_version: str
    success: bool
    message: str
    settings: dict[str, Any]
    warnings: list[str] = field(default_factory=list)


# ── analysis ─────────────────────────────────────────────────────────


def role_map(roles: RoleSet) -> dict[str, str]:
    return {e.target_id: e.value for e in roles.entries if e.value in ROLES}


def _settings_problems(settings: SDSettings) -> list[SDProblem]:
    out = []
    if settings.final_time <= settings.initial_time:
        out.append(SDProblem("", "settings_invalid", "final time must be after initial time"))
    if settings.dt <= 0:
        out.append(SDProblem("", "settings_invalid", "dt must be positive"))
    elif settings.dt > settings.final_time - settings.initial_time > 0:
        out.append(SDProblem("", "settings_invalid", "dt is longer than the whole simulation"))
    if settings.saveper is not None and settings.saveper <= 0:
        out.append(SDProblem("", "settings_invalid", "the reporting interval must be positive"))
    try:
        unit = parse_unit(settings.time_units)
        if not is_compatible(unit, parse_unit("second")):
            out.append(SDProblem("", "settings_invalid", f"time units {settings.time_units!r} are not a time"))
    except UnitError as exc:
        out.append(SDProblem("", "settings_invalid", f"time units: {exc}"))
    return out


def analyse(
    substrate: Substrate,
    roles: RoleSet,
    equations: SDEquationSet,
    stocks: SDStockSet,
    constants: SDConstantSet,
    tables: SDTableSet,
    settings: SDSettings | None = None,
    *,
    entity_ids: list[str] | None = None,
    edge_ids: list[str] | None = None,
) -> tuple[SDModel | None, list[SDProblem]]:
    """Check an SD model end to end; return the compiled model (if sound) and every problem."""
    settings = settings or SDSettings()
    labels = {e.id: e.label for e in substrate.entities}
    in_view = set(entity_ids) if entity_ids is not None else set(labels)
    edge_view = set(edge_ids) if edge_ids is not None else {e.id for e in substrate.edges}
    edges = [e for e in substrate.edges if e.id in edge_view and e.from_id in in_view and e.to_id in in_view]
    flow_edges = [e for e in edges if e.kind == "flow"]
    edge_label = {e.id: f"{labels.get(e.from_id, e.from_id)} → {labels.get(e.to_id, e.to_id)}" for e in edges}

    # Model boundary. The SD model is whatever has an SD role, plus anything a
    # flow edge touches (flow edges are SD-only). Causal edges count only when
    # they point INTO the model — those are its information links. A causal
    # edge leaving the model, or one between two non-SD entities (say, the rest
    # of a CLD on the same substrate), is outside the SD view and ignored.
    roles_of = {k: v for k, v in role_map(roles).items() if k in in_view}
    members = set(roles_of) | {n for e in flow_edges for n in (e.from_id, e.to_id)}
    causal = [e for e in edges if e.kind == "causal" and e.to_id in members]
    nodes = members | {e.from_id for e in causal}
    problems: list[SDProblem] = []

    def name(i: str) -> str:
        return labels.get(i, i)

    def add(target: str, gap: str, msg: str) -> None:
        problems.append(SDProblem(target, gap, msg))

    # 1. classification
    for n in sorted(nodes, key=name):
        if n not in roles_of:
            add(n, "unclassified",
                "Not classified for System Dynamics. Set its role: stock, flow, auxiliary, constant, or source_sink.")
    if "stock" not in roles_of.values():
        add("", "no_stocks", "The SD model has no stocks yet. Classify at least one with `sd set-role <node> stock`.")

    # 2. stock-and-flow plumbing
    inflows: dict[str, list[str]] = {}
    outflows: dict[str, list[str]] = {}
    upstream: dict[str, list[str]] = {}
    downstream: dict[str, list[str]] = {}
    ends = ("stock", "source_sink")
    for e in flow_edges:
        ra, rb = roles_of.get(e.from_id), roles_of.get(e.to_id)
        if ra is None or rb is None:
            continue  # classification gap already reported
        if ra in ends and rb == "flow":
            upstream.setdefault(e.to_id, []).append(e.from_id)
            if ra == "stock":
                outflows.setdefault(e.from_id, []).append(e.to_id)
        elif ra == "flow" and rb in ends:
            downstream.setdefault(e.from_id, []).append(e.to_id)
            if rb == "stock":
                inflows.setdefault(e.to_id, []).append(e.from_id)
        else:
            add(e.id, "flow_edge_invalid",
                f"Flow edge {edge_label[e.id]} must run between a stock (or source/sink cloud) and a flow "
                f"({ra} → {rb}). Use a causal edge for information links.")
    for n in sorted((n for n, r in roles_of.items() if r == "flow"), key=name):
        ups, downs = upstream.get(n, []), downstream.get(n, [])
        if not any(roles_of.get(s) == "stock" for s in ups + downs):
            add(n, "flow_not_connected",
                "Flow does not fill or drain any stock. Connect it with flow edges (stock → flow → stock).")
        if len(ups) > 1 or len(downs) > 1:
            add(n, "flow_ambiguous",
                "A flow moves material from at most one place to at most one place; split it into separate flows.")
    for e in causal:
        if roles_of.get(e.to_id) == "stock":
            add(e.id, "stock_causal_input",
                f"Stocks change only through flows; {edge_label[e.id]} points an information link at a stock. "
                f"Route the influence through a flow's equation instead.")

    # 3. names
    named = {n: r for n, r in roles_of.items() if r in _NAMED}
    slugs = {n: slugify(name(n)) for n in named}
    by_slug: dict[str, list[str]] = {}
    for n, s in slugs.items():
        by_slug.setdefault(s, []).append(n)
    for s, ids in by_slug.items():
        if len(ids) > 1:
            for i in ids:
                add(i, "name_collision",
                    f"Equation name '{s}' is shared by {', '.join(name(x) for x in ids)}; rename one of them.")
    resolve = {s: ids[0] for s, ids in by_slug.items() if len(ids) == 1}

    # 4. equations, references, information links
    computed = sorted((n for n, r in roles_of.items() if r in _COMPUTED), key=name)
    eq_entries = {e.target_id: e for e in equations.entries}
    parsed: dict[str, ParsedEquation] = {}
    refs: dict[str, set[str]] = {}
    linked = {(e.from_id, e.to_id) for e in causal} | {
        pair for e in flow_edges for pair in ((e.from_id, e.to_id), (e.to_id, e.from_id))
    }
    for v in computed:
        entry = eq_entries.get(v)
        if entry is None:
            add(v, "missing_equation", f"{roles_of[v].capitalize()} has no equation. Set one with `sd set-equation`.")
            continue
        try:
            p = parse(entry.expression)
        except EquationError as exc:
            add(v, "equation_invalid", str(exc))
            continue
        parsed[v] = p
        deps: set[str] = set()
        for ref in sorted(p.names):
            target = resolve.get(ref)
            if target is None:
                known = ", ".join(sorted(resolve)) or "(none)"
                add(v, "unknown_reference", f"Equation refers to '{ref}', which is not an SD variable. Known: {known}.")
                continue
            if target == v:
                add(v, "self_reference", "Equation refers to itself; only stocks may accumulate their own history.")
                continue
            deps.add(target)
            if (target, v) not in linked:
                add(v, "missing_information_link",
                    f"Equation uses {name(target)} but the diagram has no link {name(target)} → {name(v)}. "
                    f"Add a causal edge so the diagram shows the dependency.")
        refs[v] = deps
    for e in causal:
        v = e.to_id
        if v in parsed and roles_of.get(e.from_id) in _NAMED and e.from_id not in refs.get(v, set()):
            add(e.id, "unused_information_link",
                f"The diagram claims {edge_label[e.id]}, but {name(v)}'s equation doesn't use {name(e.from_id)}.")

    # 5. tables
    table_map = {t.target_id: t for t in tables.entries}
    for v, p in parsed.items():
        if p.uses_table and v not in table_map:
            add(v, "missing_table", "Equation calls TABLE() but no table is defined. Add one with `sd set-table`.")
    for t in table_map:
        if t in in_view and (t not in parsed or not parsed[t].uses_table):
            add(t, "unused_table", "A table is defined but this variable's equation never calls TABLE().")

    # 6. values
    stock_entries = {s.target_id: s for s in stocks.entries}
    const_entries = {c.target_id: c for c in constants.entries}
    for n in sorted(named, key=name):
        if named[n] == "stock" and n not in stock_entries:
            add(n, "missing_initial_value", "Stock has no initial value. Set one with `sd set-initial-value`.")
        if named[n] == "constant" and n not in const_entries:
            add(n, "missing_constant_value", "Constant has no value. Set one with `sd set-constant`.")

    # 7. algebraic loops among instantaneous variables
    from latris.operations.graph_analysis import find_all_loops, topological_sort

    computed_set = set(computed)
    dep_links = [_Link(f"{d}>{v}", d, v) for v, ds in refs.items() for d in ds if d in computed_set]
    dep_links += [
        _Link(e.id, e.from_id, e.to_id) for e in causal if e.from_id in computed_set and e.to_id in computed_set
    ]
    try:
        topological_sort(dep_links)
    except ValueError:
        for loop in find_all_loops(dep_links)[:_MAX_LOOPS_REPORTED]:
            path = " → ".join(name(n) for n in (*loop.node_ids, loop.node_ids[0]))
            add(loop.node_ids[0], "algebraic_loop",
                f"Algebraic loop among instantaneous variables: {path}. Break it with a stock "
                f"(e.g. a perception or smoothing delay).")

    # 8. units + settings
    problems.extend(_settings_problems(settings))
    time_unit = None
    with contextlib.suppress(UnitError):  # reported by _settings_problems above
        time_unit = parse_unit(settings.time_units)

    def unit_of(target: str, spec: str, what: str) -> Any:
        try:
            return parse_unit(spec)
        except UnitError as exc:
            add(target, "units_invalid", f"{what}: {exc}")
            return None

    stock_units = {n: unit_of(n, stock_entries[n].units, "initial value units")
                   for n in named if named[n] == "stock" and n in stock_entries}
    const_q = {}
    for n in named:
        if named[n] == "constant" and n in const_entries:
            u = unit_of(n, const_entries[n].units, "constant units")
            if u is not None:
                const_q[n] = Quantity(const_entries[n].value, u)
    eq_units = {v: unit_of(v, eq_entries[v].units, "equation units") for v in parsed}
    for t, entry in table_map.items():
        unit_of(t, entry.x_units, "table input units")
        unit_of(t, entry.y_units, "table output units")
    if time_unit is not None:
        for s in sorted(set(inflows) | set(outflows), key=name):
            su = stock_units.get(s)
            if su is None:
                continue
            needed = su / time_unit
            for f in inflows.get(s, []) + outflows.get(s, []):
                fu = eq_units.get(f)
                if fu is not None and not is_compatible(fu, needed):
                    stock_text = stock_entries[s].units
                    add(f, "flow_units_incompatible",
                        f"Flow {name(f)} is in {eq_entries[f].units}, but it moves material in or out of stock "
                        f"{name(s)} ({stock_text}), so it must be in stock units per time unit, "
                        f"e.g. ({stock_text})/{describe(time_unit)}.")

    if problems:
        return None, problems

    # 9. compile + trial evaluation at the initial time
    order = sorted((v for v in computed if not any(v in (lk.from_id, lk.to_id) for lk in dep_links)), key=name)
    order += [v for v in topological_sort(dep_links) if v not in order]
    stock_ids = sorted((n for n in named if named[n] == "stock"), key=name)
    model = SDModel(
        settings=settings,
        time_unit=time_unit,
        labels={n: name(n) for n in named},
        roles=named,
        slugs=slugs,
        stocks=stock_ids,
        stock_units=stock_units,
        initial={s: stock_entries[s].initial_value for s in stock_ids},
        non_negative={s for s in stock_ids if stock_entries[s].non_negative},
        constants=const_q,
        order=order,
        equations=parsed,
        eq_units=eq_units,
        unit_text={**{s: stock_entries[s].units for s in stock_ids}, **{v: eq_entries[v].units for v in parsed}},
        tables={t: e for t, e in table_map.items() if t in parsed},
        inflows=inflows,
        outflows=outflows,
    )
    problems.extend(_trial(model))
    return (None, problems) if problems else (model, [])


def _base_names(model: SDModel, t: float, y: list[float]) -> dict[str, Any]:
    names: dict[str, Any] = {TIME: Quantity(t, model.time_unit)}
    for i, s in enumerate(model.stocks):
        names[model.slugs[s]] = Quantity(y[i], model.stock_units[s])
    for c, q in model.constants.items():
        names[model.slugs[c]] = q
    return names


def _coerce(model: SDModel, v: str, value: Any) -> Any:
    unit = model.eq_units[v]
    if isinstance(value, bool):
        raise EquationError(
            f"equation for {model.labels[v]} yields true/false; wrap the condition in IF_THEN_ELSE", target_id=v
        )
    if isinstance(value, int | float):
        return Quantity(float(value), unit)  # a bare-number equation takes its declared units
    try:
        return value.to(unit)
    except Exception as exc:
        raise _UnitsMismatch(
            f"equation for {model.labels[v]} yields {describe(value.units)} but its declared units are "
            f"{model.unit_text[v]}",
            target_id=v,
        ) from exc


def _evaluate(model: SDModel, v: str, names: dict[str, Any]) -> Any:
    try:
        raw = model.evaluator.evaluate(model.equations[v], names, table=model.tables.get(v))
    except EquationError as exc:
        raise EquationError(f"{model.labels[v]}: {exc}", target_id=v) from exc
    return _coerce(model, v, raw)


def _trial(model: SDModel) -> list[SDProblem]:
    """Evaluate every equation once at the initial time, reporting each failure."""
    y0 = [model.initial[s] for s in model.stocks]
    names = _base_names(model, model.settings.initial_time, y0)
    failed: set[str] = set()
    out: list[SDProblem] = []
    for v in model.order:
        if any(d in failed for d in _deps(model, v)):
            failed.add(v)
            continue
        try:
            names[model.slugs[v]] = _evaluate(model, v, names)
        except _UnitsMismatch as exc:
            failed.add(v)
            out.append(SDProblem(v, "units_mismatch", str(exc)))
        except EquationError as exc:
            failed.add(v)
            out.append(SDProblem(v, "evaluation_error", str(exc)))
    return out


def _deps(model: SDModel, v: str) -> list[str]:
    by_slug = {s: i for i, s in model.slugs.items()}
    return [by_slug[n] for n in model.equations[v].names if n in by_slug and by_slug[n] in model.equations]


def build_model(*args: Any, **kwargs: Any) -> SDModel:
    """:func:`analyse`, raising if the model isn't ready to simulate."""
    model, problems = analyse(*args, **kwargs)
    if model is None:
        shown = "; ".join(p.message.rstrip(".") for p in problems[:3])
        more = f" (+{len(problems) - 3} more)" if len(problems) > 3 else ""
        raise EquationError(f"SD model is not ready to simulate: {shown}{more}. Run `sd check` for the full list.")
    return model


# ── evaluation + simulation ──────────────────────────────────────────


def evaluate_step(model: SDModel, t: float, y: list[float]) -> dict[str, Any]:
    """One dependency-ordered pass: every flow and auxiliary at time ``t`` given stock values ``y``."""
    names = _base_names(model, t, y)
    out: dict[str, Any] = {}
    for v in model.order:
        value = _evaluate(model, v, names)
        names[model.slugs[v]] = value
        out[v] = value
    return out


def derivatives(model: SDModel, t: float, y: list[float]) -> list[float]:
    """dS/dt for every stock, in each stock's units per time unit."""
    values = evaluate_step(model, t, y)
    out = []
    for s in model.stocks:
        rate_unit = model.stock_units[s] / model.time_unit
        net = Quantity(0.0, rate_unit)
        for f in model.inflows.get(s, []):
            net = net + values[f]
        for f in model.outflows.get(s, []):
            net = net - values[f]
        out.append(float(net.to(rate_unit).magnitude))
    return out


def simulate(model: SDModel) -> SDSimulationResult:
    """Integrate the model over its settings' horizon; report stocks, flows and auxiliaries."""
    st = model.settings
    interval = st.saveper or st.dt

    def rhs(t: float, y: list[float]) -> list[float]:
        try:
            return derivatives(model, t, y)
        except EquationError as exc:
            raise EquationError(f"at {TIME}={t:.6g} {st.time_units}: {exc}", target_id=exc.target_id) from exc

    y0 = [model.initial[s] for s in model.stocks]
    engine = _sd_engine.integrate(
        rhs, y0, st.initial_time, st.final_time, method=st.integration_method, dt=st.dt, interval=interval
    )

    series: dict[str, list[float]] = {s: [] for s in model.stocks}
    series.update({v: [] for v in model.order})
    for t, y in zip(engine.times, engine.states, strict=True):
        for s, val in zip(model.stocks, y, strict=True):
            series[s].append(val)
        for v, q in evaluate_step(model, t, y).items():
            series[v].append(float(q.magnitude))

    success, message = engine.success, engine.message
    if any(not math.isfinite(x) for vals in series.values() for x in vals):
        success, message = False, "simulation produced non-finite values (overflow or instability); try a smaller dt"

    warnings = []
    for s in sorted(model.non_negative, key=lambda i: model.labels[i]):
        low = min(series[s]) if series[s] else 0.0
        if low < -1e-9:
            warnings.append(
                f"Stock {model.labels[s]} went negative (min {low:.6g} {model.unit_text[s]}) "
                f"although it is marked non-negative; limit its outflows."
            )

    units = {i: model.unit_text[i] for i in (*model.stocks, *model.order)}
    return SDSimulationResult(
        times=engine.times,
        series=series,
        units=units,
        roles={i: model.roles[i] for i in series},
        labels={i: model.labels[i] for i in series},
        time_units=st.time_units,
        method=st.integration_method,
        algorithm=engine.algorithm,
        library_version=engine.library_version,
        success=success,
        message=message,
        settings=st.model_dump(mode="json"),
        warnings=warnings,
    )
