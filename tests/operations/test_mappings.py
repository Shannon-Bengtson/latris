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


def test_unmap(project):
    root, a, _, _ = project
    mapping_ops.map_to_view(a.id, "cld", root=root)
    assert len(mapping_ops.list_mappings("cld", root=root)) == 1

    mapping_ops.unmap_from_view(a.id, "cld", root=root)
    assert len(mapping_ops.list_mappings("cld", root=root)) == 0


def test_unmap_nonexistent_raises(project):
    root, a, _, _ = project
    with pytest.raises(ValueError, match="not mapped"):
        mapping_ops.unmap_from_view(a.id, "cld", root=root)


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
