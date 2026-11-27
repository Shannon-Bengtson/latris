"""The workflow structure: one fixed list of stages, steps and tracks (docs/engineering/WORKFLOW_STRUCTURE.md)."""

from __future__ import annotations

import pytest

from latris.schema import workflow as wf


def test_stages_in_order() -> None:
    assert wf.STAGE_IDS == ("frame", "build", "formalise", "analyse", "interpret", "communicate", "use")


def test_analyse_and_formalise_steps() -> None:
    assert wf.step_ids("analyse") == (
        "analyse.structural",
        "analyse.base_case",
        "analyse.options",
        "analyse.uncertainty",
        "analyse.sensitivity",
        "analyse.estimation",
    )
    assert wf.step_ids("formalise") == (
        "formalise.definitions",
        "formalise.values",
        "formalise.ranges",
        "formalise.scenarios",
    )


def test_tracks() -> None:
    assert wf.TRACK_IDS == ("ai", "evidence", "data", "review", "validation", "versions", "project")


def test_ids_are_unique_and_steps_belong_to_their_stage() -> None:
    every = list(wf.STAGE_IDS) + list(wf.TRACK_IDS) + list(wf.step_ids()) + [wf.COMPOSITE]
    assert len(every) == len(set(every))
    for s in wf.stages():
        assert s.steps, f"{s.id} has no steps"
        for st in s.steps:
            assert st.id.startswith(f"{s.id}.")
            assert wf.stage_of(st.id) == s.id


def test_names_and_descriptions_are_written() -> None:
    for item in [*wf.stages(), *wf.TRACKS, *(st for s in wf.stages() for st in s.steps)]:
        assert item.name and item.description.endswith(".")


@pytest.mark.parametrize("place", ["analyse.uncertainty", "analyse", "evidence", "composite"])
def test_is_place(place: str) -> None:
    assert wf.is_place(place)


@pytest.mark.parametrize("place", ["", "analyse.monte_carlo", "uncertainty", "tracks.evidence", "Analyse"])
def test_is_not_place(place: str) -> None:
    assert not wf.is_place(place)


def test_stage_of() -> None:
    assert wf.stage_of("formalise.ranges") == "formalise"
    assert wf.stage_of("use") == "use"
    assert wf.stage_of("evidence") is None
    assert wf.stage_of(wf.COMPOSITE) is None


def test_require_step_names_the_alternatives() -> None:
    assert wf.require_step("analyse.options", "analyse") == "analyse.options"
    with pytest.raises(ValueError, match="analyse.structural"):
        wf.require_step("formalise.values", "analyse")


def test_unknown_lookups_raise() -> None:
    with pytest.raises(KeyError):
        wf.stage("review")
    with pytest.raises(KeyError):
        wf.step("analyse.evaluation")


def test_structure_round_trips() -> None:
    dumped = wf.structure().model_dump(mode="json")
    assert wf.WorkflowStructure.model_validate(dumped).model_dump(mode="json") == dumped
    assert dumped["composite"] == "composite"
    assert [s["id"] for s in dumped["stages"]] == list(wf.STAGE_IDS)


def test_stages_returns_copies() -> None:
    wf.stages()[0].steps.clear()
    assert wf.step_ids("frame")


def test_a_surface_can_add_a_step_under_a_stage() -> None:
    try:
        added = wf.register_step("communicate", "story", "Story", "A scrolling page that answers the question.")
        assert added.id == "communicate.story"
        assert wf.step_ids("communicate")[-1] == "communicate.story"
        assert wf.is_place("communicate.story")
        assert wf.register_step("communicate", "story", "Story", "A scrolling page that answers the question.")
        with pytest.raises(ValueError, match="differently"):
            wf.register_step("communicate", "story", "Stories", "Something else.")
    finally:
        wf._unregister_step("communicate.story")
    assert not wf.is_place("communicate.story")


def test_a_surface_cannot_redefine_latris_steps_or_add_stages() -> None:
    with pytest.raises(ValueError, match="own steps"):
        wf.register_step("analyse", "uncertainty", "Mine", "Mine.")
    with pytest.raises(KeyError):
        wf.register_step("present", "slides", "Slides", "Slides.")
