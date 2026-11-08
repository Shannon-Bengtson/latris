"""The "Results" report section — recorded simulations, uncertainty runs, loop dominance, BN queries.

Reads :func:`latris.operations.analysis_results.report_results` (the latest
run of each analysis, minus hidden ones) and writes compact Markdown tables:
what a reader needs to see the numbers behind the answer. Results computed
before a later model change are marked out of date.

With ``chart_markers=True`` (the hosted report and Word export pass it) each
result is preceded by a fenced ``latris-chart`` block naming the run and the
chart to draw; the app swaps those for SVG charts. Plain ``export md`` leaves
them out, so the Markdown stays clean.
"""

from __future__ import annotations

import json
from typing import Any

from latris.repo.layout import ProjectPaths

_HUMAN_VERIFIED = "human-verified"
_MAX_ROWS = 8


def _f(x: Any) -> str:
    if x is None:
        return "—"
    if isinstance(x, float | int):
        return f"{x:.4g}"
    return str(x)


def _esc(text: Any) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _table(headers: list[str], rows: list[list[str]]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(_esc(c) for c in row) + " |" for row in rows]
    out.append("")
    return out


def _grounding(origin: str | None, verification: str | None) -> str:
    if verification == _HUMAN_VERIFIED:
        return "reviewed"
    who = {"ai-proposed": "AI-proposed", "data-derived": "from data", "human-elicited": "elicited"}.get(
        origin or "", "entered"
    )
    return f"{who}, not yet reviewed"


def _marker(run_id: str, chart: str, **extra: Any) -> list[str]:
    return ["```latris-chart", json.dumps({"run": run_id, "chart": chart, **extra}), "```", ""]


def _stale_note(stale: bool, run_id: str, show_ids: bool) -> list[str]:
    if not stale:
        return []
    how = f" Re-run it, or hide it with `latris results hide {run_id}`." if show_ids else ""
    return [f"> **Out of date** — the model changed after this was computed.{how}", ""]


# ── per kind ─────────────────────────────────────────────────────────


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


def _bn_query(p: dict[str, Any]) -> list[str]:
    labels = p["labels"]
    given = ", ".join(f"{labels.get(k, k)} = {v}" for k, v in sorted(p["evidence"].items()))
    out = [f"Given {given}:" if given else "With no evidence (prior probabilities):", ""]
    rows = []
    for node in sorted(p["posteriors"], key=lambda n: labels.get(n, n))[:_MAX_ROWS]:
        for state, prob in p["posteriors"][node].items():
            prior = p["priors"].get(node, {}).get(state)
            rows.append([labels.get(node, node), state, _pct(prior) if given else "", _pct(prob)])
    headers = ["Node", "State", "Prior", "Posterior"] if given else ["Node", "State", "", "Probability"]
    out += _table(headers, rows)
    return out


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:.1f}%"


def _bn_sensitivity(p: dict[str, Any], labels: dict[str, str]) -> list[str]:
    target = labels.get(p["target_id"], p["target_id"])
    out = [f"Which probabilities move P({target} = {p['target_state']}) (baseline {_pct(p['baseline'])}):", ""]
    rows = []
    for f in p["findings"][:_MAX_ROWS]:
        given = ", ".join(f"{labels.get(k, k)}={v}" for k, v in f["parent_states"].items())
        cell = f"P({labels.get(f['node_id'], f['node_id'])}={f['state']}{' | ' + given if given else ''})"
        rows.append(
            [
                cell,
                _pct(f["baseline_prob"]),
                f"{f['influence'] * 100:.1f} points",
                _grounding(f.get("origin"), f.get("verification")),
            ]
        )
    out += _table(["Probability", "Value", "Target moves by up to", "Grounding"], rows)
    return out


_TITLES = {
    "sd-simulation": "Simulation",
    "sd-monte-carlo": "Uncertainty (Monte Carlo)",
    "sd-sensitivity": "Sensitivity",
    "sd-loops": "Feedback loop dominance",
    "bn-query": "Probabilities",
    "bn-sensitivity": "Probability sensitivity",
}


def _charts(kind: str, payload: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    if kind == "sd-simulation":
        roles = payload["roles"]
        stocks = [v for v in payload["labels"] if roles.get(v) == "stock"][:4]
        return [("series", {"vars": [v]}) for v in stocks]
    if kind == "sd-monte-carlo":
        return [("bands", {"vars": [v]}) for v in payload["variables"][:4]]
    if kind == "sd-sensitivity":
        return [("tornado", {})]
    if kind == "sd-loops":
        return [("loops", {})] if payload["loops"] else []
    if kind == "bn-query":
        return [("posterior", {})]
    if kind == "bn-sensitivity":
        return [("bn-tornado", {})]
    return []


def render_results(
    paths: ProjectPaths,
    *,
    model_types: list[str] | None = None,
    chart_markers: bool = False,
    show_ids: bool = True,
    labels: dict[str, str] | None = None,
) -> list[str]:
    """The Results section's lines, or ``[]`` when nothing has been recorded."""
    from latris.operations.analysis_results import report_results

    results = report_results(model_types=model_types, root=paths.root)
    if not results:
        return []
    out = [
        "## Results",
        "",
        "The latest run of each analysis on this model. Every value a run changed or sampled is listed "
        "with where it came from.",
        "",
    ]
    for res in results:
        kind, p = res.run.result_kind, res.payload
        title = _TITLES.get(kind, kind)
        if kind == "sd-sensitivity":
            title = f"Sensitivity of {p['label']}"
        elif kind == "bn-sensitivity":
            title = f"Probability sensitivity: {(labels or {}).get(p['target_id'], p['target_id'])}"
        out.append(f"### {title}")
        out.append("")
        out += _stale_note(res.stale, res.run.id, show_ids)
        if chart_markers:
            for chart, extra in _charts(kind, p):
                out += _marker(res.run.id, chart, **extra)
        try:
            if kind == "sd-simulation":
                out += _simulation(p)
            elif kind == "sd-monte-carlo":
                out += _monte_carlo(p)
            elif kind == "sd-sensitivity":
                out += _sensitivity(p)
            elif kind == "sd-loops":
                out += _loops(p)
            elif kind == "bn-query":
                out += _bn_query(p)
            elif kind == "bn-sensitivity":
                out += _bn_sensitivity(p, labels or {})
        except (KeyError, TypeError, ValueError, IndexError):
            out += [f"_This result couldn't be shown ({res.run.output_summary})._", ""]
    return out
