"""Tests for the Configure workflow: batch view-attribute setting."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import configure as configure_ops
from latris.operations.view_attributes import get_view_attributes
from latris.repo import git
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model
from latris.schema import Substrate


@pytest.fixture
def project(triangle_project_root: Path) -> Path:
    return triangle_project_root


@pytest.fixture
def three_edges(project: Path):
    """Look up the three triangle edges (A→B, B→C, C→A) by endpoint name."""
    sub = load_model(Substrate, ProjectPaths(project).conceptual_yaml)
    by_label = {n.label: n for n in sub.entities}
    a, b, c = by_label["Variable A"], by_label["Variable B"], by_label["Variable C"]
    by_endpoints = {(e.from_id, e.to_id): e for e in sub.edges}
    return by_endpoints[(a.id, b.id)], by_endpoints[(b.id, c.id)], by_endpoints[(c.id, a.id)]


# ── Happy path ──────────────────────────────────────────────────────


def test_batch_set_polarity(project: Path, three_edges) -> None:
    e1, e2, e3 = three_edges
    applied, sha = configure_ops.batch_set_view_attributes(
        model_type="cld",
        attribute="polarity",
        entries=[
            {"target_id": e1.id, "value": "+"},
            {"target_id": e2.id, "value": "-"},
            {"target_id": e3.id, "value": "+"},
        ],
        root=project,
    )
    assert len(applied) == 3
    assert len(sha) == 40

    # Verify values persisted.
    store = get_view_attributes("cld", "polarity", root=project)
    by_target = {e.target_id: e.value for e in store.entries}
    assert by_target[e1.id] == "+"
    assert by_target[e2.id] == "-"
    assert by_target[e3.id] == "+"


def test_single_commit(project: Path, three_edges) -> None:
    """Batch should produce exactly one git commit for N entries."""
    e1, e2, e3 = three_edges
    sha_before = git.head_sha(project)
    configure_ops.batch_set_view_attributes(
        model_type="cld",
        attribute="polarity",
        entries=[
            {"target_id": e1.id, "value": "+"},
            {"target_id": e2.id, "value": "-"},
        ],
        root=project,
    )
    # Count commits between sha_before and HEAD.
    result = git.run_git(
        ["log", "--oneline", f"{sha_before}..HEAD"],
        cwd=project,
    )
    log = result.stdout.strip().splitlines()
    assert len(log) == 1


def test_provenance_fields(project: Path, three_edges) -> None:
    e1, _, _ = three_edges
    configure_ops.batch_set_view_attributes(
        model_type="cld",
        attribute="polarity",
        entries=[
            {
                "target_id": e1.id,
                "value": "+",
                "origin": "ai-proposed",
                "source_detail": "SuggestEdgePolarities run",
            },
        ],
        root=project,
    )
    store = get_view_attributes("cld", "polarity", root=project)
    entry = next(e for e in store.entries if e.target_id == e1.id)
    assert entry.origin == "ai-proposed"
    assert entry.source_id == "SuggestEdgePolarities run"


def test_batch_set_fcm_weight(project: Path, three_edges) -> None:
    e1, e2, _ = three_edges
    applied, sha = configure_ops.batch_set_view_attributes(
        model_type="fcm",
        attribute="weight",
        entries=[
            {"target_id": e1.id, "value": "0.75"},
            {"target_id": e2.id, "value": "-0.3"},
        ],
        root=project,
    )
    assert len(applied) == 2
    assert len(sha) == 40

    store = get_view_attributes("fcm", "weight", root=project)
    by_target = {e.target_id: e.value for e in store.entries}
    assert by_target[e1.id] == pytest.approx(0.75)
    assert by_target[e2.id] == pytest.approx(-0.3)


# ── Validation ──────────────────────────────────────────────────────


def test_invalid_model_type(project: Path, three_edges) -> None:
    e1, _, _ = three_edges
    with pytest.raises(ValueError, match="unknown model type|Unknown model type"):
        configure_ops.batch_set_view_attributes(
            model_type="nonexistent",
            attribute="polarity",
            entries=[{"target_id": e1.id, "value": "+"}],
            root=project,
        )


def test_invalid_attribute_for_model(project: Path, three_edges) -> None:
    e1, _, _ = three_edges
    with pytest.raises(ValueError, match="not a valid attribute"):
        configure_ops.batch_set_view_attributes(
            model_type="cld",
            attribute="weight",  # weight is FCM, not CLD
            entries=[{"target_id": e1.id, "value": "0.5"}],
            root=project,
        )


def test_empty_entries(project: Path) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        configure_ops.batch_set_view_attributes(
            model_type="cld",
            attribute="polarity",
            entries=[],
            root=project,
        )


def test_invalid_polarity_value(project: Path, three_edges) -> None:
    e1, _, _ = three_edges
    with pytest.raises(ValueError, match="polarity must be"):
        configure_ops.batch_set_view_attributes(
            model_type="cld",
            attribute="polarity",
            entries=[{"target_id": e1.id, "value": "invalid"}],
            root=project,
        )


def test_upsert_overwrites(project: Path, three_edges) -> None:
    """Setting the same edge twice updates in place, not duplicates."""
    e1, _, _ = three_edges
    configure_ops.batch_set_view_attributes(
        model_type="cld",
        attribute="polarity",
        entries=[{"target_id": e1.id, "value": "+"}],
        root=project,
    )
    configure_ops.batch_set_view_attributes(
        model_type="cld",
        attribute="polarity",
        entries=[{"target_id": e1.id, "value": "-"}],
        root=project,
    )
    store = get_view_attributes("cld", "polarity", root=project)
    matching = [e for e in store.entries if e.target_id == e1.id]
    assert len(matching) == 1
    assert matching[0].value == "-"
