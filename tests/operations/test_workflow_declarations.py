"""Every analysis and edit operation declares its place in the workflow (schema/workflow.py), by the rules
in docs/engineering/WORKFLOW_STRUCTURE.md. Construction refuses one without a valid step; these tests pin the
classification so a change to it is deliberate."""

from __future__ import annotations

from collections import Counter

import pytest

from latris.operations import formalisms
from latris.operations.capabilities import analysis_catalog, build_capability_manifest, build_surface_manifest
from latris.operations.formalisms import ChatOp, ResultKind
from latris.schema import workflow as wf


def _ops() -> list[ChatOp]:
    return [o for f in formalisms.all_formalisms() for o in (f.chat_ops or ())]


def test_every_result_kind_is_in_an_analyse_step() -> None:
    kinds = formalisms.result_kinds()
    assert kinds
    assert {k.step for k in kinds} <= set(wf.step_ids("analyse"))


def test_every_chat_op_is_in_a_formalise_step() -> None:
    ops = _ops()
    assert ops
    assert {o.step for o in ops} <= set(wf.step_ids("formalise"))


def test_analysis_classification() -> None:
    by_step = Counter(k.step for k in formalisms.result_kinds())
    assert by_step == {
        "analyse.structural": 1,
        "analyse.base_case": 12,
        "analyse.options": 5,
        "analyse.uncertainty": 8,
        "analyse.sensitivity": 10,
        "analyse.estimation": 2,
    }


@pytest.mark.parametrize(
    ("kind", "step"),
    [
        ("toc-pathways", "analyse.structural"),  # reads no values
        ("sd-loops", "analyse.base_case"),  # computes from equations: not structural
        ("toc-process-trace", "analyse.base_case"),  # computes from priors and tests
        ("ach-analysis", "analyse.base_case"),  # hypotheses aren't options a person chooses
        ("mcda-analysis", "analyse.options"),
        ("markov-analysis", "analyse.options"),
        ("dt-psa", "analyse.uncertainty"),  # samples inputs together: uncertainty, despite its name
        ("bn-gsa", "analyse.sensitivity"),
        ("eq-sweep", "analyse.sensitivity"),
        ("dag-estimate", "analyse.estimation"),
    ],
)
def test_rules_applied_to_borderline_analyses(kind: str, step: str) -> None:
    found = formalisms.result_kind(kind)
    assert found is not None
    assert found[1].step == step


def test_operation_classification() -> None:
    assert Counter(o.step for o in _ops()) == {
        "formalise.definitions": 20,
        "formalise.values": 23,
        "formalise.ranges": 11,
        "formalise.scenarios": 3,
    }


@pytest.mark.parametrize(
    ("name", "step"),
    [
        ("set_sd_settings", "formalise.definitions"),  # model-wide setting
        ("set_mcda_criterion", "formalise.values"),  # direction and weight: a weight is a quantity
        ("set_dt_branch", "formalise.values"),  # label and probability
        ("set_toc_test", "formalise.values"),
        ("set_argument_claim", "formalise.values"),  # an assessment on one claim
        ("set_dt_correlation", "formalise.ranges"),
        ("set_bn_scenario", "formalise.scenarios"),
    ],
)
def test_rules_applied_to_borderline_operations(name: str, step: str) -> None:
    assert next(o for o in _ops() if o.name == name).step == step


def test_construction_refuses_a_missing_or_wrong_step() -> None:
    with pytest.raises(ValueError, match="not a step of analyse"):
        ResultKind(
            kind="x", title="x", render=lambda p: [], analysis="x", run=lambda s, r: "", definition=lambda p: None
        )
    with pytest.raises(ValueError, match="not a step of analyse"):
        ResultKind(
            kind="x",
            title="x",
            render=lambda p: [],
            analysis="x",
            run=lambda s, r: "",
            definition=lambda p: None,
            step="formalise.values",
        )
    with pytest.raises(ValueError, match="not a step of formalise"):
        ChatOp("analyse.uncertainty", "set_x", ("x",), "x")


def test_surfaces_receive_steps_and_the_registry() -> None:
    assert all(e["step"] in wf.step_ids("analyse") for e in analysis_catalog())
    surface = build_surface_manifest()
    assert [s["id"] for s in surface["workflow"]["stages"]] == list(wf.STAGE_IDS)
    ops = [o for t in surface["model_types"] for o in t["chat_ops"]]
    assert ops and all(o["step"] in wf.step_ids("formalise") for o in ops)
    assert build_capability_manifest()["workflow"]["tracks"][0]["id"] == "ai"


def test_readiness_transitions_use_registry_stages(empty_project_root) -> None:
    """Readiness names stages by registry id. "home" is the app's landing until it shows Frame as a stage."""
    from latris.operations.readiness import assess_transition_readiness

    phases = {
        p for t in assess_transition_readiness(root=empty_project_root).transitions for p in (t.from_phase, t.to_phase)
    }
    assert phases <= set(wf.STAGE_IDS) | {"home"}
