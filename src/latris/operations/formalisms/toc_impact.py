"""Impact estimation as an analysis layer on the theory of change (``operations/impact.py``).

Interrupted time series or difference-in-differences for one factor of the results chain, from a registered
dataset — how it reads in the report, the claims it supports, how a build spec or share link reruns it, and
the dataset files that make it out of date.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from latris.operations.formalisms import Analysis, ChatTool, ResultKind, register_analysis


def _render(p: dict[str, Any]) -> list[str]:
    from latris.exporters import md
    from latris.operations.impact import describe

    e = p["effect"]
    out = [md.esc(describe(p)) + ".", ""]
    if p["method"] == "its":
        rows = [[name, md.fmt(c["estimate"]), f"{md.fmt(c['ci_low'])} – {md.fmt(c['ci_high'])}", md.fmt(c["p"])]
                for name, c in (("Trend before (per period)", p["pre_trend"]),
                                ("Step at the start", p["level_change"]),
                                ("Change of slope (per period)", p["slope_change"]),
                                ("Effect by the last period", e))]
        out += md.table(["", "Estimate", "95% CI", "p"], rows)
        out += [f"Projected without the intervention, {p['outcome']} would have been {md.fmt(p['counterfactual_end'])} "
                f"at the last period. Standard errors: {p['se_type']}.", ""]
    else:
        m = p["means"]
        rows = [["Treated", md.fmt(m["treated_before"]), md.fmt(m["treated_after"]),
                 md.fmt(m["treated_after"] - m["treated_before"])],
                ["Comparison", md.fmt(m["comparison_before"]), md.fmt(m["comparison_after"]),
                 md.fmt(m["comparison_after"] - m["comparison_before"])]]
        out += md.table(["Group", "Before", "After", "Change"], rows)
        pt = p["pre_trend_difference"]
        trend = (f"Before the start the groups' trends differed by {md.fmt(pt['estimate'])} per period (p = "
                 f"{md.fmt(pt['p'])})." if pt.get("testable") else "Parallel pre-trends couldn't be checked.")
        out += [f"Difference-in-differences {md.fmt(e['estimate'])} "
                f"(95% CI {md.fmt(e['ci_low'])} – {md.fmt(e['ci_high'])}, "
                f"p = {md.fmt(e['p'])}); {p['se_type']} standard errors. {trend}", ""]
    if p["warnings"]:
        out += ["Cautions: " + md.esc("; ".join(p["warnings"])) + ".", ""]
    out += ["This is the intervention's impact only if: " + " ".join(p["assumptions"]), ""]
    return out


def _charts(p: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    if p["method"] == "its":
        return [("impact-its", {})] if p.get("series") else []
    return [("impact-did", {})]


def _claims(p: dict[str, Any], out: dict[str, list[str]]) -> None:
    from latris.operations.impact import describe

    e = p["effect"]
    out["answer_to_question"].append(describe(p) + ".")
    if e["ci_low"] <= 0 <= e["ci_high"]:
        out["confidence_assessment"].append(
            f"The 95% interval for the impact on {p['outcome']} includes no change."
        )
    design = "interrupted time series" if p["method"] == "its" else "difference-in-differences"
    out["assumptions_limitations"].append(
        f"The {design} estimate for {p['outcome']} is the intervention's impact only if: "
        + " ".join(a[0].lower() + a[1:] for a in p["assumptions"][:2])
    )
    for w in p["warnings"]:
        out["open_questions"].append(f"Impact on {p['outcome']}: {w}.")


def _run(a, root: Path) -> str:
    from latris.operations import impact

    if not (a.outcome and a.dataset and a.time and a.at is not None):
        raise ValueError("an impact estimate needs outcome, dataset, time and at")
    payload = impact.estimate(a.outcome, a.dataset, time=a.time, at=a.at, group=a.group,
                              treated=a.treated or None, column=a.columns.get(a.outcome), root=root)
    return impact.record(payload, root=root)[1]


def _definition(p: dict[str, Any]):
    from latris.schema.build_spec import make_analysis

    return make_analysis(
        kind="toc_impact", outcome=p["outcome"], dataset=p["dataset"]["name"], time=p["time"], at=p["at"],
        group=p["group"], treated=p["treated"],
        columns={p["outcome"]: p["column"]} if p["column"] != p["outcome"] else {},
    )


def _fingerprint(paths) -> list[Path]:
    files = sorted(paths.data_files_dir.glob("*")) if paths.data_files_dir.exists() else []
    return [paths.data_datasets_yaml, *files]



# How a chat assistant runs each analysis (latris-app generates the tool from the manifest).
_TOOLS = {
    'toc-impact': ('estimate_impact',
        'Impact on an outcome from a registered dataset: interrupted time series, or '
        'difference-in-differences with group and treated, with validity cautions. Needs a dataset '
        '(latris data add).'),
}

register_analysis(Analysis(
    model_type="theory_of_change",
    result=ResultKind(step="analyse.estimation", tool=ChatTool(*_TOOLS['toc-impact']),
                      kind="toc-impact", title="Theory of change: impact estimate", render=_render,
                      analysis="toc_impact", run=_run, definition=_definition, claims=_claims,
                      charts=_charts, chart_kinds=("impact-its", "impact-did"), needs_dataset=True),
    fingerprint_files=_fingerprint,
))
