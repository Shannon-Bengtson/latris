"""Tests for elicitation operations (M14)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from latris.operations import attributes as attr_ops
from latris.operations import elicitation as elicit_ops
from latris.operations import nodes as node_ops
from latris.operations.init import init_project
from latris.repo.yaml_io import load_model
from latris.schema import DescriptionSet


@pytest.fixture
def project(tmp_path: Path, git_identity, monkeypatch):
    root = tmp_path / "demo"
    init_project(root, statement="Does X cause Y?")
    a, _ = node_ops.add_node("Price", kind="variable", root=root)
    attr_ops.set_attribute(a.id, "description", "Market price", root=root)
    monkeypatch.chdir(root)
    return root, a


def test_full_lifecycle(project):
    root, a = project

    # Start
    session, _ = elicit_ops.start_session(
        "delphi",
        "Alice",
        ["Dr. Smith", "Dr. Jones"],
        [(a.id, "description")],
        held_at=date(2026, 4, 20),
        root=root,
    )
    assert session.phase == "active"
    assert session.protocol.name == "delphi"
    assert len(session.experts) == 2
    assert len(session.target_attributes) == 1

    # List
    entries = elicit_ops.list_sessions(root=root)
    assert len(entries) == 1
    assert entries[0].id == session.id

    # Get
    loaded = elicit_ops.get_session(session.id, root=root)
    assert loaded.id == session.id

    # Add round
    session, _ = elicit_ops.add_round(
        session.id,
        "Dr. Smith",
        "high confidence",
        rationale="Based on field data",
        round_num=1,
        root=root,
    )
    assert len(session.raw_responses) == 1

    session, _ = elicit_ops.add_round(
        session.id,
        "Dr. Jones",
        "medium confidence",
        round_num=1,
        root=root,
    )
    assert len(session.raw_responses) == 2

    # Aggregate
    session, _ = elicit_ops.aggregate_session(
        session.id,
        {"confidence": "high"},
        confidence_summary="Agreement between experts",
        root=root,
    )
    assert session.aggregated_result == {"confidence": "high"}
    assert session.confidence_summary == "Agreement between experts"

    # Finalise
    session, _ = elicit_ops.finalise_session(session.id, root=root)
    assert session.phase == "finalised"


def test_finalise_sets_provenance_on_attributes(project):
    root, a = project

    session, _ = elicit_ops.start_session(
        "direct",
        "Alice",
        ["Expert"],
        [(a.id, "description")],
        root=root,
    )
    elicit_ops.add_round(session.id, "Expert", "updated view", root=root)
    elicit_ops.aggregate_session(session.id, {"value": "updated"}, root=root)
    elicit_ops.finalise_session(session.id, root=root)

    # Check provenance was set on the description attribute
    from latris.repo.layout import ProjectPaths

    paths = ProjectPaths(root)
    desc_set = load_model(DescriptionSet, paths.descriptions_yaml)
    entry = next(e for e in desc_set.entries if e.target_id == a.id)
    assert entry.origin == "human-elicited"
    assert entry.verification == "human-verified"
    assert entry.source_id == session.id


def test_cannot_add_round_to_finalised(project):
    root, a = project
    session, _ = elicit_ops.start_session(
        "direct",
        "Alice",
        ["Expert"],
        [(a.id, "description")],
        root=root,
    )
    elicit_ops.finalise_session(session.id, root=root)

    with pytest.raises(ValueError, match="finalised"):
        elicit_ops.add_round(session.id, "Expert", "late input", root=root)


def test_cannot_finalise_twice(project):
    root, a = project
    session, _ = elicit_ops.start_session(
        "direct",
        "Alice",
        ["Expert"],
        [(a.id, "description")],
        root=root,
    )
    elicit_ops.finalise_session(session.id, root=root)

    with pytest.raises(ValueError, match="already finalised"):
        elicit_ops.finalise_session(session.id, root=root)


def test_session_file_created_at_correct_path(project):
    root, a = project
    session, _ = elicit_ops.start_session(
        "shelf",
        "Alice",
        ["Expert"],
        [(a.id, "confidence")],
        held_at=date(2026, 5, 1),
        root=root,
    )
    from latris.repo.layout import ProjectPaths

    paths = ProjectPaths(root)

    entries = elicit_ops.list_sessions(root=root)
    session_path = paths.root / entries[0].file_path
    assert session_path.exists()
    assert "shelf" in session_path.name
    assert "2026-05-01" in session_path.name
