"""System dynamics results as registry entries — the five recorded SD result kinds.

SD predates the formalism registry. Its model-side wiring (roles, readiness,
outcome, build-spec block, diagram) still lives in its own modules; this
module moves its *results* into the registry as analyses on the ``sd`` model
type, so reports, claims, chart markers, share-link replay and the GUI's
results panel read SD the way they read every newer type (latris#3, SD part).

Kind strings are unchanged (``sd-simulation``, ``sd-options``,
``sd-monte-carlo``, ``sd-sensitivity``, ``sd-loops``), so recorded runs and
share links keep working, and they still lead the report order.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from latris.operations.formalisms import Analysis, ResultKind, register_analysis

_REVIEWED = "human-verified"
_MAX_ROWS = 8  # as exporters.results


# The report's table helpers, imported lazily (as bn.py does) so operations/ doesn't import exporters/ at load.
def _f(x: Any) -> str:
    from latris.exporters.results import _f as f

    return f(x)


def _grounding(origin: str | None, verification: str | None) -> str:
    from latris.exporters.results import _grounding as g

    return g(origin, verification)


def _table(headers: list[str], rows: list[list[str]]) -> list[str]:
    from latris.exporters.results import _table as t

    return t(headers, rows)


def _cf(x: float) -> str:
    return f"{x:.4g}"


def _who(origin: str | None) -> str:
    return {"ai-proposed": "AI-proposed", "data-derived": "derived from data", "human-elicited": "elicited"}.get(
        origin or "", "entered"
    )


# ── report renderers (Markdown) ──────────────────────────────────────

def _render_simulation(p: dict[str, Any]) -> list[str]:
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


def _render_monte_carlo(p: dict[str, Any]) -> list[str]:
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


def _render_sensitivity(p: dict[str, Any]) -> list[str]:
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


def _render_loops(p: dict[str, Any]) -> list[str]:
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


def _render_options(p: dict[str, Any]) -> list[str]:
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


# ── headings ─────────────────────────────────────────────────────────

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


# ── interpretation claims ────────────────────────────────────────────

def _claims_simulation(p: dict[str, Any], out: dict[str, list[str]]) -> None:
    labels, units, roles = p["labels"], p["units"], p["roles"]
    base = p["scenarios"][0]
    t = p["times"]
    stocks = sorted((v for v in labels if roles.get(v) == "stock"), key=labels.get)[:3]
    for s in stocks:
        sm = base["summary"].get(s)
        if not sm:
            continue
        peak = (
            f", peaking at {_cf(sm['peak'])} at t={_cf(sm['peak_time'])}"
            if sm["peak"] > max(sm["start"], sm["end"])
            else ""
        )
        out["answer_to_question"].append(
            f"Simulation (baseline): {labels[s]} goes from {_cf(sm['start'])} to {_cf(sm['end'])} {units[s]} "
            f"over {t[0]:g}–{t[-1]:g} {p['time_units']}{peak}."
        )
    for sc in p["scenarios"][1:]:
        changes = "; ".join(f"{o['label']} {o['baseline']} → {o['value']:g} {o['units']}" for o in sc["overrides"])
        for s in stocks:
            ch, sm = sc.get("change_vs_baseline", {}).get(s), sc["summary"].get(s)
            if not ch or not sm:
                continue
            pct = f" ({ch['end_pct']:+.0f}%)" if ch.get("end_pct") is not None else ""
            claim = (
                f"Scenario {sc['name']} ({changes}): {labels[s]} ends at {_cf(sm['end'])} {units[s]}, "
                f"{_cf(abs(ch['end']))} {units[s]} {'more' if ch['end'] >= 0 else 'less'} than the baseline{pct}."
            )
            out["answer_to_question"].append(claim)
            out["implications"].append(claim)
        if sc.get("verification") != _REVIEWED and sc.get("origin") == "ai-proposed":
            out["open_questions"].append(f"Scenario {sc['name']}'s values are AI-proposed and not yet reviewed.")


def _claims_monte_carlo(p: dict[str, Any], out: dict[str, list[str]]) -> None:
    on = f" on scenario {p['scenario']}" if p.get("scenario") else ""
    t = p["times"][-1]
    by_id = {prm["target_id"]: prm for prm in p["parameters"]}
    for v in p["variables"]:
        e = p["end"][v]
        central = e.get("baseline")
        claim = (
            f"Across {p['succeeded']} sampled runs{on}, {p['labels'][v]} at {t:g} {p['time_units']} is between "
            f"{_cf(e['p2.5'])} and {_cf(e['p97.5'])} {p['units'][v]} in 95% of runs (median {_cf(e['p50'])}"
            + (f"; the run with every value at its stated value gives {_cf(central)}" if central is not None else "")
            + ")."
        )
        out["sensitivity"].append(claim)
        out["confidence_assessment"].append(claim)
        width = e["p97.5"] - e["p2.5"]
        if central is not None and width > 0 and abs(e["p50"] - central) > 0.1 * width:
            out["confidence_assessment"].append(
                f"The typical sampled run of {p['labels'][v]} ({_cf(e['p50'])}) sits "
                f"{'above' if e['p50'] > central else 'below'} the central-value run ({_cf(central)}) because some "
                "uncertainty ranges are lopsided; quote the range, not the central value, as the expected outcome."
            )
        drivers = [r for r in p["influence"][v] if r["rho"] is not None and abs(r["rho"]) >= 0.3]
        if drivers:
            top = drivers[0]
            prm = by_id.get(top["target_id"], {})
            unreviewed = prm.get("verification") != _REVIEWED
            note = f", whose range is {_who(prm.get('origin'))} and not yet reviewed" if unreviewed else ""
            out["sensitivity"].append(
                f"The spread in {p['labels'][v]} comes mostly from {top['label']} "
                f"(rank correlation {top['rho']:+.2f}){note}."
            )
            if unreviewed:
                out["open_questions"].append(
                    f"How wide is {top['label']} really? Its uncertainty range drives most of the spread in "
                    f"{p['labels'][v]} but is {_who(prm.get('origin'))} and not yet reviewed."
                )


def _claims_options(p: dict[str, Any], out: dict[str, list[str]]) -> None:
    from latris.operations.sd_montecarlo import arm_label, describe_option

    world = f"; in every run: {'; '.join(p['world'])}" if p.get("world") else ""
    intro = (f"Options compared on {p['label']} ({p['metric_label']}), {p['succeeded']} paired draws of the "
             f"uncertain values{world}. Each difference is measured against the arm named after 'vs'")
    out["answer_to_question"].append(intro + ":")
    for r in p["options"]:
        claim = "  - " + describe_option(p, r)
        out["answer_to_question"].append(claim)
    for r in p["options"]:
        d = r.get("difference")
        if not d:
            continue
        ref = arm_label(r.get("reference", "baseline"))
        if 0.1 < d["share_lower"] < 0.9:
            out["confidence_assessment"].append(
                f"Whether {r['name']} gives a lower {p['label']} ({p['metric_label']}) than {ref} is uncertain: "
                f"lower in {d['share_lower']:.0%} of draws, higher in {d['share_higher']:.0%}{world}."
            )
        else:
            out["implications"].append(describe_option(p, r) + ".")
    for w in p.get("warnings", []):
        out["open_questions"].append(w)


def _claims_sensitivity(p: dict[str, Any], out: dict[str, list[str]]) -> None:
    rows = [r for r in p["parameters"] if r.get("swing")]
    if not rows:
        return
    on = f" on scenario {p['scenario']}" if p.get("scenario") else ""
    ranged = [r for r in rows if r.get("range_kind", "uncertainty") == "uncertainty"]
    nudged = [r for r in rows if r.get("range_kind") == "pct"]
    top = ranged[:3]
    if top:
        listed = ", ".join(f"{r['label']} (moves it by {_cf(r['swing'])} {p['units']})" for r in top)
        out["sensitivity"].append(
            f"Across their stated uncertainty ranges, {p['label']}'s {p['metric_label']}{on} is most sensitive to "
            f"{listed}."
        )
    if nudged:
        listed = ", ".join(f"{r['label']} ({_cf(r['swing'])} {p['units']})" for r in nudged[:3])
        out["sensitivity"].append(
            f"Values with no stated range, each moved ±{p['pct']:g}% (a probe, not their real uncertainty): "
            f"{listed}."
        )
    for r in top + nudged[:2]:
        if r.get("weak"):
            out["open_questions"].append(
                f"{r['label']} strongly affects {p['label']} but its value is {_who(r.get('origin'))} and not yet "
                f"reviewed."
            )


def _claims_loops(p: dict[str, Any], out: dict[str, list[str]]) -> None:
    from latris.operations.sd_loops import describe

    if not p["loops"]:
        return
    on = f" (scenario {p['scenario']})" if p.get("scenario") else ""
    claim = f"Loop dominance{on}: {describe(p)}."
    out["key_findings"].append(claim)
    out["answer_to_question"].append(claim)
    dominant = {lid for s in p["sets"] for per in s["dominant_periods"] for lid in per["loops"]}
    for lp in p["loops"]:
        if lp["id"] in dominant and lp["weak_links"]:
            links = "; ".join(f"{w['link']} ({w['why']})" for w in lp["weak_links"][:3])
            out["open_questions"].append(f"Loop {lp['id']} dominates for a period but rests on weak links: {links}.")


# ── share-link replay: run a definition, and a recorded run back to one ──

def _what_if(payload: dict[str, Any]) -> list[str]:
    for sc in payload.get("scenarios", [])[1:]:
        if sc["name"] == "what-if":
            return [f"{o['label']}={o['value']!r} {o['units']}" for o in sc.get("overrides", [])]
    return []


def _run(a: Any, root: Path) -> str:
    from latris.operations import sd as sd_ops
    from latris.operations.analysis_replay import _settings
    from latris.repo.layout import ProjectPaths

    paths = ProjectPaths(root)
    s = _settings(a.settings)
    if a.kind == "simulate":
        payload, runs = sd_ops.simulate_scenarios(a.scenarios, a.set, **s, apply_to_all=a.apply_to_all or None,
                                                  root=paths.root)
        return sd_ops.record_comparison(payload, runs, root=paths.root)[1]
    if a.kind == "monte_carlo":
        payload = sd_ops.run_monte_carlo(
            runs=a.runs or 200, seed=a.seed if a.seed is not None else 1234, sampling=a.sampling or "lhs",
            variables=a.variables or None, scenario=a.scenario, settings=s, apply_to_all=a.apply_to_all or None,
            root=paths.root,
        )
        return sd_ops.record_monte_carlo(payload, root=paths.root)[1]
    if a.kind == "compare":
        if not a.variable:
            raise ValueError("comparing options needs a variable")
        payload = sd_ops.run_compare(
            a.scenarios, a.variable, metric=a.metric or "final", runs=a.runs or 200,
            seed=a.seed if a.seed is not None else 1234, sampling=a.sampling or "lhs", settings=s,
            apply_to_all=a.apply_to_all or None, reference=a.reference, root=paths.root,
        )
        return sd_ops.record_compare(payload, root=paths.root)[1]
    if a.kind == "sensitivity":
        if not a.variable:
            raise ValueError("a sensitivity analysis needs a variable")
        payload = sd_ops.run_sensitivity(
            a.variable, metric=a.metric or "final", pct=a.pct or 10.0, scenario=a.scenario, settings=s,
            apply_to_all=a.apply_to_all or None, root=paths.root,
        )
        return sd_ops.record_sensitivity(payload, root=paths.root)[1]
    if a.kind == "loops":
        payload = sd_ops.run_loops(scenario=a.scenario, start=a.start, end=a.end, settings=s, root=paths.root)
        return sd_ops.record_loops(payload, root=paths.root)[1]
    raise ValueError(f"unknown SD analysis kind {a.kind!r}")


def _definition(kind: str, p: dict[str, Any], h: dict[str, Any]) -> Any:
    from latris.operations.analysis_replay import _settings
    from latris.schema.build_spec import SpecAnalysis

    s = _settings(h)
    labels = p.get("labels", {})
    if kind == "sd-simulation":
        saved = [n for n in h.get("scenarios", []) if n != "what-if"]
        return (SpecAnalysis(kind="simulate", settings=s, scenarios=saved, set=_what_if(p),
                                apply_to_all=p.get("world") or []))
    if kind == "sd-monte-carlo":
        return (SpecAnalysis(
            kind="monte_carlo", settings=s, runs=p["runs"], seed=p["seed"], sampling=p["sampling"],
            variables=[labels.get(v, v) for v in p["variables"]], scenario=p.get("scenario"),
            apply_to_all=p.get("world") or [],
        ))
    if kind == "sd-options":
        metric = p["metric"] if p.get("at") is None else f"at:{p['at']:g}"
        return (SpecAnalysis(
            kind="compare", settings=s, scenarios=p["scenarios"], variable=p["label"], metric=metric,
            runs=p["runs"], seed=p["seed"], sampling=p["sampling"], apply_to_all=p.get("world") or [],
            reference=p.get("reference"),
        ))
    if kind == "sd-sensitivity":
        metric = p["metric"] if p.get("at") is None else f"at:{p['at']:g}"
        return (SpecAnalysis(
            kind="sensitivity", settings=s, variable=p["label"], metric=metric, pct=p["pct"],
            scenario=p.get("scenario"), apply_to_all=p.get("world") or [],
        ))
    if kind == "sd-loops":
        lo, hi = p["window"]
        full = p["times"] and lo == p["times"][0] and hi == p["times"][-1]
        return (SpecAnalysis(
            kind="loops", settings=s, scenario=p.get("scenario"),
            start=None if full else lo, end=None if full else hi,
        ))
    raise ValueError(f"not an SD result kind: {kind!r}")


def _kind(kind: str, title: str, render: Any, analysis: str, claims: Any, *, charts: Any = None,
          heading: Any = None) -> ResultKind:
    return ResultKind(
        kind=kind, title=title, render=render, analysis=analysis, run=_run,
        definition=lambda p: _definition(kind, p, {}),
        run_definition=lambda p, run: _definition(kind, p, run.hyperparameters),
        claims=claims, charts=charts, subtitle=lambda p: _sd_subtitle(kind, p), title_for=heading,
    )


def _simulation_charts(p: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    roles = p["roles"]
    stocks = [v for v in p["labels"] if roles.get(v) == "stock"][:4]
    return [("series", {"vars": [v]}) for v in stocks]


for _rk in (
    _kind("sd-simulation", "Simulation", _render_simulation, "simulate", _claims_simulation,
          charts=_simulation_charts),
    _kind("sd-options", "Options compared under uncertainty", _render_options, "compare", _claims_options),
    _kind("sd-monte-carlo", "Uncertainty (Monte Carlo)", _render_monte_carlo, "monte_carlo", _claims_monte_carlo,
          charts=lambda p: [("bands", {"vars": [v]}) for v in p["variables"][:4]]),
    _kind("sd-sensitivity", "Sensitivity", _render_sensitivity, "sensitivity", _claims_sensitivity,
          charts=lambda p: [("tornado", {})], heading=lambda p: f"Sensitivity of {p['label']}"),
    _kind("sd-loops", "Feedback loop dominance", _render_loops, "loops", _claims_loops,
          charts=lambda p: [("loops", {})] if p["loops"] else []),
):
    register_analysis(Analysis(model_type="sd", result=_rk), lead=True)
