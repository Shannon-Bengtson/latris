"""Interpretation claims drawn from recorded results (simulations, uncertainty, loops, BN queries).

Claims are what the model supports — the interpretation's prose must stick to
them. Structural claims come from the diagram; these come from the numbers:
what a simulation shows, what each scenario changes, how wide the uncertainty
is and what drives it, which loop dominates, what a query concludes. Each
claim is a deterministic sentence built from a recorded result, and results
computed before the model last changed are left out (they no longer describe
the model).

Claims also say when a conclusion rests on something unreviewed — an
influential value nobody has checked, a dominant loop built on unsourced
links — so the open questions surface it.
"""

from __future__ import annotations

from typing import Any

from latris.repo.layout import ProjectPaths

_REVIEWED = "human-verified"


def _f(x: float) -> str:
    return f"{x:.4g}"


def _who(origin: str | None) -> str:
    return {"ai-proposed": "AI-proposed", "data-derived": "derived from data", "human-elicited": "elicited"}.get(
        origin or "", "entered"
    )


def _simulation(p: dict[str, Any], out: dict[str, list[str]]) -> None:
    labels, units, roles = p["labels"], p["units"], p["roles"]
    base = p["scenarios"][0]
    t = p["times"]
    stocks = sorted((v for v in labels if roles.get(v) == "stock"), key=labels.get)[:3]
    for s in stocks:
        sm = base["summary"].get(s)
        if not sm:
            continue
        peak = (
            f", peaking at {_f(sm['peak'])} at t={_f(sm['peak_time'])}"
            if sm["peak"] > max(sm["start"], sm["end"])
            else ""
        )
        out["answer_to_question"].append(
            f"Simulation (baseline): {labels[s]} goes from {_f(sm['start'])} to {_f(sm['end'])} {units[s]} "
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
                f"Scenario {sc['name']} ({changes}): {labels[s]} ends at {_f(sm['end'])} {units[s]}, "
                f"{_f(abs(ch['end']))} {units[s]} {'more' if ch['end'] >= 0 else 'less'} than the baseline{pct}."
            )
            out["answer_to_question"].append(claim)
            out["implications"].append(claim)
        if sc.get("verification") != _REVIEWED and sc.get("origin") == "ai-proposed":
            out["open_questions"].append(f"Scenario {sc['name']}'s values are AI-proposed and not yet reviewed.")


def _monte_carlo(p: dict[str, Any], out: dict[str, list[str]]) -> None:
    on = f" on scenario {p['scenario']}" if p.get("scenario") else ""
    t = p["times"][-1]
    by_id = {prm["target_id"]: prm for prm in p["parameters"]}
    for v in p["variables"]:
        e = p["end"][v]
        claim = (
            f"Across {p['succeeded']} sampled runs{on}, {p['labels'][v]} at {t:g} {p['time_units']} is between "
            f"{_f(e['p2.5'])} and {_f(e['p97.5'])} {p['units'][v]} in 95% of runs (median {_f(e['p50'])})."
        )
        out["sensitivity"].append(claim)
        out["confidence_assessment"].append(claim)
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


def _sensitivity(p: dict[str, Any], out: dict[str, list[str]]) -> None:
    rows = [r for r in p["parameters"] if r.get("swing")]
    if not rows:
        return
    top = rows[:3]
    listed = ", ".join(f"{r['label']} (moves it by {_f(r['swing'])} {p['units']})" for r in top)
    on = f" on scenario {p['scenario']}" if p.get("scenario") else ""
    out["sensitivity"].append(f"{p['label']}'s {p['metric_label']}{on} is most sensitive to {listed}.")
    for r in top:
        if r.get("weak"):
            out["open_questions"].append(
                f"{r['label']} strongly affects {p['label']} but its value is {_who(r.get('origin'))} and not yet "
                f"reviewed."
            )


def _loops(p: dict[str, Any], out: dict[str, list[str]]) -> None:
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


def _given(p: dict[str, Any]) -> str:
    from latris.operations.bn import evidence_description

    return evidence_description(p.get("evidence", {}), p.get("soft"), p.get("likelihood"), p.get("labels", {}))


def _soft_question(p: dict[str, Any], out: dict[str, list[str]]) -> None:
    labels = p.get("labels", {})
    for k, dist in sorted((p.get("soft") or {}).items()):
        state = max(dist, key=dist.get)  # type: ignore[arg-type]
        question = (
            f"How sure are we that {labels.get(k, k)} is {state}? The analysis takes it as {dist[state]:.0%} — "
            "an estimate entered by hand, not an observation."
        )
        if question not in out["open_questions"]:
            out["open_questions"].append(question)


