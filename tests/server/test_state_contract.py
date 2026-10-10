"""State contract test — verify load_full_state() structure matches the expected shape.

This catches drift between Python models and the TypeScript FullState type.
The GUI's types/schema.ts is hand-written to mirror this structure; if the
Python side adds or removes top-level keys, this test fails.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.repo.layout import ProjectPaths
from latris.server.state import load_full_state


@pytest.fixture
def populated_project(two_node_project_root: Path) -> ProjectPaths:
    return ProjectPaths(two_node_project_root)


EXPECTED_TOP_KEYS = {
    "project",
    "substrate",
    "references",
    "challenges",
    "mappings",
    "attributes",
    "view_attributes",
    "provenance",
    "findings",
    "interpretation",
    "datasets",
    "versions",
    "lineage",
}

EXPECTED_ATTRIBUTE_KEYS = {"descriptions", "confidence", "evidence", "data_links"}

EXPECTED_PROVENANCE_KEYS = {
    "assumptions",
    "decisions",
    "signoffs",
    "sessions",
    "questions",
    "exclusions",
    "predictions",
    "review_sessions",
    "model_choices",
}

EXPECTED_LINEAGE_KEYS = {"current_node", "milestones", "current_branch"}


def test_full_state_top_level_keys(populated_project) -> None:
    state = load_full_state(populated_project)
    assert set(state.keys()) == EXPECTED_TOP_KEYS


def test_full_state_attribute_keys(populated_project) -> None:
    state = load_full_state(populated_project)
    assert set(state["attributes"].keys()) == EXPECTED_ATTRIBUTE_KEYS


def test_full_state_view_attribute_keys(populated_project) -> None:
    state = load_full_state(populated_project)
    assert "cld" in state["view_attributes"]
    assert "polarity" in state["view_attributes"]["cld"]
    assert "fcm" in state["view_attributes"]
    assert "weight" in state["view_attributes"]["fcm"]


def test_full_state_provenance_keys(populated_project) -> None:
    state = load_full_state(populated_project)
    assert set(state["provenance"].keys()) == EXPECTED_PROVENANCE_KEYS


def test_full_state_lineage_keys(populated_project) -> None:
    state = load_full_state(populated_project)
    assert set(state["lineage"].keys()) == EXPECTED_LINEAGE_KEYS


def test_substrate_has_entities_and_edges(populated_project) -> None:
    state = load_full_state(populated_project)
    sub = state["substrate"]
    assert "entities" in sub
    assert "edges" in sub
    assert len(sub["entities"]) == 2
    assert len(sub["edges"]) == 1


def test_project_has_required_fields(populated_project) -> None:
    state = load_full_state(populated_project)
    proj = state["project"]
    assert "statement" in proj
