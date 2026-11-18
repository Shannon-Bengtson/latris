"""Effect estimation as an analysis layer on the DAG (``operations/estimation.py``).

Not a model type: it adds the ``dag-estimate`` result to the existing DAG — how it reads in the report,
the claims it supports, how a build spec or share link reruns it, and the dataset files that make an
estimate out of date when they change.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from latris.operations.formalisms import Analysis, ResultKind, register_analysis


def _render(p: dict[str, Any]) -> list[str]:
    from latris.exporters.results import _f, _table
    from latris.operations.estimation import describe

    e, u = p["effect"], p["unadjusted"]
    logistic = p["model"] == "logistic"
    out = [describe(p) + ".", ""]
    how = "the smallest valid backdoor set the dataset measures" if p["adjustment_how"] != "given" else "as given"
    adj = ", ".join(p["adjustment"]) or "nothing (no backdoor path)"
    out += [f"Adjusted for {adj} — {how}. Model: {p['model']} regression, {p['se_type']} standard errors; "
            f"{p['n']} complete rows from {p['dataset']['name']}.", ""]
    if logistic:
        rows = [["Adjusted", _f(e["odds_ratio"]), f"{_f(e['or_ci_low'])} – {_f(e['or_ci_high'])}", _f(e["p"])],
                ["Unadjusted", _f(u["odds_ratio"]), f"{_f(u['or_ci_low'])} – {_f(u['or_ci_high'])}", _f(u["p"])]]
        out += _table(["", "Odds ratio", "95% CI", "p"], rows)
    else:
        rows = [["Adjusted", _f(e["estimate"]), f"{_f(e['ci_low'])} – {_f(e['ci_high'])}", _f(e["p"])],
                ["Unadjusted", _f(u["estimate"]), f"{_f(u['ci_low'])} – {_f(u['ci_high'])}", _f(u["p"])]]
        out += _table(["", f"Change in {p['outcome']} per unit of {p['treatment']}", "95% CI", "p"], rows)
    if p["coding"]:
        out += ["Coded as 0/1: " + "; ".join(f"{k}: {v['0']} = 0, {v['1']} = 1" for k, v in p["coding"].items())
                + ".", ""]
    if p["warnings"]:
        out += ["Cautions: " + "; ".join(p["warnings"]) + ".", ""]
    out += ["This is the effect only if: " + " ".join(p["assumptions"]), ""]
    return out


def _charts(p: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [("estimate-forest", {})]


def _claims(p: dict[str, Any], out: dict[str, list[str]]) -> None:
    from latris.operations.estimation import describe

    out["answer_to_question"].append(describe(p) + ".")
    e, u = p["effect"], p["unadjusted"]
    if p["adjustment"] and abs(u["estimate"]) > 0:
        shift = (e["estimate"] - u["estimate"]) / abs(u["estimate"])
        if abs(shift) >= 0.1:
            out["answer_to_question"].append(
                f"Adjusting for {', '.join(p['adjustment'])} moved the estimate {abs(shift):.0%} "
                f"({'down' if shift < 0 else 'up'}) from the unadjusted association."
            )
    if e["ci_low"] <= 0 <= e["ci_high"]:
        out["confidence_assessment"].append(
            f"The 95% interval for the effect of {p['treatment']} on {p['outcome']} includes no effect."
        )
    out["assumptions_limitations"].append(
        f"The estimate of {p['treatment']} → {p['outcome']} is causal only if the DAG leaves out no common cause, "
        f"the {p['model']} model's form is right, and every unit could receive every treatment level."
    )
    for w in p["warnings"]:
        out["open_questions"].append(f"Estimate of {p['treatment']} → {p['outcome']}: {w}.")


def _run(a, root: Path) -> str:
    from latris.operations import estimation

    if not (a.treatment and a.outcome and a.dataset):
        raise ValueError("an effect estimate needs treatment, outcome and dataset")
    payload = estimation.estimate(a.treatment, a.outcome, a.dataset, adjust=a.adjust or None,
                                  columns=a.columns or None, estimator=a.estimator or "auto", root=root)
    return estimation.record(payload, root=root)[1]


def _definition(p: dict[str, Any]):
    from latris.schema.build_spec import make_analysis

    return make_analysis(
        kind="dag_estimate", treatment=p["treatment"], outcome=p["outcome"], dataset=p["dataset"]["name"],
        adjust=p["adjustment"] if p["adjustment_how"] == "given" else [],
        columns={k: v for k, v in p["columns"].items() if v != k}, estimator=p["model"],
    )


def _fingerprint(paths) -> list[Path]:
    # An estimate goes out of date when the data it was fitted to changes.
    files = sorted(paths.data_files_dir.glob("*")) if paths.data_files_dir.exists() else []
    return [paths.data_datasets_yaml, *files]


register_analysis(Analysis(
    model_type="dag",
    result=ResultKind(kind="dag-estimate", title="Effect estimate", render=_render, analysis="dag_estimate",
                      run=_run, definition=_definition, claims=_claims, charts=_charts,
                      chart_kinds=("estimate-forest",), needs_dataset=True),
    fingerprint_files=_fingerprint,
))