def _bn_query(p: dict[str, Any], out: dict[str, list[str]]) -> None:
    labels = p["labels"]
    if not (p["evidence"] or p.get("soft") or p.get("likelihood")):
        return
    _soft_question(p, out)
    given = _given(p)
    for node in sorted(p["posteriors"], key=lambda n: labels.get(n, n))[:4]:
        dist = p["posteriors"][node]
        state = max(dist, key=dist.get)  # type: ignore[arg-type]
        prior = p["priors"].get(node, {}).get(state)
        before = f" (prior {prior * 100:.0f}%)" if prior is not None else ""
        out["answer_to_question"].append(
            f"Given {given}, P({labels.get(node, node)} = {state}) = {dist[state] * 100:.0f}%{before}."
        )


def _bn_explanation(p: dict[str, Any], out: dict[str, list[str]]) -> None:
    from latris.operations.bn import describe_explanation

    out["answer_to_question"].append(describe_explanation(p) + ".")
    _soft_question(p, out)
    labels = p["labels"]
    weak = [r for r in p["rows"] if r.get("times_likelier") is not None and r["times_likelier"] < 1.5]
    for r in weak:
        out["confidence_assessment"].append(
            f"In the most likely explanation, {labels.get(r['node'], r['node'])} = {r['state']} is only "
            f"{r['times_likelier']:.2g}× likelier than {r['runner_up']} — close to a coin-flip."
        )


def _bn_monte_carlo(p: dict[str, Any], out: dict[str, list[str]]) -> None:
    labels = p["labels"]
    s = p["focus_state"]
    b = p["by_state"][s]
    given = _given(p)
    cond = f" | {given}" if given else ""
    claim = (
        f"P({labels.get(p['target'], p['target'])} = {s}{cond}) is between {b['p2.5']:.0%} and {b['p97.5']:.0%} "
        f"in 95% of {p['runs']} draws of the uncertain probability tables (point estimate {b['point']:.0%})."
    )
    out["sensitivity"].append(claim)
    out["confidence_assessment"].append(claim)
    _soft_question(p, out)
    tables = {t["node"]: t for t in p["tables"]}
    drivers = [d for d in p["drivers"] if d["rho"] is not None and abs(d["rho"]) >= 0.3]
    if drivers:
        top = drivers[0]
        t = tables.get(top["node"], {})
        unreviewed = t.get("verification") != _REVIEWED
        note = f", and its uncertainty is {_who(t.get('origin'))} and not yet reviewed" if unreviewed else ""
        out["sensitivity"].append(f"The spread comes mostly from {top['label']}'s probability table{note}.")
        if unreviewed:
            out["open_questions"].append(
                f"How well is {top['label']}'s probability table known? It drives most of the uncertainty in "
                f"P({labels.get(p['target'], p['target'])} = {s})."
            )


def _bn_sensitivity(p: dict[str, Any], out: dict[str, list[str]], labels: dict[str, str]) -> None:
    target = f"P({labels.get(p['target_id'], p['target_id'])} = {p['target_state']})"
    top = p["findings"][:3]
    if not top:
        return
    listed = ", ".join(
        f"P({labels.get(f['node_id'], f['node_id'])} = {f['state']}) (up to {f['influence'] * 100:.0f} points)"
        for f in top
    )
    out["sensitivity"].append(f"{target} is most sensitive to {listed}.")
    for f in top:
        if f.get("weak"):
            out["open_questions"].append(
                f"P({labels.get(f['node_id'], f['node_id'])} = {f['state']}) strongly affects {target} but is not "
                f"yet reviewed."
            )


def claims_by_section(model_type: str, paths: ProjectPaths) -> dict[str, list[str]]:
    """Claims per interpretation section from the current (non-stale) results of ``model_type``."""
    from collections import defaultdict

    from latris.operations.analysis_results import report_results
    from latris.repo.yaml_io import load_model
    from latris.schema import Substrate

    out: dict[str, list[str]] = defaultdict(list)
    results = [r for r in report_results(model_types=[model_type], root=paths.root) if not r.stale]
    if not results:
        return out
    labels = {e.id: e.label for e in load_model(Substrate, paths.conceptual_yaml).entities}
    for r in results:
        kind, p = r.run.result_kind, r.payload
        try:
            if kind == "sd-simulation":
                _simulation(p, out)
            elif kind == "sd-monte-carlo":
                _monte_carlo(p, out)
            elif kind == "sd-sensitivity":
                _sensitivity(p, out)
            elif kind == "sd-loops":
                _loops(p, out)
            elif kind == "bn-query":
                _bn_query(p, out)
            elif kind == "bn-explanation":
                _bn_explanation(p, out)
            elif kind == "bn-monte-carlo":
                _bn_monte_carlo(p, out)
            elif kind == "bn-sensitivity":
                _bn_sensitivity(p, out, labels)
        except (KeyError, TypeError, ValueError, IndexError):
            continue  # an unreadable result contributes no claims rather than a wrong one
    return out
