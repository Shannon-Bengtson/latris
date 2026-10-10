from __future__ import annotations

from pathlib import Path

import pytest

from latris.diff.semantic import (
    diff_commits,
    diff_working_tree,
    read_log,
)
from latris.operations import attributes as attr_ops
from latris.operations import challenges as ch_ops
from latris.operations import edges as edge_ops
from latris.operations import evidence as evidence_ops
from latris.operations import nodes as node_ops
from latris.operations import project as project_ops
from latris.operations import provenance as prov_ops
from latris.operations import references as ref_ops
from latris.operations.init import init_project
from latris.repo import git


def _head(root: Path) -> str:
    return git.run_git(["rev-parse", "HEAD"], cwd=root).stdout.strip()


def _diff_last(root: Path):
    head = _head(root)
    return diff_commits(root, f"{head}^", head)


@pytest.fixture
def project(tmp_path: Path, git_identity):
    root = tmp_path / "demo"
    init_project(root, statement="Q?")
    return root


# ---- log ----


def test_read_log_returns_entries(project: Path, git_identity) -> None:
    node_ops.add_node("Price", root=project)
    node_ops.add_node("Demand", root=project)
    entries = read_log(project, limit=10)
    assert len(entries) == 3  # init + 2 nodes
    # Most recent first
    assert 'Added node "Demand"' in entries[0]["subject"]
    assert entries[0]["author"] == git_identity[0]


# ---- project ----


def test_diff_captures_project_statement_change(project: Path) -> None:
    project_ops.set_question(project, "A completely new framing?")
    events = _diff_last(project)
    kinds = {e.kind for e in events}
    assert "project_statement_changed" in kinds


# ---- substrate ----


def test_diff_node_added(project: Path) -> None:
    node_ops.add_node("Price", kind="variable", root=project)
    events = _diff_last(project)
    assert any(e.kind == "node_added" and "Price" in e.summary for e in events)


def test_diff_node_renamed(project: Path) -> None:
    entity, _ = node_ops.add_node("Price", root=project)
    node_ops.rename_node(entity.id, "Retail price", root=project)
    events = _diff_last(project)
    assert any(e.kind == "node_renamed" and "Price" in e.summary and "Retail price" in e.summary for e in events)


def test_diff_node_removed_cascades_edges(project: Path) -> None:
    a, _ = node_ops.add_node("A", root=project)
    b, _ = node_ops.add_node("B", root=project)
    edge_ops.add_edge(a.id, b.id, root=project)
    node_ops.remove_node(a.id, root=project)
    events = _diff_last(project)
    kinds = {e.kind for e in events}
    assert "node_removed" in kinds
    assert "edge_removed" in kinds


def test_diff_edge_added_and_kind_change(project: Path) -> None:
    a, _ = node_ops.add_node("A", root=project)
    b, _ = node_ops.add_node("B", root=project)
    edge, _ = edge_ops.add_edge(a.id, b.id, kind="causal", root=project)
    events_added = _diff_last(project)
    assert any(e.kind == "edge_added" and "causal" in e.summary for e in events_added)


# ---- attributes ----


def test_diff_attribute_set(project: Path) -> None:
    a, _ = node_ops.add_node("A", root=project)
    attr_ops.set_attribute(a.id, "description", "Hello world", root=project)
    events = _diff_last(project)
    assert any(e.kind == "attribute_set" and "description" in e.summary for e in events)


def test_diff_attribute_value_changed(project: Path) -> None:
    a, _ = node_ops.add_node("A", root=project)
    attr_ops.set_attribute(a.id, "description", "first", root=project)
    attr_ops.set_attribute(a.id, "description", "second", root=project)
    events = _diff_last(project)
    assert any(e.kind == "attribute_changed" and "first" in e.summary and "second" in e.summary for e in events)


