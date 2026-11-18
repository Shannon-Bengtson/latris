"""System dynamics as a formalism plugin: its result kinds (simulation, options compared, Monte Carlo,
sensitivity, loop dominance), how the report shows them and how a link replays them, its build-spec
block, and its outcome (kept with the SD settings, since SD roles are one per factor).

SD's interpretation claims about the live model are still composed in ``operations/interpret.py`` with
the causal types'; its readiness validators sit in ``readiness._STRUCTURAL_VALIDATORS``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from latris.operations.formalisms import Formalism, ResultKind, default_origin, register

_MAX_ROWS = 8  # rows a result table shows before folding the rest (as exporters.results)


def _f(x: Any) -> str:
    from latris.exporters.results import _f as f

    return f(x)


def _table(headers: list[str], rows: list[list[str]]) -> list[str]:
    from latris.exporters.results import _table as t

    return t(headers, rows)


def _grounding(origin: str | None, verification: str | None) -> str:
    from latris.exporters.results import _grounding as g

    return g(origin, verification)


# ── how the report shows each result ─────────────────────────────────

def _simulation(p: dict[str, Any]) -> list[str]:
    labels, units, roles = p["labels"], p["units"], p["roles"]
    t = p["times"]
    out = [f"Simulated {t[0]:g}–{t[-1]:g} {p['time_units']} ({p['method']})." if t else "No output.", ""]
    scenarios = p["scenarios"]
    for sc in scenarios[1:]:
        changes = "; ".join(f"{o['label']} {o['baseline']} → {o['value']:g} {o['units']}" for o in sc["overrides"])
        why = f" _{sc['reason']}_" if sc.get("reason") else ""
        desc = f" — {sc['description']}" if sc.get("description") else ""
        out.append(
            f"- **{sc['name']}**{desc}: {changes}.{why} ({_grounding(sc.get('origin'), sc.get('verification'))})"
        )
    if len(scenarios) > 1:
        out.append("")
    order = {"stock": 0, "flow": 1, "auxiliary": 2}
    shown = sorted((v for v in labels if v in roles), key=lambda v: (order.get(roles[v], 9), labels[v]))[:_MAX_ROWS]
    base = scenarios[0]
    headers = ["Variable", "Start → end", "Peak (at)"] + [f"{sc['name']}: end (change)" for sc in scenarios[1:]]
    rows = []
    for v in shown:
        s = base["summary"].get(v)
        if not s:
            continue
        row = [
            f"{labels[v]} ({units[v]})",
            f"{_f(s['start'])} → {_f(s['end'])}",
            f"{_f(s['peak'])} (t={_f(s['peak_time'])})",
        ]
        for sc in scenarios[1:]:
            ss, ch = sc["summary"].get(v), sc.get("change_vs_baseline", {}).get(v)
            pct = f", {ch['end_pct']:+.3g}%" if ch and ch.get("end_pct") is not None else ""
            row.append(f"{_f(ss['end'])} ({ch['end']:+.4g}{pct})" if ss and ch else "—")
        rows.append(row)
    out += _table(headers, rows)
    for sc in scenarios:
        if not sc["success"]:
            out.append(f"_The {sc['name']} run failed: {sc['message']}_")
        for w in sc.get("warnings", []):
            out.append(f"_{sc['name']}: {w}_")
    return out

def _monte_carlo(p: dict[str, Any]) -> list[str]:
    on = f" on scenario **{p['scenario']}**" if p.get("scenario") else ""
    sampler = "Latin hypercube" if p["sampling"] == "lhs" else "random"
    out = [
        f"{p['succeeded']} of {p['runs']} runs succeeded{on} ({sampler} sampling, seed {p['seed']}). "
        f"Values at {p['times'][-1]:g} {p['time_units']}:",
        "",
    ]
    rows = []
    for v in p["variables"]:
        e = p["end"][v]
        rows.append(
            [
                f"{p['labels'][v]} ({p['units'][v]})",
                _f(e["baseline"]),
                _f(e["p50"]),
                f"{_f(e['p25'])}–{_f(e['p75'])}",
                f"{_f(e['p2.5'])}–{_f(e['p97.5'])}",
            ]
        )
    out += _table(["Variable", "Baseline", "Median", "50% of runs", "95% of runs"], rows)
    out.append("Uncertain values sampled:")
    out.append("")
    for prm in p["parameters"]:
        pretty = ", ".join(f"{k} {v:g}" for k, v in prm["params"].items())
        why = f" — {prm['reason']}" if prm.get("reason") else ""
        out.append(
            f"- {prm['label']} ~ {prm['distribution']}({pretty}) {prm['units']}{why} "
            f"({_grounding(prm.get('origin'), prm.get('verification'))})"
        )
    for prm in p.get("skipped_parameters", []):
        out.append(f"- {prm['label']}: {prm['reason']}")
    out.append("")
    for v in p["variables"]:
        drivers = [r for r in p["influence"][v] if r["rho"] is not None and abs(r["rho"]) >= 0.1][:3]
        if drivers:
            listed = ", ".join(f"{r['label']} (rank correlation {r['rho']:+.2f})" for r in drivers)
            out.append(f"What drives the spread in {p['labels'][v]}: {listed}.")
    out.append("")
    return out

def _options(p: dict[str, Any]) -> list[str]:
    u = p["units"]
    out = [
        f"{p['label']}, {p['metric_label']} ({u}). Every option ran on the same {p['succeeded']} sampled draws "
        f"of the uncertain values ({', '.join(p['uncertain'])}; {p['sampling']}, seed {p['seed']}), so each "
        "difference from its reference is measured draw by draw (positive: higher than the reference). "
        "The baseline is the model with no scenario changes. 'Central values' is the run with every value "
        "at its stated value; with skewed ranges the median draw can sit away from it.",
        "",
    ]
    rows = []
    for r in p["options"]:
        d = r.get("difference")
        rows.append([
            "Baseline (no scenario changes)" if r["name"] == "baseline" else r["name"],
            f"{r['p50']:.4g}", f"{r['p2.5']:.4g}–{r['p97.5']:.4g}", f"{r['central']:.4g}",
            r.get("reference", "baseline") if d else "—",
            f"{d['p50']:+.4g} ({d['p2.5']:+.4g} to {d['p97.5']:+.4g})" if d else "—",
            f"{d['share_lower']:.0%} / {d['share_higher']:.0%}" if d else "—",
        ])
    out += _table(["Option", "Median", "95% of draws", "Central values", "Compared with",
                   "Difference (median, 95%)", "Draws lower / higher"], rows)
    for w in p.get("warnings", []):
        out += ["", f"> ⚠ {w}"]
    return out

def _sensitivity(p: dict[str, Any]) -> list[str]:
    on = f" on scenario **{p['scenario']}**" if p.get("scenario") else ""
    out = [
        f"How far each value moves {p['label']}'s {p['metric_label']}{on} (baseline {_f(p['baseline'])} "
        f"{p['units']}), swinging it across its uncertainty range where one is recorded, else ±{p['pct']:g}%.",
        "",
    ]
    rows = []
    for r in [r for r in p["parameters"] if r.get("swing")][:_MAX_ROWS]:
        rows.append(
            [
                r["label"],
                f"{_f(r['low'])}–{_f(r['high'])} {r['units']}",
                r["range_source"],
                f"{_f(r['result_low'])} → {_f(r['result_high'])}",
                _f(r["swing"]),
                _grounding(r.get("origin"), r.get("verification")),
            ]
        )
    out += _table(["Value", "Range tested", "Range from", f"{p['label']} range", "Swing", "Grounding"], rows)
    weak = [r for r in p["parameters"] if r.get("swing") and r.get("weak")][:3]
    if weak and weak[0] is next((r for r in p["parameters"] if r.get("swing")), None):
        out.append(f"The result is most sensitive to {weak[0]['label']}, which has not been reviewed.")
        out.append("")
    return out

def _loops(p: dict[str, Any]) -> list[str]:
    from latris.operations.sd_loops import describe

    if not p["loops"]:
        return ["The model has no feedback loops.", ""]
    on = f" on scenario **{p['scenario']}**" if p.get("scenario") else ""
    lo, hi = p["window"]
    out = [
        f"Which feedback loop drives the behaviour{on}, {lo:g}–{hi:g} {p['time_units']} (Loops That Matter):",
        "",
        describe(p) + ".",
        "",
    ]
    rows = []
    for lp in p["loops"][:_MAX_ROWS]:
        kind = "reinforcing" if lp["polarity"] == "R" else "balancing"
        weak = "; ".join(f"{w['link']} ({w['why']})" for w in lp["weak_links"]) or "—"
        rows.append(
            [lp["id"], kind, " → ".join([*lp["members"], lp["members"][0]]), f"{lp['average_share'] * 100:.0f}%", weak]
        )
    out += _table(["Loop", "Type", "Path", "Average share", "Weak links"], rows)
    return out

def _sd_subtitle(kind: str, p: dict[str, Any]) -> str:
    """What an SD run was of: which scenarios it compared, or which one it ran on."""
    if kind == "sd-simulation":
        shown = [("unsaved what-if (" + "; ".join(f"{o['label']}={o['value']:g}" for o in sc.get("overrides", []))
                  + ")") if sc["name"] == "what-if" else sc["name"] for sc in p.get("scenarios", [])[1:]]
        return "baseline vs " + ", ".join(shown) if shown else "baseline"
    if kind == "sd-options":
        return f"{p['label']}, {p['metric_label']}"
    scenario = p.get("scenario")
    return f"scenario {scenario}" if scenario else "baseline"



def _sensitivity_title(p: dict[str, Any]) -> str:
    return f"Sensitivity of {p['label']}"


# ── how a build spec or link runs each, and describes a recorded one ─


def _settings(a: Any) -> dict[str, Any]:
    from latris.operations.analysis_replay import _settings as settings

    return settings(a.settings)


def _run_simulate(a: Any, root: Path) -> str:
    from latris.operations import sd as sd_ops

    payload, runs = sd_ops.simulate_scenarios(a.scenarios, a.set, **_settings(a), apply_to_all=a.apply_to_all or None,
                                              root=root)
    return sd_ops.record_comparison(payload, runs, root=root)[1]


def _run_monte_carlo(a: Any, root: Path) -> str:
    from latris.operations import sd as sd_ops

    payload = sd_ops.run_monte_carlo(
        runs=a.runs or 200, seed=a.seed if a.seed is not None else 1234, sampling=a.sampling or "lhs",
        variables=a.variables or None, scenario=a.scenario, settings=_settings(a), apply_to_all=a.apply_to_all or None,
        root=root,
    )
    return sd_ops.record_monte_carlo(payload, root=root)[1]


def _run_compare(a: Any, root: Path) -> str:
    from latris.operations import sd as sd_ops

    if not a.variable:
        raise ValueError("comparing options needs a variable")
    payload = sd_ops.run_compare(
        a.scenarios, a.variable, metric=a.metric or "final", runs=a.runs or 200,
        seed=a.seed if a.seed is not None else 1234, sampling=a.sampling or "lhs", settings=_settings(a),
        apply_to_all=a.apply_to_all or None, reference=a.reference, root=root,
    )
    return sd_ops.record_compare(payload, root=root)[1]


def _run_sensitivity(a: Any, root: Path) -> str:
    from latris.operations import sd as sd_ops

    if not a.variable:
        raise ValueError("a sensitivity analysis needs a variable")
    payload = sd_ops.run_sensitivity(
        a.variable, metric=a.metric or "final", pct=a.pct or 10.0, scenario=a.scenario, settings=_settings(a),
        apply_to_all=a.apply_to_all or None, root=root,
    )
    return sd_ops.record_sensitivity(payload, root=root)[1]


def _run_loops(a: Any, root: Path) -> str:
    from latris.operations import sd as sd_ops

    payload = sd_ops.run_loops(scenario=a.scenario, start=a.start, end=a.end, settings=_settings(a), root=root)
    return sd_ops.record_loops(payload, root=root)[1]


def _definition_args(h: dict[str, Any]) -> dict[str, Any]:
    from latris.operations.analysis_replay import _settings as settings

    return {"settings": settings(h)}


def _def_simulate(p: dict[str, Any], h: dict[str, Any]) -> Any:
    from latris.operations.analysis_replay import _what_if
    from latris.schema.build_spec import make_analysis

    saved = [n for n in h.get("scenarios", []) if n != "what-if"]
    return make_analysis(kind="simulate", **_definition_args(h), scenarios=saved, set=_what_if(p),
                         apply_to_all=p.get("world") or [])


def _def_monte_carlo(p: dict[str, Any], h: dict[str, Any]) -> Any:
    from latris.schema.build_spec import make_analysis

    labels = p.get("labels", {})
    return make_analysis(
        kind="monte_carlo", **_definition_args(h), runs=p["runs"], seed=p["seed"], sampling=p["sampling"],
        variables=[labels.get(v, v) for v in p["variables"]], scenario=p.get("scenario"),
        apply_to_all=p.get("world") or [],
    )


def _def_compare(p: dict[str, Any], h: dict[str, Any]) -> Any:
    from latris.schema.build_spec import make_analysis

    metric = p["metric"] if p.get("at") is None else f"at:{p['at']:g}"
    return make_analysis(
        kind="compare", **_definition_args(h), scenarios=p["scenarios"], variable=p["label"], metric=metric,
        runs=p["runs"], seed=p["seed"], sampling=p["sampling"], apply_to_all=p.get("world") or [],
        reference=p.get("reference"),
    )


def _def_sensitivity(p: dict[str, Any], h: dict[str, Any]) -> Any:
    from latris.schema.build_spec import make_analysis

    metric = p["metric"] if p.get("at") is None else f"at:{p['at']:g}"
    return make_analysis(
        kind="sensitivity", **_definition_args(h), variable=p["label"], metric=metric, pct=p["pct"],
        scenario=p.get("scenario"), apply_to_all=p.get("world") or [],
    )


def _def_loops(p: dict[str, Any], h: dict[str, Any]) -> Any:
    from latris.schema.build_spec import make_analysis

    lo, hi = p["window"]
    full = p["times"] and lo == p["times"][0] and hi == p["times"][-1]
    return make_analysis(kind="loops", **_definition_args(h), scenario=p.get("scenario"),
                         start=None if full else lo, end=None if full else hi)


# ── charts and the interpretation's claims from results ───────────────


def _charts_simulation(p: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    roles = p["roles"]
    stocks = [v for v in p["labels"] if roles.get(v) == "stock"][:4]
    return [("series", {"vars": [v]}) for v in stocks]


def _charts_monte_carlo(p: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [("bands", {"vars": [v]}) for v in p["variables"][:4]]


def _charts_options(p: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [("options-diff", {})] if len(p.get("options") or []) > 1 else []


def _charts_loops(p: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [("loops", {})] if p["loops"] else []


def _claims(name: str):  # noqa: ANN202 — (payload, claims by section) → None
    def add(p: dict[str, Any], out: dict[str, list[str]]) -> None:
        from latris.operations import result_claims

        getattr(result_claims, name)(p, out)

    return add


# ── build spec, share link and outcome ───────────────────────────────


def _check(block: Any, known: Any, outcome: str | None) -> list[str]:
    names = ([("sd role", r.node) for r in block.roles] + [("sd stock", s.node) for s in block.stocks]
             + [("sd constant", c.node) for c in block.constants] + [("sd equation", e.node) for e in block.equations]
             + [("sd table", t.node) for t in block.tables] + [("sd uncertainty", u.node) for u in block.uncertainty])
    return [f"{where}: no factor named {n!r}" for where, n in names if not known(n)]


def _apply(block: Any, verified_by: str, root: Path) -> int:
    return _apply_values(block, default_origin(verified_by), root)


def _apply_values(sd, default_origin: str, root: Path) -> int:
    """Roles first (equations need them), then values, equations, tables, uncertainty, scenarios."""
    from latris.operations import sd as sd_ops
    from latris.operations import sd_scenarios, uncertainty

    n = 0
    for r in sd.roles:
        sd_ops.set_role(r.node, r.role, root=root)
        n += 1
    if sd.settings:
        sd_ops.set_settings(**{("method" if k == "integration_method" else k): v
                               for k, v in sd.settings.items()}, root=root)
        n += 1
    for s in sd.stocks:
        sd_ops.set_initial_value(s.node, s.value, s.units, non_negative=s.non_negative,
                                 origin=s.origin or default_origin, source_id=s.source, root=root)
        n += 1
    for c in sd.constants:
        sd_ops.set_constant(c.node, c.value, c.units, origin=c.origin or default_origin, source_id=c.source,
                            root=root)
        n += 1
    for e in sd.equations:
        sd_ops.set_equation(e.node, e.expression, e.units, origin=e.origin or default_origin, source_id=e.source,
                            root=root)
        n += 1
    for t in sd.tables:
        sd_ops.set_table(t.node, [tuple(p) for p in t.points], t.x_units, t.y_units, extrapolate=t.extrapolate,
                         origin=t.origin or default_origin, source_id=t.source, root=root)
        n += 1
    for u in sd.uncertainty:
        uncertainty.set_uncertainty(u.node, u.distribution, u.params, reason=u.reason, source_id=u.source,
                                    origin=u.origin or default_origin, root=root)  # type: ignore[arg-type]
        n += 1
    from latris.operations.build import _parents_first

    for sc in _parents_first(sd.scenarios):
        sd_scenarios.set_scenario(sc.name, sc.set, description=sc.description, extends=sc.extends,
                                  reason=sc.reason, origin=sc.origin or default_origin,  # type: ignore[arg-type]
                                  source_id=sc.source, root=root)
        n += 1
    return n


def _export(paths, labels: dict[str, str]):  # noqa: ANN001, ANN202
    """System Dynamics parameters as spec entries (origins kept; reviews are not carried)."""
    from latris.operations import sd as sd_ops
    from latris.operations import sd_scenarios, uncertainty
    from latris.schema.build_spec import (
        SpecScenario,
        SpecSD,
        SpecSDEquation,
        SpecSDRole,
        SpecSDStock,
        SpecSDTable,
        SpecSDValue,
        SpecUncertainty,
    )

    def named(target_id: str) -> bool:
        return target_id in labels

    roles = [SpecSDRole(node=labels[r.target_id], role=r.value)
             for r in sd_ops.get_roles(root=paths.root).entries if named(r.target_id)]
    if not roles:
        return None
    stocks = [SpecSDStock(node=labels[e.target_id], value=e.initial_value, units=e.units,
                          non_negative=e.non_negative, origin=e.origin, source=e.source_id)
              for e in sd_ops.get_stocks(root=paths.root).entries if named(e.target_id)]
    constants = [SpecSDValue(node=labels[e.target_id], value=e.value, units=e.units, origin=e.origin,
                             source=e.source_id)
                 for e in sd_ops.get_constants(root=paths.root).entries if named(e.target_id)]
    equations = [SpecSDEquation(node=labels[e.target_id], expression=e.expression, units=e.units,
                                origin=e.origin, source=e.source_id)
                 for e in sd_ops.get_equations(root=paths.root).entries if named(e.target_id)]
    tables = [SpecSDTable(node=labels[e.target_id], points=[(p.x, p.y) for p in e.points], x_units=e.x_units,
                          y_units=e.y_units, extrapolate=e.extrapolate, origin=e.origin, source=e.source_id)
              for e in sd_ops.get_tables(root=paths.root).entries if named(e.target_id)]
    ranges = [SpecUncertainty(node=labels[e.target_id], distribution=e.distribution, params=e.params,
                              reason=e.reason, origin=e.origin, source=e.source_id)
              for e in uncertainty.sd_specs(paths).values() if named(e.target_id)]
    scenarios = [
        SpecScenario(
            name=s.name, extends=s.extends, description=s.description, reason=s.reason, origin=s.origin,
            source=s.source_id,
            set=[f"{labels[o.target_id]}={o.value!r} {o.units}" for o in s.overrides if named(o.target_id)],
        )
        for s in sd_scenarios.load(paths).scenarios
        if any(named(o.target_id) for o in s.overrides)
    ]
    stored = sd_ops.get_settings(root=paths.root).model_dump(exclude_none=True, exclude={"outcome"})
    return SpecSD(settings=stored, roles=roles, stocks=stocks, constants=constants, equations=equations, tables=tables,
                  uncertainty=ranges, scenarios=scenarios)


def _outcome_ids(paths: Any) -> set[str]:
    from latris.operations import sd as sd_ops

    outcome = sd_ops.get_settings(root=paths.root).outcome
    return {outcome} if outcome else set()


def _set_outcome(target: str, root: Path) -> Any:
    from latris.operations import sd as sd_ops

    return sd_ops.set_outcome(target, root=root)


@dataclass(frozen=True)
class _Problem:
    target_id: str | None
    gap_type: str
    message: str


def _problems(root: Path) -> list[_Problem]:
    from latris.operations import sd as sd_ops

    return [_Problem(g.element_id or None, g.gap_type, g.message) for g in sd_ops.check(root=root)]


def _subtitle(kind: str):  # noqa: ANN202
    return lambda p: _sd_subtitle(kind, p)


register(Formalism(
    model_type="sd",
    # SD roles are one per factor (stock, flow, ...), so the outcome is kept with the SD settings.
    outcome_role="outcome",
    outcome_refusal="System dynamics keeps its outcome with its settings: `latris view role sd <factor> outcome`.",
    outcome_ids=_outcome_ids,
    set_outcome=_set_outcome,
    structure_problems=_problems,
    results=(
        ResultKind(kind="sd-simulation", title="Simulation", render=_simulation, analysis="simulate",
                   run=_run_simulate, definition=_def_simulate, definition_reads_run=True,
                   claims=_claims("_simulation"), charts=_charts_simulation, chart_kinds=("series",),
                   subtitle=_subtitle("sd-simulation")),
        ResultKind(kind="sd-options", title="Options compared under uncertainty", render=_options,
                   analysis="compare", run=_run_compare, definition=_def_compare, definition_reads_run=True,
                   claims=_claims("_options"), charts=_charts_options, chart_kinds=("options-diff",),
                   subtitle=_subtitle("sd-options")),
        ResultKind(kind="sd-monte-carlo", title="Uncertainty (Monte Carlo)", render=_monte_carlo,
                   analysis="monte_carlo", run=_run_monte_carlo, definition=_def_monte_carlo,
                   definition_reads_run=True, claims=_claims("_monte_carlo"), charts=_charts_monte_carlo,
                   chart_kinds=("bands",), subtitle=_subtitle("sd-monte-carlo")),
        ResultKind(kind="sd-sensitivity", title="Sensitivity", render=_sensitivity, analysis="sensitivity",
                   run=_run_sensitivity, definition=_def_sensitivity, definition_reads_run=True,
                   claims=_claims("_sensitivity"), charts=lambda p: [("tornado", {})], chart_kinds=("tornado",),
                   subtitle=_subtitle("sd-sensitivity"), title_for=_sensitivity_title),
        ResultKind(kind="sd-loops", title="Feedback loop dominance", render=_loops, analysis="loops",
                   run=_run_loops, definition=_def_loops, definition_reads_run=True, claims=_claims("_loops"),
                   charts=_charts_loops, chart_kinds=("loops",), subtitle=_subtitle("sd-loops")),
    ),
    spec_field="sd",
    spec_check=_check,
    spec_apply=_apply,
    spec_export=_export,
    cli=("latris.cli.sd_cmd", "sd"),
    routes="latris.server.routes.sd",
))
