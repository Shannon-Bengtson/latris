"""Tests for the state loader (server/state.py).

The GUI hydrates its entire zustand store from ``load_full_state()``.
These tests verify the shape of the returned dict, graceful defaults
for missing optional files, and JSON-serialisability.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations.init import init_project
from latris.operations.references import add_reference
from latris.repo.layout import ProjectPaths
from latris.server.state import load_full_state


@pytest.fixture
def project(tmp_path: Path, git_identity) -> Path:
    root = tmp_path / "proj"
    init_project(root, statement="Test?")
    return root


@pytest.fixture
def paths(project: Path) -> ProjectPaths:
    return ProjectPaths(project)


# ── Shape of freshly-init'd project ────────────────────────────────


def test_fresh_project_has_expected_keys(paths: ProjectPaths) -> None:
    state = load_full_state(paths)
    expected_keys = {
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
    assert set(state.keys()) == expected_keys


def test_fresh_project_substrate_is_empty(paths: ProjectPaths) -> None:
    state = load_full_state(paths)
    assert state["substrate"]["entities"] == []
    assert state["substrate"]["edges"] == []


def test_fresh_project_provenance_sections(paths: ProjectPaths) -> None:
    state = load_full_state(paths)
    provenance = state["provenance"]
    for section in ("assumptions", "decisions", "signoffs", "sessions", "questions", "exclusions", "predictions"):
        assert section in provenance


def test_fresh_project_lineage_has_branch(paths: ProjectPaths) -> None:
    state = load_full_state(paths)
    assert "current_branch" in state["lineage"]
    assert isinstance(state["lineage"]["current_branch"], str)


# ── After adding data ──────────────────────────────────────────────


def test_nodes_appear_in_substrate(project: Path, paths: ProjectPaths) -> None:
    node_ops.add_node("Price", root=project)
    node_ops.add_node("Demand", root=project)
    state = load_full_state(paths)
    labels = [e["label"] for e in state["substrate"]["entities"]]
    assert "Price" in labels
    assert "Demand" in labels


def test_edges_appear_in_substrate(project: Path, paths: ProjectPaths) -> None:
    a, _ = node_ops.add_node("A", root=project)
    b, _ = node_ops.add_node("B", root=project)
    edge_ops.add_edge(a.id, b.id, root=project)
    state = load_full_state(paths)
    assert len(state["substrate"]["edges"]) == 1


def test_references_appear(project: Path, paths: ProjectPaths) -> None:
    add_reference("smith2020", "Smith Paper", root=project)
    state = load_full_state(paths)
    bibkeys = [r["bibkey"] for r in state["references"]["entries"]]
    assert "smith2020" in bibkeys


# ── Missing optional files → graceful defaults ─────────────────────


def test_missing_datasets_returns_empty(paths: ProjectPaths) -> None:
    """Dataset files don't exist on a fresh project — should return empty."""
    state = load_full_state(paths)
    assert state["datasets"]["entries"] == []


def test_missing_lineage_node_returns_none(paths: ProjectPaths) -> None:
    state = load_full_state(paths)
    assert state["lineage"]["current_node"] is None


def test_missing_interpretation_returns_empty_sections(paths: ProjectPaths) -> None:
    state = load_full_state(paths)
    assert state["interpretation"]["sections"] == []


# ── JSON-serialisable ───────────────────────────────────────────────


def test_full_state_is_json_serialisable(project: Path, paths: ProjectPaths) -> None:
    """The GUI receives this as JSON — it must serialise without error."""
    node_ops.add_node("X", root=project)
    state = load_full_state(paths)
    # json.dumps will raise TypeError if anything isn't serialisable
    serialised = json.dumps(state)
    assert isinstance(serialised, str)
    assert len(serialised) > 100
