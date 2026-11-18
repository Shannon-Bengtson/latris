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

from latris.exporters import md
from latris.repo.layout import ProjectPaths

_HUMAN_VERIFIED = "human-verified"
_MAX_ROWS, _esc, _f, _table, _grounding = md.MAX_ROWS, md.esc, md.fmt, md.table, md.grounding










def _marker(run_id: str, chart: str, **extra: Any) -> list[str]:
    return ["```latris-chart", json.dumps({"run": run_id, "chart": chart, **extra}), "```", ""]


def _run_date(run_id: str) -> str:
    from latris.schema.ids import id_timestamp

    try:
        return id_timestamp(run_id).strftime("%Y-%m-%d %H:%M UTC")
    except (ValueError, TypeError):
        return "date unknown"


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


_TITLES = {
    "sd-simulation": "Simulation",
    "sd-options": "Options compared under uncertainty",
    "sd-monte-carlo": "Uncertainty (Monte Carlo)",
    "sd-sensitivity": "Sensitivity",
    "sd-loops": "Feedback loop dominance",
}


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


def _heading(kind: str, title: str, p: dict[str, Any], plugin_kind: Any) -> str:
    world = p.get("world") if isinstance(p, dict) else None
    title = f"{title} (in every run: {'; '.join(world)})" if world else title
    try:
        if plugin_kind is not None and plugin_kind.subtitle:
            sub = plugin_kind.subtitle(p)
        elif kind in _TITLES:
            sub = _sd_subtitle(kind, p)
        else:
            sub = ""
    except (KeyError, TypeError, ValueError, IndexError):
        sub = ""
    return f"{title}: {sub}" if sub else title


def _charts(kind: str, payload: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """The ``latris-chart`` markers for one result: the plugin's own ``charts`` hook when it has one,
    else the legacy sd mapping (which moves to the sd plugin when that type registers)."""
    from latris.operations import formalisms

    found = formalisms.result_kind(kind)
    if found and found[1].charts:
        return found[1].charts(payload)
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
    return []


def render_results(
    paths: ProjectPaths,
    *,
    model_types: list[str] | None = None,
    chart_markers: bool = False,
    show_ids: bool = True,
) -> list[str]:
    """The Results section's lines, or ``[]`` when nothing has been recorded."""
    from latris.operations import formalisms
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
        found = formalisms.result_kind(kind)
        plugin_kind = found[1] if found else None
        title = _TITLES.get(kind) or (plugin_kind.title if plugin_kind else kind)
        if kind == "sd-sensitivity":
            title = f"Sensitivity of {p['label']}"
        out.append(f"### {_heading(kind, title, p, plugin_kind)}")
        out.append("")
        out += [f"_Run {_run_date(res.run.id)}._", ""]
        out += _stale_note(res.stale, res.run.id, show_ids)
        if chart_markers:
            for chart, extra in _charts(kind, p):
                out += _marker(res.run.id, chart, **extra)
        try:
            if kind == "sd-simulation":
                out += _simulation(p)
            elif kind == "sd-monte-carlo":
                out += _monte_carlo(p)
            elif kind == "sd-options":
                out += _options(p)
            elif kind == "sd-sensitivity":
                out += _sensitivity(p)
            elif kind == "sd-loops":
                out += _loops(p)
            elif plugin_kind:
                out += plugin_kind.render(p)
        except (KeyError, TypeError, ValueError, IndexError):
            out += [f"_This result couldn't be shown ({res.run.output_summary})._", ""]
    return out