def test_diff_maturity_change(project: Path) -> None:
    """Maturity now sits on the parent Entity/Edge — diff records
    `node_maturity_changed`, not per-attribute changes.
    """
    from latris.operations import maturity as maturity_ops

    a, _ = node_ops.add_node("A", root=project)
    attr_ops.set_attribute(a.id, "description", "d", root=project)
    maturity_ops.mark_reviewed(a.id, root=project)
    events = _diff_last(project)
    assert any(e.kind == "node_maturity_changed" and "reviewed" in e.summary for e in events)


# ---- evidence ----


def test_diff_evidence_attached(project: Path) -> None:
    a, _ = node_ops.add_node("A", root=project)
    attr_ops.set_attribute(a.id, "description", "d", root=project)
    ref_ops.add_reference("smith2023", title="X", root=project)
    evidence_ops.add_evidence(a.id, "description", "smith2023", root=project)
    events = _diff_last(project)
    assert any(e.kind == "evidence_attached" for e in events)


# ---- challenges ----


def test_diff_challenge_opened(project: Path) -> None:
    a, _ = node_ops.add_node("A", root=project)
    b, _ = node_ops.add_node("B", root=project)
    edge, _ = edge_ops.add_edge(a.id, b.id, root=project)
    ch_ops.open_challenge(edge.id, "arguable", root=project)
    events = _diff_last(project)
    assert any(e.kind == "challenge_opened" for e in events)


def test_diff_challenge_resolved_shows_transition(project: Path) -> None:
    a, _ = node_ops.add_node("A", root=project)
    b, _ = node_ops.add_node("B", root=project)
    edge, _ = edge_ops.add_edge(a.id, b.id, root=project)
    ch, _ = ch_ops.open_challenge(edge.id, "arg", root=project)
    ch_ops.resolve_challenge(ch.id, "modified", root=project)
    events = _diff_last(project)
    resolved = [e for e in events if e.kind == "challenge_resolved"]
    assert len(resolved) == 1
    assert "open" in resolved[0].summary
    assert "modified" in resolved[0].summary


# ---- provenance ----


def test_diff_assumption_added(project: Path) -> None:
    prov_ops.add_assumption("Market liquid", rationale="norm", root=project)
    events = _diff_last(project)
    assert any(e.kind == "assumption_added" for e in events)


def test_diff_prediction_added(project: Path) -> None:
    prov_ops.add_prediction("Demand falls 8%", horizon="6 months", root=project)
    events = _diff_last(project)
    assert any(e.kind == "prediction_added" for e in events)


# ---- references ----


def test_diff_reference_added(project: Path) -> None:
    ref_ops.add_reference("smith2023", title="A title", root=project)
    events = _diff_last(project)
    assert any(e.kind == "reference_added" and "smith2023" in e.summary for e in events)


# ---- working tree ----


def test_diff_working_tree_clean_after_init(project: Path) -> None:
    assert diff_working_tree(project) == []


def test_diff_working_tree_picks_up_manual_edits(project: Path) -> None:
    node_ops.add_node("A", root=project)
    conceptual = project / "substrate" / "conceptual.yaml"
    # Manually corrupt the label — simulates a user editing the YAML directly.
    text = conceptual.read_text(encoding="utf-8")
    conceptual.write_text(
        text.replace("label: A", "label: Edited"),
        encoding="utf-8",
        newline="",
    )
    events = diff_working_tree(project)
    # Should surface as a node rename (same id, different label).
    assert any(e.kind == "node_renamed" for e in events)


# ---- commit range ----


def test_diff_commits_multiple_commits(project: Path) -> None:
    head0 = _head(project)
    node_ops.add_node("A", root=project)
    node_ops.add_node("B", root=project)
    node_ops.add_node("C", root=project)
    head3 = _head(project)
    events = diff_commits(project, head0, head3)
    added_names = {e.summary for e in events if e.kind == "node_added"}
    assert any('"A"' in s for s in added_names)
    assert any('"B"' in s for s in added_names)
    assert any('"C"' in s for s in added_names)
