"""Tests for mapping registry operations (M13)."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import edges as edge_ops
from latris.operations import mappings as mapping_ops
from latris.operations import nodes as node_ops
from latris.operations.init import init_project


@pytest.fixture
def project(tmp_path: Path, git_identity, monkeypatch):
    root = tmp_path / "demo"
    init_project(root, statement="Does X cause Y?")
    a, _ = node_ops.add_node("Price", kind="variable", root=root)
    b, _ = node_ops.add_node("Demand", kind="variable", root=root)
    edge, _ = edge_ops.add_edge(a.id, b.id, kind="causal", root=root)
    monkeypatch.chdir(root)
    return root, a, b, edge


def test_map_and_list(project):
    root, a, b, edge = project
    mapping_ops.map_to_view(a.id, "cld", root=root)
    mapping_ops.map_to_view(b.id, "cld", root=root)
    mapping_ops.map_to_view(edge.id, "cld", root=root)

    all_mappings = mapping_ops.list_mappings(root=root)
    assert len(all_mappings) == 3

    cld_only = mapping_ops.list_mappings("cld", root=root)
    assert len(cld_only) == 3

    dag_only = mapping_ops.list_mappings("dag", root=root)
    assert len(dag_only) == 0


def test_map_duplicate_raises(project):
    root, a, _, _ = project
    mapping_ops.map_to_view(a.id, "cld", root=root)
    with pytest.raises(ValueError, match="already mapped"):
        mapping_ops.map_to_view(a.id, "cld", root=root)


def test_leave_out_keeps_it_out_and_mapping_puts_it_back(project):
    from latris.operations.views import auto_project

    root, a, _, _ = project
    auto_project("cld", root=root)
    assert a.id in {m.l2_id for m in mapping_ops.list_mappings("cld", root=root)}

    mapping_ops.leave_out(a.id, "cld", reason="Not part of the loop story", root=root)
    assert a.id not in {m.l2_id for m in mapping_ops.list_mappings("cld", root=root)}
    auto_project("cld", root=root)  # what the app does when the type is opened
    assert a.id not in {m.l2_id for m in mapping_ops.list_mappings("cld", root=root)}
    [left] = mapping_ops.list_left_out("cld", root=root)
    assert left.l2_id == a.id and left.reason == "Not part of the loop story"

    mapping_ops.map_to_view(a.id, "cld", root=root)
    assert mapping_ops.list_left_out("cld", root=root) == []
    assert a.id in {m.l2_id for m in mapping_ops.list_mappings("cld", root=root)}


def test_leave_out_twice_raises(project):
    root, a, _, _ = project
    mapping_ops.leave_out(a.id, "cld", root=root)
    with pytest.raises(ValueError, match="already left out"):
        mapping_ops.leave_out(a.id, "cld", root=root)


def test_a_left_out_factor_takes_its_links_out_of_the_view(project):
    from latris.operations.views import auto_project, project_view

    root, a, _, _ = project
    auto_project("cld", root=root)
    mapping_ops.leave_out(a.id, "cld", root=root)
    view = project_view("cld", root=root)
    assert a.id not in view.entity_ids
    from latris.operations.edges import list_edges

    touching = {e.id for e in list_edges(root=root) if a.id in (e.from_id, e.to_id)}
    assert touching and not touching & set(view.edge_ids)


def test_removing_a_factor_clears_what_was_left_out(project):
    from latris.operations.nodes import remove_node

    root, a, _, _ = project
    mapping_ops.leave_out(a.id, "cld", root=root)
    remove_node(a.id, root=root)
    assert mapping_ops.list_left_out(root=root) == []


def test_approve_mapping(project):
    root, a, _, _ = project
    mapping_ops.map_to_view(a.id, "cld", ai_proposed=True, root=root)
    mappings = mapping_ops.list_mappings("cld", root=root)
    assert mappings[0].origin == "ai-proposed"
    assert mappings[0].maturity == "proposed"

    mapping_ops.approve_mapping(a.id, "cld", root=root)
    mappings = mapping_ops.list_mappings("cld", root=root)
    assert mappings[0].maturity == "approved"


def test_map_by_label(project):
    root, _, _, _ = project
    mapping_ops.map_to_view("Price", "dag", root=root)
    mappings = mapping_ops.list_mappings("dag", root=root)
    assert len(mappings) == 1


def test_map_nonexistent_raises(project):
    root, _, _, _ = project
    with pytest.raises(ValueError):
        mapping_ops.map_to_view("nonexistent_id_12345", "cld", root=root)


def test_the_diff_says_what_was_left_out_and_put_back(project):
    from latris.diff.semantic import diff_commits
    from latris.repo import git

    root, a, _, _ = project
    mapping_ops.map_to_view(a.id, "cld", root=root)
    before = git.head_sha(root)
    mapping_ops.leave_out(a.id, "cld", reason="Not in the loops", root=root)
    [left] = [e for e in diff_commits(root, before, git.head_sha(root)) if e.kind == "left_out_of_view"]
    assert left.target_id == a.id and left.change == "changed" and "Not in the loops" in left.summary
    middle = git.head_sha(root)
    mapping_ops.map_to_view(a.id, "cld", root=root)
    kinds = {e.kind for e in diff_commits(root, middle, git.head_sha(root))}
    assert "put_back_in_view" in kinds
