"""Round-trip and default tests for the Story schema."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from latris.repo.yaml_io import dump_model, load_model
from latris.schema.ids import new_id, parse_id
from latris.schema.interpretation import InterpretTextVersion
from latris.schema.story import (
    StoryBeat,
    StoryBrand,
    StoryDoc,
    StoryEmphasis,
    StoryGenerationRequest,
    StoryImage,
    StoryStore,
)


def _sample_store() -> StoryStore:
    beat = StoryBeat(
        id=new_id("story-beat"),
        kind="answer",
        title="What we found",
        prose="In plain terms, nutrient load drives algal blooms.",
        prose_versions=[
            InterpretTextVersion(version_id=new_id("version"), text="draft", source="ai", model_commit="abc"),
        ],
        emphasis=StoryEmphasis(node_ids=["node_x"], edge_ids=["edge_y"], loop_ids=["finding_z"]),
        show_confidence=True,
        source_section="answer_to_question",
    )
    doc = StoryDoc(
        id=new_id("story"),
        model_type="cld",
        title="Coastal water quality",
        standfirst="Why the bay keeps turning green",
        title_image=StoryImage(asset_id=new_id("story-asset"), alt="The bay", caption="Algal bloom, 2025"),
        brand=StoryBrand(accent="#2a6b5e"),
        request=StoryGenerationRequest(
            include_sections=["answer_to_question", "open_questions"],
            source_report_selection=["interp_answer"],
            drafted_at_commit="abc123",
        ),
        beats=[beat],
        source_commit="abc123",
        generation_state="drafted",
    )
    return StoryStore(docs=[doc])


def test_story_roundtrip(tmp_path: Path) -> None:
    store = _sample_store()
    path = tmp_path / "story.yaml"
    dump_model(store, path)
    reloaded = load_model(StoryStore, path)
    assert reloaded == store


def test_empty_story_defaults() -> None:
    doc = StoryDoc(id=new_id("story"), model_type="cld")
    assert doc.beats == []
    assert doc.tone == "public"
    assert doc.generation_state == "empty"
    assert doc.theme == "default"
    assert doc.title_image is None


def test_id_kinds_are_registered() -> None:
    # New ID kinds must parse without error.
    assert parse_id(new_id("story"))[0] == "story"
    assert parse_id(new_id("story-beat"))[0] == "story-beat"
    assert parse_id(new_id("story-asset"))[0] == "story-asset"


def test_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        StoryEmphasis(node_ids=[], bogus=1)  # type: ignore[call-arg]
