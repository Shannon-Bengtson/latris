"""Tests for view projection operations (M13)."""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from latris.operations import edges as edge_ops
from latris.operations import mappings as mapping_ops
from latris.operations import nodes as node_ops
from latris.operations import view_attributes as view_attr_ops
from latris.operations import views as view_ops
from latris.operations.init import init_project
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model


@pytest.fixture
def project(tmp_path: Path, git_identity, monkeypatch):
    root = tmp_path / "demo"
    init_project(root, statement="Does X cause Y?")
    a, _ = node_ops.add_node("Price", kind="variable", root=root)
    b, _ = node_ops.add_node("Demand", kind="variable", root=root)
    c, _ = node_ops.add_node("Revenue", kind="variable", root=root)
    e1, _ = edge_ops.add_edge(a.id, b.id, kind="causal", root=root)
    e2, _ = edge_ops.add_edge(b.id, c.id, kind="causal", root=root)
    monkeypatch.chdir(root)
    return root, a, b, c, e1, e2


def test_auto_project_maps_all(project):
    root, a, b, c, e1, e2 = project
    # Set polarity on both edges so CLD auto-project succeeds
    view_attr_ops.set_view_attribute(e1.id, "cld", "polarity", "+", root=root)
    view_attr_ops.set_view_attribute(e2.id, "cld", "polarity", "-", root=root)
    created = view_ops.auto_project("cld", root=root)
    # 3 nodes + 2 edges = 5 mappings
    assert len(created) == 5

    paths = ProjectPaths(root)
    from latris.schema import View

    view = load_model(View, paths.view_yaml("cld"))
    assert len(view.entity_ids) == 3
    assert len(view.edge_ids) == 2


def test_project_view_from_mappings(project):
    root, a, b, _, e1, _ = project
    mapping_ops.map_to_view(a.id, "dag", root=root)
    mapping_ops.map_to_view(b.id, "dag", root=root)
    mapping_ops.map_to_view(e1.id, "dag", root=root)

    view = view_ops.project_view("dag", root=root)
    assert len(view.entity_ids) == 2
    assert len(view.edge_ids) == 1
    assert a.id in view.entity_ids
    assert b.id in view.entity_ids
    assert e1.id in view.edge_ids


def test_dag_acyclicity_passes_for_acyclic(project):
    root, a, b, c, e1, e2 = project
    # a→b→c is acyclic
    mapping_ops.map_to_view(a.id, "dag", root=root)
    mapping_ops.map_to_view(b.id, "dag", root=root)
    mapping_ops.map_to_view(c.id, "dag", root=root)
    mapping_ops.map_to_view(e1.id, "dag", root=root)
    mapping_ops.map_to_view(e2.id, "dag", root=root)

    # Should not raise
    view = view_ops.project_view("dag", root=root)
    assert len(view.entity_ids) == 3


def test_dag_acyclicity_raises_for_cycle(project):
    root, a, b, c, e1, e2 = project
    # Add c→a to create a cycle: a→b→c→a
    e3, _ = edge_ops.add_edge(c.id, a.id, kind="causal", root=root)

    mapping_ops.map_to_view(a.id, "dag", root=root)
    mapping_ops.map_to_view(b.id, "dag", root=root)
    mapping_ops.map_to_view(c.id, "dag", root=root)
    mapping_ops.map_to_view(e1.id, "dag", root=root)
    mapping_ops.map_to_view(e2.id, "dag", root=root)
    mapping_ops.map_to_view(e3.id, "dag", root=root)

    with pytest.raises(ValueError, match="cycle"):
        view_ops.project_view("dag", root=root)


def test_cld_polarity_warning(project):
    root, a, b, _, e1, _ = project
    # Map edge without polarity set
    mapping_ops.map_to_view(a.id, "cld", root=root)
    mapping_ops.map_to_view(b.id, "cld", root=root)
    mapping_ops.map_to_view(e1.id, "cld", root=root)

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        view_ops.project_view("cld", root=root)
        assert len(w) == 1
        assert "missing polarity" in str(w[0].message).lower()


def test_cld_no_warning_when_polarity_set(project):
    root, a, b, _, e1, _ = project
    view_attr_ops.set_view_attribute(e1.id, "cld", "polarity", "-", root=root)
    mapping_ops.map_to_view(a.id, "cld", root=root)
    mapping_ops.map_to_view(b.id, "cld", root=root)
    mapping_ops.map_to_view(e1.id, "cld", root=root)

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        view_ops.project_view("cld", root=root)
        polarity_warnings = [x for x in w if "polarity" in str(x.message).lower()]
        assert len(polarity_warnings) == 0


def test_unknown_view_kind_raises(project):
    root, _, _, _, _, _ = project
    with pytest.raises(ValueError, match="Unknown model type"):
        view_ops.project_view("invalid", root=root)
