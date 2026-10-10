"""Tests for Story operations — draft skeleton, prose, emphasis, reorder."""

from __future__ import annotations

import pytest

from latris.ai import proposals as p
from latris.ai.adapters.base import ChatResult
from latris.ai.adapters.mock_adapter import MockAdapter
from latris.operations.commit import auto_commit
from latris.operations.edges import add_edge
from latris.operations.findings import record_new_finding
from latris.operations.init import init_project
from latris.operations.nodes import add_node
from latris.operations.story import (
    draft_story,
    generate_beat_prose,
    load_story,
    reorder_beats,
    set_beat_prose,
    set_emphasis,
)
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import dump_model, load_model
from latris.schema.project import ProjectFoundation
from latris.schema.story import StoryGenerationRequest


@pytest.fixture
def story_project(tmp_path, git_identity, monkeypatch):
    monkeypatch.setenv("LATRIS_AI_MOCK", "1")
    MockAdapter.shared().register_default(
        response_cls=p.InterpretProseResult,
        result=ChatResult(
            parsed=p.InterpretProseResult(prose="(mock) Plain-language beat prose."),
            raw="(mock)",
            model_id="mock-model",
        ),
    )
    root = tmp_path / "proj"
    init_project(root, statement="What drives water quality decline?")
    paths = ProjectPaths(root)
    foundation = load_model(ProjectFoundation, paths.project_yaml)
    foundation.selected_model_types = ["cld"]
    foundation.name = "Coastal water quality"
    dump_model(foundation, paths.project_yaml)
    auto_commit(root, subject="Select CLD", paths=[paths.project_yaml])

    a, _ = add_node("Nutrient load", kind="variable", root=root)
    b, _ = add_node("Algal bloom", kind="variable", root=root)
    e1, _ = add_edge(a.id, b.id, kind="causal", root=root)
    e2, _ = add_edge(b.id, a.id, kind="causal", root=root)  # closes the loop
    finding, _ = record_new_finding(
        "Reinforcing loop: Nutrient load to Algal bloom and back",
        category="structure",
        model_type="cld",
        payload={"node_ids": [a.id, b.id], "edge_ids": [e1.id, e2.id], "classification": "R"},
        root=root,
    )
    return root, a, b, e1, e2, finding


def _full_request() -> StoryGenerationRequest:
    return StoryGenerationRequest(
        include_sections=["key_findings", "answer_to_question", "open_questions", "implications"],
        source_report_selection=["interp_answer"],
    )


def test_draft_builds_arc_skeleton(story_project) -> None:
    root, a, b, e1, e2, finding = story_project
    doc, sha = draft_story("cld", _full_request(), root=root)
    assert sha
    kinds = [beat.kind for beat in doc.beats]
    assert kinds == ["hook", "system_tour", "answer", "uncertainty", "implication", "closing"]
    assert doc.generation_state == "drafted"
    assert doc.title == "Coastal water quality"
    # system_tour emphasis seeded from the detected loop
    tour = next(beat for beat in doc.beats if beat.kind == "system_tour")
    assert set(tour.emphasis.node_ids) == {a.id, b.id}
    assert set(tour.emphasis.edge_ids) == {e1.id, e2.id}
    assert tour.emphasis.loop_ids == [finding.id]
    # confidence beats
    assert next(x for x in doc.beats if x.kind == "answer").show_confidence
    assert next(x for x in doc.beats if x.kind == "uncertainty").show_confidence


def test_uncertainty_beat_is_always_on(story_project) -> None:
    root, *_ = story_project
    # Even with open_questions NOT ticked, the uncertainty beat survives.
    req = StoryGenerationRequest(include_sections=["answer_to_question"])
    doc, _ = draft_story("cld", req, root=root)
    assert "uncertainty" in [beat.kind for beat in doc.beats]


def test_generate_beat_prose_fills_ai_version(story_project) -> None:
    root, *_ = story_project
    doc, _ = draft_story("cld", _full_request(), root=root)
    answer = next(beat for beat in doc.beats if beat.kind == "answer")
    beat, sha = generate_beat_prose("cld", answer.id, root=root)
    assert sha
    assert beat.prose == "(mock) Plain-language beat prose."
    assert beat.prose_versions[-1].source == "ai"


def test_set_beat_prose_human_edit_versions(story_project) -> None:
    root, *_ = story_project
    doc, _ = draft_story("cld", _full_request(), root=root)
    hook = next(beat for beat in doc.beats if beat.kind == "hook")
    beat, _ = set_beat_prose("cld", hook.id, "A human-written hook.", root=root)
    assert beat.prose == "A human-written hook."
    assert beat.prose_versions[-1].source == "human-edit"
    assert load_story(root=root).docs[0].generation_state == "edited"


def test_set_emphasis_expands_loops(story_project) -> None:
    root, a, b, e1, e2, finding = story_project
    doc, _ = draft_story("cld", _full_request(), root=root)
    answer = next(beat for beat in doc.beats if beat.kind == "answer")
    beat, _ = set_emphasis("cld", answer.id, loop_ids=[finding.id], root=root)
    assert set(beat.emphasis.node_ids) == {a.id, b.id}
    assert set(beat.emphasis.edge_ids) == {e1.id, e2.id}
    assert beat.emphasis.loop_ids == [finding.id]


def test_reorder_beats(story_project) -> None:
    root, *_ = story_project
    doc, _ = draft_story("cld", _full_request(), root=root)
    reversed_ids = [beat.id for beat in reversed(doc.beats)]
    new_doc, _ = reorder_beats("cld", reversed_ids, root=root)
    assert [beat.id for beat in new_doc.beats] == reversed_ids
