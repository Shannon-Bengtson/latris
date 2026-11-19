"""FCM inference as an analysis layer on the fuzzy cognitive map (``operations/fcm_inference.py``).

Not a model type: it adds the ``fcm-inference`` result to the FCM — each factor's activation at steady
state, under a scenario (factors clamped at a value) — so a run is recorded for the report, rerun from a
build spec or share link, offered as a chat tool and generated as a form in the editor, like every other
analysis. One recorded result per scenario.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from latris.operations.formalisms import Analysis, ChatTool, ResultKind, register_analysis


def _render(p: dict[str, Any]) -> list[str]:
    from latris.exporters import md
    from latris.operations.analysis import describe_fcm

    rows = [[a["label"], md.fmt(a["activation"]), "held" if a["clamped"] else ""] for a in p["activations"]]
    out = [describe_fcm(p) + ".", ""]
    out += md.table(["Factor", "Activation (0–1)", "Scenario"], rows)
    if not p["converged"]:
        out += ["It hadn't settled when the run stopped: the map may cycle; read the activations as a snapshot.", ""]
    return out


def _claims(p: dict[str, Any], out: dict[str, list[str]]) -> None:
    from latris.operations.analysis import describe_fcm

    out["answer_to_question"].append(describe_fcm(p) + ".")
    if not p["converged"]:
        out["confidence_assessment"].append(
            "The fuzzy cognitive map didn't settle to a steady state; its activations are a snapshot, not an end point."
        )
    out["assumptions_limitations"].append(
        "Fuzzy cognitive map activations are relative (0–1) and depend on the weights' signs and sizes, not "
        "measured quantities."
    )


def _run(a, root: Path) -> str:
    from latris.operations.analysis import fcm_steady_state, record_fcm

    settings = {"transfer_function": a.transfer_function, "lambda_steepness": a.lambda_steepness,
                "max_iterations": a.max_iterations}
    return record_fcm(fcm_steady_state(clamp=a.clamp, initial=a.initial, settings=settings, root=root), root=root)[1]


def _definition(p: dict[str, Any]):
    from latris.schema.build_spec import make_analysis

    return make_analysis(kind="fcm_infer", clamp=p["clamp"], initial=p["initial"], **p["settings"])


_TOOLS = {
    "fcm-inference": ("run_fcm",
        "Fuzzy cognitive map inference to a steady state: each factor's activation (0-1). clamp holds "
        "factors at a value for a scenario, e.g. {'Price': 1.0}; one recorded result per scenario."),
}

register_analysis(Analysis(
    model_type="fcm",
    result=ResultKind(tool=ChatTool(*_TOOLS["fcm-inference"]),
                      kind="fcm-inference", title="Steady state", render=_render, analysis="fcm_infer",
                      run=_run, definition=_definition, claims=_claims),
))
