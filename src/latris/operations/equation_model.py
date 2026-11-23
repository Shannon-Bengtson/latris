"""Equation model — sourced formulas with units and no clock: what do they give for these inputs?

A model built from a physical law, an engineering relationship or a published parameterisation
(``docs/engineering/EQUATION_MODEL.md``). Quantities are substrate factors with an ``equation_model``
role: an ``input`` or ``parameter`` has a value, a ``computed`` quantity or ``output`` a formula over the
others. Formulas run in the same sandbox as system-dynamics equations (``operations/_sd_eval.py``), with
values bound to ``pint`` quantities, so adding metres to seconds is an error, not a number.

Three analyses:

- :func:`evaluate` — every quantity at the model's own (reference) values and under each saved scenario;
- :func:`sweep` — how an output responds as one input moves across a range, the others held;
- :func:`monte_carlo` — the spread of the outputs given the ranges on inputs and parameters, and which
  of them drive it (Spearman rank correlation; Latin hypercube sampling by default).

A value can state the range it is valid over (the range its source covered). Every analysis reports
values outside it; nothing is clamped, so an extrapolation is shown as one.

:func:`compute` is the kernel and is pure: a loaded :class:`Model` and a set of values in, every
quantity's value out, nothing read or written. Running a pinned version of a model on inputs a pipeline
supplies (the roadmap's *predict*) wraps it.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from latris.operations import _sampling as smp
from latris.operations import uncertainty as unc
from latris.operations._sd_eval import ALGEBRAIC_FUNCTIONS, EquationError, Evaluator, ParsedEquation, parse, slugify
from latris.operations._units import Quantity, UnitError, is_compatible, parse_unit, with_units
from latris.operations._units import describe as describe_unit
from latris.operations._units import display as display_units
from latris.operations._view_store import ViewStore, replace_entry, resolve_factor
from latris.operations.commit import auto_commit
from latris.operations.equation_model_scenarios import chain
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_model, load_model
from latris.schema import Edge, Substrate, new_id
from latris.schema.attributes import ParameterUncertainty
from latris.schema.common import ProvenanceOrigin, ProvenanceVerification, default_origin
from latris.schema.equation_model import (
    EQUATION_ROLES,
    FORMULA_ROLES,
    VALUE_ROLES,
    EquationFormulaEntry,
    EquationFormulaSet,
    EquationOverride,
    EquationScenario,
    EquationScenarioSet,
    EquationValueEntry,
    EquationValueSet,
)

MODEL_TYPE = "equation_model"
CELL = f"{MODEL_TYPE}:value"
REFERENCE = "Reference"
MAX_RUNS = 100_000
MAX_STEPS = 500
_UNSET: Any = object()
_ASSIGN = re.compile(r"^\s*(?P<target>[^=]+?)\s*=\s*(?P<value>[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?)\s*(?P<units>.*)$")

_store = ViewStore(MODEL_TYPE, EQUATION_ROLES)


# ── reads ────────────────────────────────────────────────────────────


def get_roles(*, root: Path | None = None) -> dict[str, str]:
    return _store.roles(root)


def get_values(*, root: Path | None = None) -> EquationValueSet:
    return _store.load(root, "value", EquationValueSet)


def get_formulas(*, root: Path | None = None) -> EquationFormulaSet:
    return _store.load(root, "formula", EquationFormulaSet)


def get_scenarios(*, root: Path | None = None) -> EquationScenarioSet:
    return _store.load(root, "scenarios", EquationScenarioSet)


# ── writes ───────────────────────────────────────────────────────────


def _factor(paths, target: str) -> tuple[str, str]:
    return resolve_factor(paths, target, link_error=f"{target!r} is a link; an equation model's quantities are factors")


def _an(role: str) -> str:
    name = "computed quantity" if role == "computed" else role
    return f"an {name}" if name[0] in "aeiou" else f"a {name}"


def _require_role(paths, tid: str, label: str, allowed: tuple[str, ...], what: str) -> str:
    role = get_roles(root=paths.root).get(tid)
    if role not in allowed:
        have = f"is {_an(role)}" if role else "has no role in the equation model yet"
        raise ValueError(f"{label} {have}; {what} belongs to {' or '.join(_an(r) for r in allowed)}")
    return role


def _assign_role(paths, tid: str, role: str) -> None:
    """Give the factor ``role`` unless it has it already (one commit, or part of the caller's batch)."""
    from latris.operations.view_roles import assign_role

    if get_roles(root=paths.root).get(tid) != role:
        assign_role(tid, MODEL_TYPE, role, root=paths.root)


def ensure_role(target: str, role: str, *, root: Path | None = None) -> None:
    """Give a factor ``role`` if it doesn't have it yet (so a formula can read a quantity defined after it)."""
    paths = require_project(root)
    _assign_role(paths, _factor(paths, target)[0], role)


def set_role(target: str, role: str, *, root: Path | None = None) -> tuple[str, str]:
    """Make a factor an input, a parameter, a computed quantity or an output."""
    from latris.operations.view_roles import assign_role

    if role not in EQUATION_ROLES:
        raise ValueError(f"{role!r} is not an equation-model role. Roles: {', '.join(EQUATION_ROLES)}")
    return assign_role(target, MODEL_TYPE, role, root=root)


def remove(target: str, *, root: Path | None = None) -> tuple[str, int, str]:
    """Take a factor out of the equation model: its role, value or formula and range go; the factor, its
    links and citations stay. Returns ``(factor id, rows removed, commit sha)``."""
    from latris.operations._cascade import cascade_model_type

    paths = require_project(root)
    tid, label = _factor(paths, target)
    if tid not in get_roles(root=paths.root):
        raise ValueError(f"{label} is not in the equation model")
    changed, removed = cascade_model_type(paths, MODEL_TYPE, [tid])
    sha = auto_commit(paths.root, subject=f"Equation model: take {label} out",
                      body=f"target: {tid}\nrows removed: {removed}", paths=changed)
    return tid, removed, sha


def set_value(
    target: str,
    value: float,
    units: str,
    *,
    role: str | None = None,
    valid_min: float | None = None,
    valid_max: float | None = None,
    notes: str | None = None,
    origin: ProvenanceOrigin = "human-direct",
    source_id: str | None = None,
    verification: ProvenanceVerification = "unverified",
    root: Path | None = None,
) -> tuple[EquationValueEntry, str]:
    """Set an input's or a parameter's value, in its units, with the range it is valid over.

    ``role`` (``input`` or ``parameter``) also gives the factor that role; without it the factor must
    already have one of them.
    """
    paths = require_project(root)
    tid, label = _factor(paths, target)
    if role is not None and role not in VALUE_ROLES:
        raise ValueError(f"a value belongs to an input or a parameter, not {_an(role)}")
    if not math.isfinite(value):
        raise ValueError("the value must be a finite number")
    try:
        parse_unit(units)
    except UnitError as exc:
        raise ValueError(str(exc)) from exc
    if role is None:
        _require_role(paths, tid, label, VALUE_ROLES, "a value")
    entry = EquationValueEntry(target_id=tid, value=value, units=units.strip(), valid_min=valid_min,
                               valid_max=valid_max, notes=notes, origin=origin, source_id=source_id,
                               verification=verification)
    store = get_values(root=paths.root)
    previous = next((e for e in store.entries if e.target_id == tid), None)
    ranges, converted = _carry_range(paths, tid, label, previous, entry)
    if role is not None:
        _assign_role(paths, tid, role)
    replace_entry(store, entry)
    path = _store.path(paths, "value")
    dump_model(store, path)
    touched = [path]
    if ranges is not None:
        dump_model(ranges, paths.parameter_uncertainty_yaml)
        touched.append(paths.parameter_uncertainty_yaml)
    span = "" if valid_min is None and valid_max is None else f"\nvalid range: {valid_min} to {valid_max}"
    sha = auto_commit(paths.root, subject=f"Set equation-model value {label} = {value:g} {entry.units}",
                      body=f"target: {tid}\nvalue: {value}\nunits: {entry.units}{span}\norigin: {origin}\n"
                           f"source_id: {source_id}" + (f"\nuncertainty range converted from {previous.units} to "
                                                        f"{entry.units}" if converted and previous else ""),
                      paths=touched)
    return entry, sha


def _convert(value: float, have: str, want: str) -> float:
    """``value`` in ``have`` units, expressed in ``want`` units; ``ValueError`` if they don't convert."""
    try:
        return float(Quantity(float(value), parse_unit(have)).to(parse_unit(want)).magnitude)
    except UnitError:
        raise
    except Exception as exc:  # pint: a different dimension, or units with an offset
        raise ValueError(f"{have} can't be converted to {want}") from exc


# The parameters of a distribution that are in the value's units (the others are shapes).
_UNIT_PARAMS = ("min", "mode", "max", "mean", "sd", "scale")


def _carry_range(paths, tid: str, label: str, previous: EquationValueEntry | None, entry: EquationValueEntry):
    """What a change of units means for what was said in the old ones.

    A scenario's value carries its own units, so it survives any compatible change; an uncertainty range is
    in the value's units, so it is converted with them. A change to units of another kind (metres to
    seconds) leaves both meaningless, and is refused until they are removed.

    Returns ``(the uncertainty store to save, or None; whether a range was converted)``.
    """
    if previous is None or previous.units == entry.units:
        return None, False
    try:
        old, new = parse_unit(previous.units), parse_unit(entry.units)
    except UnitError:
        return None, False  # the old units were never valid: nothing to carry
    if old == new:
        return None, False
    store = unc.load(paths)
    mine = [e for e in store.entries if e.target_id == tid and e.parameter_cell_id == CELL]
    scenarios = [s.name for s in get_scenarios(root=paths.root).scenarios
                 if any(o.target_id == tid and not _fits(o.units, new) for o in s.overrides)]
    if not is_compatible(old, new):
        blockers = ([f"scenario {', '.join(repr(n) for n in scenarios)} "
                     f"(`latris eq scenario <name> --remove`, or save it again without {label})"] if scenarios else [])
        blockers += [f"its uncertainty range (`latris eq uncertainty \"{label}\" --clear`)"] if mine else []
        if blockers:
            raise ValueError(f"{label} is in {previous.units}; {entry.units} is a different kind of quantity, so what "
                             f"was said about it in {previous.units} would no longer mean anything. Remove first: "
                             + "; ".join(blockers))
        return None, False
    if not mine:
        return None, False
    try:
        factor = _convert(1.0, previous.units, entry.units)
        linear = abs(_convert(0.0, previous.units, entry.units)) < 1e-12 and factor > 0
    except ValueError:
        linear = False
    if not linear:
        raise ValueError(f"{label}'s uncertainty range is in {previous.units} and can't be carried over to "
                         f"{entry.units}; clear it first (`latris eq uncertainty \"{label}\" --clear`) and set it "
                         "again")
    for e in mine:
        e.params = {k: (v * factor if k in _UNIT_PARAMS else v) for k, v in e.params.items()}
    return store, True


def _fits(units: str, unit) -> bool:  # noqa: ANN001
    try:
        return is_compatible(parse_unit(units), unit)
    except UnitError:
        return False


def _names(paths, substrate: Substrate) -> dict[str, list[str]]:
    """Formula name → the quantities (factor ids) with that slugified label."""
    roles = get_roles(root=paths.root)
    out: dict[str, list[str]] = {}
    for e in substrate.entities:
        if e.id in roles:
            out.setdefault(slugify(e.label), []).append(e.id)
    return out


def formula_reads(expression: str, *, root: Path | None = None) -> dict[str, str]:
    """The names a formula reads, each with the factor it resolves to ({"slope": "Slope"}); a name no
    factor has maps to itself, so a typo shows."""
    paths = require_project(root)
    labels = [e.label for e in load_model(Substrate, paths.conceptual_yaml).entities]
    by_name = {slugify(label): label for label in labels}
    return {n: by_name.get(n, n) for n in sorted(_parse(expression).names)}


def _parse(expression: str) -> ParsedEquation:
    return parse(expression, functions=ALGEBRAIC_FUNCTIONS, clock=False)


def set_formula(
    target: str,
    expression: str,
    units: str,
    *,
    role: str | None = None,
    notes: str | None = None,
    origin: ProvenanceOrigin = "human-direct",
    source_id: str | None = None,
    verification: ProvenanceVerification = "unverified",
    link: bool = True,
    root: Path | None = None,
) -> tuple[EquationFormulaEntry, str]:
    """Set the formula of a computed quantity or an output, with the units it gives.

    Quantities are referenced by slugified label (``Hydraulic radius`` → ``hydraulic_radius``) and must
    already be in the model. ``role`` (``computed`` or ``output``) also gives the factor that role. With
    ``link`` (the default) any link the formula needs and the map lacks is added in the same commit, so
    the diagram shows what the formula reads.
    """
    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    tid, label = _factor(paths, target)
    if role is not None and role not in FORMULA_ROLES:
        raise ValueError(f"a formula belongs to a computed quantity or an output, not {_an(role)}")
    try:
        parsed = _parse(expression)
        parse_unit(units)
    except (EquationError, UnitError) as exc:
        raise ValueError(str(exc)) from exc
    if role is None:
        _require_role(paths, tid, label, FORMULA_ROLES, "a formula")
    known = _names(paths, substrate)
    unknown = sorted(n for n in parsed.names if n not in known)
    if unknown:
        raise ValueError(
            f"the formula refers to {', '.join(repr(n) for n in unknown)}, which "
            f"{'is' if len(unknown) == 1 else 'are'} not in the equation model. "
            f"Known: {', '.join(sorted(known)) or '(none yet: add inputs and parameters first)'}")
    if slugify(label) in parsed.names:
        raise ValueError(f"the formula for {label} refers to itself")
    entry = EquationFormulaEntry(target_id=tid, expression=parsed.expression, units=units.strip(), notes=notes,
                                 origin=origin, source_id=source_id, verification=verification)
    touched: list[Path] = []
    added: list[Edge] = []
    if link:
        have = {(e.from_id, e.to_id) for e in substrate.edges if e.kind == "causal"}
        need = sorted({i for n in parsed.names for i in known[n]} - {tid})
        added = [Edge(id=new_id("edge"), from_id=i, to_id=tid, kind="causal", origin=default_origin())
                 for i in need if (i, tid) not in have]
        if added:
            substrate.edges.extend(added)
            dump_model(substrate, paths.conceptual_yaml)
            touched.append(paths.conceptual_yaml)
    if role is not None:
        _assign_role(paths, tid, role)
    store = get_formulas(root=paths.root)
    replace_entry(store, entry)
    path = _store.path(paths, "formula")
    dump_model(store, path)
    sha = auto_commit(
        paths.root, subject=f"Set equation-model formula {label} = {parsed.expression} [{entry.units}]",
        body=f"target: {tid}\nexpression: {parsed.expression}\nunits: {entry.units}\norigin: {origin}\n"
             f"source_id: {source_id}" + (f"\nlinks added: {len(added)}" if added else ""),
        paths=[path, *touched])
    return entry, sha


# ── structure ────────────────────────────────────────────────────────


@dataclass
class EquationProblem:
    target_id: str | None
    gap_type: str
    message: str


@dataclass
class Model:
    """A loaded equation model: what :func:`compute` runs on."""

    labels: dict[str, str]
    roles: dict[str, str]
    slugs: dict[str, str]  # quantity id → the name formulas use for it
    values: dict[str, EquationValueEntry]
    formulas: dict[str, EquationFormulaEntry]
    parsed: dict[str, ParsedEquation]
    reads: dict[str, list[str]]  # computed quantity → the quantities its formula reads
    order: list[str]  # the computed quantities, each after everything it reads
    outputs: list[str]
    problems: list[EquationProblem] = field(default_factory=list)

    def quantity_units(self, i: str) -> str:
        return self.values[i].units if i in self.values else self.formulas[i].units


def _by_label(ids, labels: dict[str, str]) -> list[str]:
    return sorted(ids, key=lambda i: (labels[i].casefold(), i))


def load(*, root: Path | None = None, check_units: bool = True) -> Model:
    """Load the model and list what is wrong with it; a model with no problems can be computed."""
    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    labels = {e.id: e.label for e in substrate.entities}
    roles = {k: v for k, v in get_roles(root=paths.root).items() if k in labels}
    values = {e.target_id: e for e in get_values(root=paths.root).entries if roles.get(e.target_id) in VALUE_ROLES}
    formulas = {e.target_id: e for e in get_formulas(root=paths.root).entries
                if roles.get(e.target_id) in FORMULA_ROLES}
    slugs = {i: slugify(labels[i]) for i in roles}
    m = Model(labels=labels, roles=roles, slugs=slugs, values=values, formulas=formulas, parsed={}, reads={},
              order=[], outputs=_by_label((i for i, r in roles.items() if r == "output"), labels))
    add = m.problems.append
    if not m.outputs:
        add(EquationProblem(None, "eq_no_output", "No output: say which quantity the model is for "
                                                  "(`latris eq formula <factor> \"<formula>\" <units> --output`)."))
    by_name: dict[str, list[str]] = {}
    for i, s in slugs.items():
        by_name.setdefault(s, []).append(i)
    for s, ids in sorted(by_name.items()):
        if len(ids) > 1:
            for i in ids:
                add(EquationProblem(i, "eq_name_collision", f"The formula name '{s}' is shared by "
                                    f"{', '.join(labels[x] for x in _by_label(ids, labels))}; rename one."))
    resolve = {s: ids[0] for s, ids in by_name.items() if len(ids) == 1}
    for i in _by_label(roles, labels):
        if roles[i] in VALUE_ROLES and i not in values:
            add(EquationProblem(i, "eq_no_value", f"No value (`latris eq {roles[i]} <factor> <value> <units>`)."))
        if roles[i] in FORMULA_ROLES and i not in formulas:
            add(EquationProblem(i, "eq_no_formula", "No formula (`latris eq formula <factor> \"<formula>\" <units>`)."))
    causal = [e for e in substrate.edges if e.kind == "causal" and e.from_id in roles and e.to_id in roles]
    linked = {(e.from_id, e.to_id) for e in causal}
    for i in _by_label(formulas, labels):
        try:
            p = _parse(formulas[i].expression)
            parse_unit(formulas[i].units)
        except (EquationError, UnitError) as exc:
            add(EquationProblem(i, "eq_formula_invalid", str(exc)))
            continue
        deps: list[str] = []
        ok = True
        for name in sorted(p.names):
            ref = resolve.get(name)
            if ref is None or ref == i:
                ok = False
                if name not in by_name:
                    add(EquationProblem(i, "eq_unknown_reference", f"The formula refers to '{name}', which is not "
                                        f"in the equation model. Known: {', '.join(sorted(resolve)) or '(none)'}."))
                elif ref == i:
                    add(EquationProblem(i, "eq_unknown_reference", "The formula refers to itself."))
                continue
            deps.append(ref)
            if (ref, i) not in linked:
                add(EquationProblem(i, "eq_missing_link", f"The formula uses {labels[ref]} but the map has no link "
                                    f"{labels[ref]} → {labels[i]}; set the formula again to add it."))
        if ok:
            m.parsed[i] = p
            m.reads[i] = deps
    for e in causal:
        if e.to_id in m.reads and e.from_id not in m.reads[e.to_id]:
            add(EquationProblem(e.id, "eq_unused_link", f"The map says {labels[e.from_id]} → {labels[e.to_id]}, but "
                                f"{labels[e.to_id]}'s formula doesn't use {labels[e.from_id]}."))
        elif roles[e.to_id] in VALUE_ROLES:
            add(EquationProblem(e.id, "eq_unused_link", f"{labels[e.to_id]} is {_an(roles[e.to_id])}: it is given, "
                                f"not computed, so the link from {labels[e.from_id]} means nothing here."))
    m.order = _order(m)
    # A formula left out of the order is waiting on something upstream that has its own problem (no value, no
    # formula); only one that reads itself through other formulas is circular.
    for i in _by_label((i for i in set(m.reads) - set(m.order) if _reads_itself(m, i)), labels):
        add(EquationProblem(i, "eq_circular", "Its formula depends on itself through other formulas; simultaneous "
                                              "equations aren't solved here."))
    from latris.operations.membership import shares_map

    if not shares_map(paths, MODEL_TYPE):  # on a shared map, a link to a loop-map factor is the loop map's
        strays: dict[str, set[str]] = {}
        for e in substrate.edges:
            if e.kind == "causal" and (e.from_id in roles) != (e.to_id in roles):
                inside, outside = (e.from_id, e.to_id) if e.from_id in roles else (e.to_id, e.from_id)
                if outside in labels:
                    strays.setdefault(outside, set()).add(inside)
        for i in _by_label(strays, labels):
            near = ", ".join(labels[x] for x in _by_label(strays[i], labels))
            add(EquationProblem(i, "eq_unclassified", f"Linked to {near} "
                                "but has no role in the equation model: make it an input, a parameter, a computed "
                                "quantity or an output, or remove the link."))
    _check_scenarios_and_ranges(paths, m)
    # The units are checked as soon as every formula can be evaluated: a model with no output yet, or a
    # link out of step with a formula, still computes.
    if check_units and not {p.gap_type for p in m.problems} - _COMPUTABLE_WITH:
        m.problems += _trial(m)
    return m


_COMPUTABLE_WITH = frozenset({"eq_no_output", "eq_missing_link", "eq_unused_link", "eq_unclassified",
                              "eq_scenario_invalid", "eq_range_invalid"})


def _reads_itself(m: Model, start: str) -> bool:
    """Does ``start``'s formula read ``start`` again, through any chain of formulas?"""
    seen: set[str] = set()
    stack = list(m.reads.get(start, []))
    while stack:
        i = stack.pop()
        if i == start:
            return True
        if i not in seen:
            seen.add(i)
            stack.extend(m.reads.get(i, []))
    return False


def _check_scenarios_and_ranges(paths, m: Model) -> None:
    """A saved scenario or an uncertainty range that no longer fits the value it is about (its units were
    changed by hand, the quantity lost its value): reported here, so no analysis meets it as a raw error."""
    add = m.problems.append
    for s in get_scenarios(root=paths.root).scenarios:
        for o in s.overrides:
            name = m.labels.get(o.target_id, o.target_id)
            entry = m.values.get(o.target_id)
            if entry is None:
                add(EquationProblem(o.target_id if o.target_id in m.labels else None, "eq_scenario_invalid",
                                    f"Scenario '{s.name}' changes {name}, which has no value in the model any more; "
                                    f"save the scenario again without it, or remove it "
                                    f"(`latris eq scenario \"{s.name}\" --remove`)."))
                continue
            try:
                fits = is_compatible(parse_unit(o.units), parse_unit(entry.units))
            except UnitError:
                continue  # the value's own units are reported by the units check
            if not fits:
                add(EquationProblem(o.target_id, "eq_scenario_invalid",
                                    f"Scenario '{s.name}' gives {name} in {o.units}, but it is in {entry.units} now; "
                                    f"save the scenario again with a value in {entry.units}."))
    for i, r in sorted(specs(paths).items()):
        entry = m.values.get(i)
        if entry is None:
            continue
        try:
            sampler = smp.Sampler(r)
            lo, hi = sampler.quantile(0.001), sampler.quantile(0.999)
        except (ValueError, KeyError, RuntimeError, ZeroDivisionError):
            continue
        if not lo <= entry.value <= hi:
            add(EquationProblem(i, "eq_range_invalid",
                                f"Its value {entry.value:g} {display_units(entry.units)} lies outside its uncertainty "
                                f"range ({lo:.3g} to {hi:.3g}, read in the same units); set the range again "
                                f"(`latris eq uncertainty`) or clear it (`--clear`)."))


def _order(m: Model) -> list[str]:
    """The computed quantities whose formulas (and everything they read) can be evaluated, in order."""
    done: list[str] = []
    ready = {i for i in m.roles if i in m.values}
    pending = _by_label(m.reads, m.labels)
    moved = True
    while moved:
        moved = False
        for i in list(pending):
            if all(d in ready for d in m.reads[i]):
                done.append(i)
                ready.add(i)
                pending.remove(i)
                moved = True
    return done


def _trial(m: Model) -> list[EquationProblem]:
    """Evaluate every formula once at the reference values, reporting each that fails."""
    for i, v in m.values.items():
        try:
            parse_unit(v.units)
        except UnitError as exc:
            return [EquationProblem(i, "eq_units", str(exc))]
    try:
        compute(m)
    except EquationError as exc:
        return [EquationProblem(exc.target_id, "eq_units", str(exc))]
    return []


def structure_problems(*, root: Path | None = None) -> list[EquationProblem]:
    return load(root=root).problems


def snapshot(*, root: Path | None = None) -> dict[str, Any]:
    """The whole model as a surface shows it: every quantity with its role, value (computed, once the model
    is complete) or formula, units (and ``units_display``, as a reader sees them: ``m³/s``), valid range and
    provenance; the saved scenarios; the ranges; the problems."""
    paths = require_project(root)
    m = load(root=paths.root)
    values = compute(m) if not m.problems else {i: v.value for i, v in m.values.items()}
    ranges = specs(paths)
    rows = []
    for role in EQUATION_ROLES:
        for i in _by_label((k for k in m.roles if m.roles[k] == role), m.labels):
            e = m.values.get(i) or m.formulas.get(i)
            r = ranges.get(i)
            rows.append({
                "id": i, "quantity": m.labels[i], "name": m.slugs[i], "role": role, "value": values.get(i),
                "units": e.units if e else None, "units_display": display_units(e.units) if e else "",
                "formula": m.formulas[i].expression if i in m.formulas else None,
                "reads": [m.labels[d] for d in m.reads.get(i, [])],
                "valid_min": getattr(e, "valid_min", None), "valid_max": getattr(e, "valid_max", None),
                "notes": e.notes if e else None, "source": e.source_id if e else None,
                "origin": e.origin if e else None, "verification": e.verification if e else None,
                "uncertainty": ({"distribution": r.distribution, "params": r.params, "reason": r.reason}
                                if r else None),
            })
    return {
        "quantities": rows,
        "scenarios": [{"name": s.name, "description": s.description, "reason": s.reason, "source": s.source_id,
                       "changes": [{"quantity": m.labels.get(o.target_id, o.target_id), "value": o.value,
                                    "units": o.units, "units_display": display_units(o.units)}
                                   for o in s.overrides]}
                      for s in get_scenarios(root=paths.root).scenarios],
        "problems": [{"id": p.target_id, "label": m.labels.get(p.target_id or "", "(model)"),
                      "gap_type": p.gap_type, "message": p.message} for p in m.problems],
    }


# ── the kernel ───────────────────────────────────────────────────────


def compute(m: Model, values: dict[str, float] | None = None) -> dict[str, float]:
    """Every quantity's value, by factor id, in its declared units. ``values`` replaces inputs' or
    parameters' own values (by factor id, in their declared units). Pure: reads and writes nothing.

    Raises :class:`EquationError` (with ``target_id``) if a formula can't be evaluated or gives the
    wrong units.
    """
    given = values or {}
    names: dict[str, Any] = {}
    out: dict[str, float] = {}
    for i, v in m.values.items():
        out[i] = float(given.get(i, v.value))
        names[m.slugs[i]] = Quantity(out[i], parse_unit(v.units))
    evaluator = Evaluator()
    for i in m.order:
        f = m.formulas[i]
        try:
            raw = evaluator.evaluate(m.parsed[i], names)
        except EquationError as exc:
            raise EquationError(f"{m.labels[i]}: {exc}", target_id=i) from exc
        if isinstance(raw, bool):
            raise EquationError(f"the formula for {m.labels[i]} gives true/false; wrap the condition in "
                                "IF_THEN_ELSE", target_id=i)
        unit = parse_unit(f.units)
        if isinstance(raw, int | float):
            q = Quantity(float(raw), unit)  # a bare-number formula takes its declared units
        else:
            try:
                q = raw.to(unit)
            except Exception as exc:
                raise EquationError(f"the formula for {m.labels[i]} gives {describe_unit(raw.units)} but its declared "
                                    f"units are {f.units}", target_id=i) from exc
        if isinstance(q.magnitude, complex):
            raise EquationError(f"the formula for {m.labels[i]} can't be evaluated at these values: it doesn't "
                                "give a real number", target_id=i)
        value = float(q.magnitude)
        if not math.isfinite(value):
            raise EquationError(f"the formula for {m.labels[i]} doesn't give a finite number", target_id=i)
        names[m.slugs[i]] = q
        out[i] = value
    return out


def outside_range(m: Model, values: dict[str, float]) -> list[dict[str, Any]]:
    """The inputs and parameters whose value (as computed with) is outside its stated valid range."""
    return [{"quantity": m.labels[i], "value": values[i], "units": v.units, "valid_min": v.valid_min,
             "valid_max": v.valid_max}
            for i, v in sorted(m.values.items(), key=lambda t: m.labels[t[0]].casefold()) if v.outside(values[i])]


def _ready(root: Path | None) -> Model:
    m = load(root=root)
    if m.problems:
        first = m.problems[0]
        raise ValueError(f"the equation model is incomplete ({len(m.problems)} problem(s), e.g. "
                         f"{m.labels.get(first.target_id or '', 'the model')}: {first.message}); "
                         "`latris eq check` lists them")
    return m


# ── scenarios ────────────────────────────────────────────────────────


def parse_assignment(text: str, paths) -> EquationOverride:
    """``"Slope=0.002"`` or ``"Depth = 250 cm"`` → a checked override (without units: the declared ones)."""
    match = _ASSIGN.match(text or "")
    if not match:
        raise ValueError(f"expected 'Quantity=value [units]', got {text!r}")
    tid, label = _factor(paths, match["target"])
    _require_role(paths, tid, label, VALUE_ROLES, "a scenario value")
    current = next((e for e in get_values(root=paths.root).entries if e.target_id == tid), None)
    if current is None:
        raise ValueError(f"{label} has no value yet, so a scenario has nothing to change; set it first")
    units = match["units"].strip() or current.units
    try:
        if not is_compatible(parse_unit(units), parse_unit(current.units)):
            raise ValueError(f"{label} is in {current.units}; a value in {units} can't replace it")
    except UnitError as exc:
        raise ValueError(f"{label}: {exc}") from exc
    return EquationOverride(target_id=tid, value=float(match["value"]), units=units)


def _overrides(m: Model, overrides: list[EquationOverride]) -> dict[str, float]:
    """Scenario overrides as values in each quantity's declared units."""
    out: dict[str, float] = {}
    for o in overrides:
        if o.target_id not in m.values:
            raise ValueError(f"a scenario changes {m.labels.get(o.target_id, o.target_id)}, which has no value in "
                             "the model any more")
        entry = m.values[o.target_id]
        try:
            out[o.target_id] = _convert(o.value, o.units, entry.units)
        except ValueError as exc:
            raise ValueError(f"a scenario gives {m.labels[o.target_id]} in {o.units}, but it is in {entry.units}: "
                             "save the scenario again in its units") from exc
    return out


def set_scenario(
    name: str,
    assignments: list[str],
    *,
    description: str = "",
    reason: str = "",
    origin: ProvenanceOrigin = "human-direct",
    source_id: str | None = None,
    verification: ProvenanceVerification = "unverified",
    root: Path | None = None,
) -> tuple[EquationScenario, str]:
    """Save a named set of input values (replacing a scenario of the same name)."""
    paths = require_project(root)
    if not assignments:
        raise ValueError("a scenario changes at least one value: give 'Quantity=value [units]'")
    overrides = [parse_assignment(a, paths) for a in assignments]
    if len({o.target_id for o in overrides}) != len(overrides):
        raise ValueError("a scenario gives each quantity one value")
    scenario = EquationScenario(name=name, description=description, overrides=overrides, reason=reason,
                                origin=origin, source_id=source_id, verification=verification)
    store = get_scenarios(root=paths.root)
    store.scenarios = [s for s in store.scenarios if s.name.casefold() != scenario.name.casefold()] + [scenario]
    sha = _store.save(paths, "scenarios", store, subject=f"Set equation-model scenario {scenario.name}",
                      body="\n".join(assignments) + f"\norigin: {origin}\nsource_id: {source_id}\nreason: {reason}")
    return scenario, sha


def remove_scenario(name: str, *, root: Path | None = None) -> str:
    paths = require_project(root)
    store = get_scenarios(root=paths.root)
    found = chain(name, store.scenarios)[0]
    store.scenarios = [s for s in store.scenarios if s is not found]
    return _store.save(paths, "scenarios", store, subject=f"Remove equation-model scenario {found.name}")


# ── uncertainty ──────────────────────────────────────────────────────


def specs(paths) -> dict[str, ParameterUncertainty]:
    """The ranges on this model's values, by factor id."""
    return {e.target_id: e for e in unc.load(paths).entries
            if e.parameter_cell_id == CELL and e.distribution != "unknown"}


def set_uncertainty(
    target: str,
    distribution: str,
    params: dict[str, float],
    *,
    reason: str = "",
    source_id: str | None = None,
    origin: ProvenanceOrigin = "human-direct",
    verification: ProvenanceVerification = "unverified",
    root: Path | None = None,
) -> tuple[ParameterUncertainty, str]:
    """Give an input or parameter a distribution over its value, in its units (replacing any earlier one)."""
    paths = require_project(root)
    tid, label = _factor(paths, target)
    _require_role(paths, tid, label, VALUE_ROLES, "an uncertainty range")
    current = next((e for e in get_values(root=paths.root).entries if e.target_id == tid), None)
    if current is None:
        raise ValueError(f"{label} has no value yet; set it before describing its uncertainty")
    entry = ParameterUncertainty(target_id=tid, distribution=distribution, params=params,  # type: ignore[arg-type]
                                 parameter_cell_id=CELL, reason=reason, source_id=source_id, origin=origin,
                                 verification=verification)
    sampler = smp.Sampler(entry)
    lo, hi = sampler.quantile(0.001), sampler.quantile(0.999)
    if not lo <= current.value <= hi:
        raise ValueError(f"{label}'s value {current.value:g} lies outside this distribution (99.8% of it is "
                         f"between {lo:.3g} and {hi:.3g})")
    store = unc.load(paths)
    store.entries = [e for e in store.entries if not (e.target_id == tid and e.parameter_cell_id == CELL)] + [entry]
    dump_model(store, paths.parameter_uncertainty_yaml)
    pretty = ", ".join(f"{k}={v:.4g}" for k, v in entry.params.items())
    sha = auto_commit(paths.root, subject=f"Set uncertainty on {label}: {distribution}({pretty})",
                      body=f"target: {tid}\ncell: {CELL}\norigin: {origin}\nsource_id: {source_id}\n"
                           f"reason: {reason}", paths=[paths.parameter_uncertainty_yaml])
    return entry, sha


def clear_uncertainty(target: str, *, root: Path | None = None) -> str:
    paths = require_project(root)
    tid, label = _factor(paths, target)
    store = unc.load(paths)
    kept = [e for e in store.entries if not (e.target_id == tid and e.parameter_cell_id == CELL)]
    if len(kept) == len(store.entries):
        raise ValueError(f"{label} has no uncertainty range to clear")
    store.entries = kept
    dump_model(store, paths.parameter_uncertainty_yaml)
    return auto_commit(paths.root, subject=f"Clear uncertainty on {label}", paths=[paths.parameter_uncertainty_yaml])


# ── analysis: evaluate ───────────────────────────────────────────────


def _problem_rows(m: Model) -> list[dict[str, Any]]:
    return [{"label": m.labels.get(p.target_id or "", "(model)"), "gap_type": p.gap_type, "message": p.message}
            for p in m.problems]


def _quantity_rows(m: Model) -> list[dict[str, Any]]:
    """Every quantity as the report lists it: inputs, parameters, then formulas in the order they run."""
    rows = []
    ordered = ([i for r in VALUE_ROLES for i in _by_label((k for k in m.values if m.roles[k] == r), m.labels)]
               + [i for i in m.order if m.roles[i] == "computed"] + [i for i in m.order if m.roles[i] == "output"])
    for i in ordered:
        e = m.values.get(i) or m.formulas[i]
        rows.append({
            "quantity": m.labels[i], "name": m.slugs[i], "role": m.roles[i], "units": e.units,
            "formula": m.formulas[i].expression if i in m.formulas else None,
            "reads": [m.labels[d] for d in m.reads.get(i, [])],
            "valid_min": getattr(e, "valid_min", None), "valid_max": getattr(e, "valid_max", None),
            "notes": e.notes, "source": e.source_id, "origin": e.origin, "weak": e.is_weak,
        })
    return rows


def _arm(m: Model, name: str, description: str, overrides: list[EquationOverride]) -> dict[str, Any]:
    changed = _overrides(m, overrides)
    try:
        values = compute(m, changed)
    except EquationError as exc:
        raise ValueError(f"under {name}: {exc}") from exc
    return {"name": name, "description": description,
            "changes": [{"quantity": m.labels[i], "value": v, "units": m.values[i].units,
                         "from": m.values[i].value} for i, v in changed.items()],
            "values": {m.labels[i]: v for i, v in values.items()},
            "outside": outside_range(m, values)}


def evaluate(*, scenarios: list[str] | None = None, set: list[str] | None = None,  # noqa: A002 (the spec's name)
             root: Path | None = None) -> dict[str, Any]:
    """Every quantity at the reference values and under each scenario.

    ``scenarios`` names saved scenarios (default: all of them); ``set`` is an unsaved one to try, as
    'Quantity=value [units]' assignments.
    """
    paths = require_project(root)
    m = load(root=paths.root)
    payload: dict[str, Any] = {"problems": _problem_rows(m), "outputs": [m.labels[i] for i in m.outputs]}
    if m.problems:
        return payload
    saved = get_scenarios(root=paths.root).scenarios
    chosen = saved if scenarios is None else [chain(n, saved)[0] for n in scenarios]
    arms = [_arm(m, REFERENCE, "The model's own values.", [])]
    arms += [_arm(m, s.name, s.description, s.overrides) for s in chosen]
    if set:
        arms.append(_arm(m, "What-if", "Unsaved values tried in this run.", [parse_assignment(a, paths) for a in set]))
    payload.update(
        quantities=_quantity_rows(m), arms=arms, scenarios=[s.name for s in chosen], set=list(set or []),
        units={m.labels[i]: m.quantity_units(i) for i in m.roles if i in m.values or i in m.formulas},
        unverified=sorted(q["quantity"] for q in _quantity_rows(m) if q["weak"]),
        unsourced=sorted(q["quantity"] for q in _quantity_rows(m) if not q["source"]),
    )
    return payload


def _num(x: float | None) -> str:
    return "—" if x is None else f"{x:,.4g}"


def fmt(x: float | None, units: str) -> str:
    """A value with its units as a reader sees them (``8.22 m³/s``)."""
    return with_units(_num(x), units)


def describe(p: dict[str, Any]) -> str:
    if p["problems"]:
        return f"The equation model is incomplete ({len(p['problems'])} structure problem(s))"
    ref = p["arms"][0]
    units = p["units"]
    parts = ["; ".join(f"{o} = {fmt(ref['values'][o], units[o])}" for o in p["outputs"]) + " at the reference values"]
    if p["outputs"]:
        first = p["outputs"][0]
        parts += [f"{fmt(a['values'][first], units[first])} under {a['name']}" for a in p["arms"][1:4]]
    outside = sorted({o["quantity"] for a in p["arms"] for o in a["outside"]})
    if outside:
        parts.append(f"{len(outside)} value(s) outside their valid range ({', '.join(outside)})")
    return "; ".join(parts)


def record(payload: dict[str, Any], *, root: Path | None = None) -> tuple[str, str]:
    from latris.operations.analysis_results import record_result

    ref = payload["arms"][0]
    sha, run = record_result(
        kind="eq-evaluation",
        key="eq-evaluation",
        payload=payload,
        purpose="inference",
        algorithm="formulas evaluated in dependency order with dimensional analysis (pint)",
        library_version="latris",
        summary=describe(payload),
        model_type=MODEL_TYPE,
        hyperparameters={"scenarios": payload["scenarios"], "set": payload["set"]},
        scenarios=payload["scenarios"],
        metrics={o: ref["values"][o] for o in payload["outputs"]},
        commit_subject="Analysis: equation model evaluated",
        root=root,
    )
    return sha, run.id


# ── analysis: sweep ──────────────────────────────────────────────────


def _pick(m: Model, name: str | None, ids: list[str], what: str) -> str:
    """The quantity among ``ids`` that ``name`` names (by label, or the start of one)."""
    if not ids:
        raise ValueError(f"the model has no {what}")
    if name is None:
        return ids[0]
    exact = [i for i in ids if m.labels[i].casefold() == name.casefold()]
    match = exact or [i for i in ids if m.labels[i].casefold().startswith(name.casefold())]
    if len(match) != 1:
        raise ValueError(f"no single {what} matches {name!r}; choose from: {', '.join(m.labels[i] for i in ids)}")
    return match[0]


def sweep(*, input: str | None = None, target: str | None = None, low: float | None = None,  # noqa: A002
          high: float | None = None, steps: int = 25, root: Path | None = None) -> dict[str, Any]:
    """How ``target`` (an output) responds as ``input`` moves from ``low`` to ``high``, everything else at
    its reference value.

    Without ``low``/``high`` the input's stated valid range is swept, or failing that half to one and a
    half times its reference value.
    """
    m = _ready(root)
    x_id = _pick(m, input, _by_label(m.values, m.labels), "input or parameter")
    y_id = _pick(m, target, m.outputs + [i for i in m.order if i not in m.outputs], "output")
    entry = m.values[x_id]
    if not 2 <= steps <= MAX_STEPS:
        raise ValueError(f"steps must be between 2 and {MAX_STEPS}")
    lo = low if low is not None else entry.valid_min if entry.valid_min is not None else None
    hi = high if high is not None else entry.valid_max if entry.valid_max is not None else None
    if lo is None or hi is None:
        if entry.value == 0:
            raise ValueError(f"{m.labels[x_id]} is 0 and has no valid range: give the range to sweep (low, high)")
        a, b = sorted((0.5 * entry.value, 1.5 * entry.value))
        lo, hi = (a if lo is None else lo), (b if hi is None else hi)
    if not lo < hi:
        raise ValueError("the sweep needs low below high")
    xs = [lo + (hi - lo) * k / (steps - 1) for k in range(steps)]
    reported = m.outputs + ([y_id] if y_id not in m.outputs else [])
    series: dict[str, list[float | None]] = {m.labels[i]: [] for i in reported}
    failed: list[float] = []
    for x in xs:
        try:
            values = compute(m, {x_id: x})
        except EquationError:
            failed.append(x)
            values = {}
        for i in reported:
            series[m.labels[i]].append(values.get(i))
    ys = series[m.labels[y_id]]
    good = [(x, y) for x, y in zip(xs, ys, strict=True) if y is not None]
    if len(good) < 2:
        raise ValueError(f"the model can't be evaluated across {lo:g}–{hi:g} {display_units(entry.units)} for "
                         f"{m.labels[x_id]}")
    ref = compute(m)
    diffs = [b[1] - a[1] for a, b in zip(good, good[1:], strict=False)]
    span = max(abs(y) for _, y in good) or 1.0
    tol = 1e-12 * span
    shape = ("flat" if all(abs(d) <= tol for d in diffs) else "increasing" if all(d >= -tol for d in diffs)
             else "decreasing" if all(d <= tol for d in diffs) else "mixed")
    elasticity = None
    if entry.value != 0 and ref[y_id] != 0:
        h = abs(entry.value) * 1e-4
        try:
            up, down = compute(m, {x_id: entry.value + h})[y_id], compute(m, {x_id: entry.value - h})[y_id]
            elasticity = ((up - down) / (2 * h)) * entry.value / ref[y_id]
        except EquationError:
            elasticity = None
    lo_pt, hi_pt = min(good, key=lambda t: t[1]), max(good, key=lambda t: t[1])
    return {
        "input": m.labels[x_id], "input_units": entry.units, "input_role": m.roles[x_id],
        "target": m.labels[y_id], "target_units": m.quantity_units(y_id),
        "low": lo, "high": hi, "steps": steps, "x": xs, "series": series,
        "units": {m.labels[i]: m.quantity_units(i) for i in reported},
        "reference": {"x": entry.value, "y": ref[y_id]},
        "valid_min": entry.valid_min, "valid_max": entry.valid_max,
        "extrapolated": entry.outside(lo) or entry.outside(hi),
        "min": {"x": lo_pt[0], "y": lo_pt[1]}, "max": {"x": hi_pt[0], "y": hi_pt[1]},
        "shape": shape, "elasticity": elasticity, "failed": failed,
        "weak": entry.is_weak,
    }


def describe_sweep(p: dict[str, Any]) -> str:
    ys = p["series"][p["target"]]
    s = (f"As {p['input']} goes from {_num(p['low'])} to {fmt(p['high'], p['input_units'])}, {p['target']} "
         f"runs from {_num(ys[0])} to {fmt(ys[-1], p['target_units'])} ({p['shape']})")
    if p["elasticity"] is not None:
        s += f"; near the reference value a 1% rise in {p['input']} changes it by {p['elasticity']:+.2g}%"
    if p["extrapolated"]:
        s += f"; part of the sweep is outside {p['input']}'s valid range"
    if p["failed"]:
        s += f"; the model can't be evaluated at {len(p['failed'])} of the {p['steps']} points"
    return s


def record_sweep(payload: dict[str, Any], *, root: Path | None = None) -> tuple[str, str]:
    from latris.operations.analysis_results import record_result

    sha, run = record_result(
        kind="eq-sweep",
        key=f"eq-sweep:{payload['input']}→{payload['target']}",
        payload=payload,
        purpose="sensitivity-analysis",
        algorithm="one-at-a-time sweep of one input, the others at their reference values",
        library_version="latris",
        summary=describe_sweep(payload),
        model_type=MODEL_TYPE,
        hyperparameters={"input": payload["input"], "target": payload["target"], "low": payload["low"],
                         "high": payload["high"], "steps": payload["steps"]},
        metrics={"min": payload["min"]["y"], "max": payload["max"]["y"], "elasticity": payload["elasticity"]},
        commit_subject=f"Analysis: sweep of {payload['input']}",
        root=root,
    )
    return sha, run.id


# ── analysis: Monte Carlo ────────────────────────────────────────────


def _summary(values: list[float], point: float) -> dict[str, Any]:
    s = sorted(values)
    mean = math.fsum(s) / len(s)
    return {"point": point, "mean": mean, "p5": smp.percentile(s, 5), "p50": smp.percentile(s, 50),
            "p95": smp.percentile(s, 95), "min": s[0], "max": s[-1],
            "mean_over_point": mean / point if point > 0 else None,
            "share_above_point": sum(1 for v in s if v > point) / len(s)}


def monte_carlo(*, runs: int = 2000, seed: int = 1234, sampling: str = "lhs", target: str | None = None,
                root: Path | None = None) -> dict[str, Any]:
    """Sample every input and parameter that has a range; summarise each output and rank what drives it.

    ``target`` picks the output to headline (default: the first). A draw the formulas can't be evaluated
    at (a negative under a square root) is left out and counted.
    """
    if not 10 <= runs <= MAX_RUNS:
        raise ValueError(f"runs must be between 10 and {MAX_RUNS}")
    paths = require_project(root)
    m = _ready(paths.root)
    primary = _pick(m, target, m.outputs, "output")
    ranges = {i: e for i, e in specs(paths).items() if i in m.values}
    if not ranges:
        raise ValueError("no input or parameter has an uncertainty range yet; give some a distribution first "
                         "(e.g. `latris eq uncertainty <factor> triangular --min 0.02 --mode 0.03 --max 0.05`)")
    draws = smp.sample(ranges, runs, seed=seed, method=sampling)
    point = compute(m)
    outputs: dict[str, list[float]] = {i: [] for i in m.outputs}
    kept: list[dict[str, float]] = []
    for d in draws:
        try:
            values = compute(m, d)
        except EquationError:
            continue
        kept.append(d)
        for i in m.outputs:
            outputs[i].append(values[i])
    if len(kept) < max(10, runs // 2):
        raise ValueError(f"the formulas could be evaluated for only {len(kept)} of {runs} draws; the ranges reach "
                         "values the formulas can't take")
    keys = _by_label(ranges, m.labels)
    correlations = {m.labels[o]: {m.labels[k]: smp.spearman([d[k] for d in kept], vals) for k in keys}
                    for o, vals in outputs.items()}
    drivers = []
    for k in keys:
        e, v = ranges[k], m.values[k]
        sampler = smp.Sampler(e)
        drivers.append({"input": m.labels[k], "role": m.roles[k], "units": v.units, "point": v.value,
                        "distribution": e.distribution, "params": e.params, "reason": e.reason, "origin": e.origin,
                        "source": e.source_id, "weak": e.verification != "human-verified" or e.contested,
                        "p5": sampler.quantile(0.05), "p95": sampler.quantile(0.95),
                        "outside_valid": sum(1 for d in kept if v.outside(d[k])) / len(kept),
                        "spearman": correlations[m.labels[primary]][m.labels[k]]})
    drivers.sort(key=lambda r: -abs(r["spearman"] or 0))
    return {
        "model_type": MODEL_TYPE, "quantity": "value", "primary": m.labels[primary],
        "runs": runs, "seed": seed, "sampling": sampling, "evaluated": len(kept),
        "outputs": [{"output": m.labels[i], "units": m.quantity_units(i), **_summary(v, point[i])}
                    for i, v in outputs.items()],
        "drivers": drivers, "correlations": correlations,
        "fixed": sorted(m.labels[i] for i in m.values if i not in ranges),
    }


def describe_monte_carlo(p: dict[str, Any]) -> str:
    main = next(o for o in p["outputs"] if o["output"] == p["primary"])
    s = (f"{p['primary']}: 90% of {p['evaluated']} runs between {_num(main['p5'])} and "
         f"{fmt(main['p95'], main['units'])} (median {_num(main['p50'])}, value at the reference inputs "
         f"{_num(main['point'])})")
    top = p["drivers"][0] if p["drivers"] else None
    if top and top["spearman"] is not None:
        s += f"; most of the spread comes from {top['input']} (rank correlation {top['spearman']:.2f})"
    if p["fixed"]:
        s += f"; {len(p['fixed'])} value(s) held fixed"
    return s


def record_monte_carlo(payload: dict[str, Any], *, root: Path | None = None) -> tuple[str, str]:
    from latris.operations.analysis_results import record_result

    main = next(o for o in payload["outputs"] if o["output"] == payload["primary"])
    sha, run = record_result(
        kind="eq-monte-carlo",
        key="eq-monte-carlo",
        payload=payload,
        purpose="sensitivity-analysis",
        algorithm=f"Monte Carlo ({'Latin hypercube' if payload['sampling'] == 'lhs' else 'random'} sampling) "
                  "through the model's formulas; Spearman rank correlation for drivers",
        library_version="latris",
        summary=describe_monte_carlo(payload),
        model_type=MODEL_TYPE,
        hyperparameters={"runs": payload["runs"], "sampling": payload["sampling"], "target": payload["primary"]},
        uncertainty=True,
        seed=payload["seed"],
        metrics={"p5": main["p5"], "p50": main["p50"], "p95": main["p95"], "mean": main["mean"],
                 "point": main["point"]},
        commit_subject="Analysis: Monte Carlo on the equation model",
        root=root,
    )
    return sha, run.id
