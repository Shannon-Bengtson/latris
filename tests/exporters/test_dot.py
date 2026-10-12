from __future__ import annotations

from pathlib import Path

import pytest

from latris.exporters import dot
from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations import view_attributes as view_attr_ops
from latris.operations.init import init_project
from latris.repo.layout import ProjectPaths


@pytest.fixture
def project_with_graph(tmp_path: Path, git_identity):
    root = tmp_path / "demo"
    init_project(root, statement="Q?")
    a, _ = node_ops.add_node("Price", kind="variable", root=root)
    b, _ = node_ops.add_node("Demand", kind="variable", root=root)
    edge, _ = edge_ops.add_edge(a.id, b.id, kind="causal", root=root)
    view_attr_ops.set_view_attribute(edge.id, "cld", "polarity", "-", root=root)
    return root, a, b, edge


def test_dot_system_map_has_digraph_and_nodes(project_with_graph) -> None:
    root, a, b, edge = project_with_graph
    out = dot.render(ProjectPaths(root), view="system_map")
    assert out.startswith("digraph ")
    assert "rankdir=LR" in out
    assert out.rstrip().endswith("}")
    assert f'"{a.id}"' in out
    assert f'"{b.id}"' in out
    assert '"Price\\n[variable]"' in out  # escaped newline-in-label
    assert f'"{a.id}" -> "{b.id}" [label="causal", id="{edge.id}"];' in out
    # Machine/intermediate format — never carries the "Made with Latris" badge.
    assert "Made with Latris" not in out


def test_dot_cld_labels_edges_with_polarity(project_with_graph) -> None:
    root, a, b, edge = project_with_graph
    out = dot.render(ProjectPaths(root), view="cld")
    assert f'"{a.id}" -> "{b.id}" [label="-", id="{edge.id}"];' in out
    # kind "causal" should NOT be a label in the cld view
    assert 'label="causal"' not in out


def test_dot_nodes_and_edges_carry_ids(project_with_graph) -> None:
    """Story emphasis needs addressable SVG ids: DOT must emit ``id=`` for
    both nodes and edges so graphviz writes ``<g class="node"/"edge" id=...>``.
    """
    root, a, b, edge = project_with_graph
    out = dot.render(ProjectPaths(root), view="system_map")
    assert f'id="{a.id}"' in out
    assert f'id="{b.id}"' in out
    assert f'id="{edge.id}"' in out


def test_dot_dag_uses_top_bottom_layout(project_with_graph) -> None:
    root, *_ = project_with_graph
    out = dot.render(ProjectPaths(root), view="dag")
    assert "rankdir=TB" in out


def test_dot_empty_project(tmp_path: Path, git_identity) -> None:
    root = tmp_path / "empty"
    init_project(root, statement="Do X.")
    out = dot.render(ProjectPaths(root))
    assert "digraph" in out
    assert "// empty project" in out
    assert out.rstrip().endswith("}")


def test_dot_escapes_quotes_in_labels(tmp_path: Path, git_identity) -> None:
    root = tmp_path / "demo"
    init_project(root, statement="X")
    node_ops.add_node('The "quoted" node', kind="concept", root=root)
    out = dot.render(ProjectPaths(root))
    # The quote must be escaped as \" in the DOT output.
    assert 'The \\"quoted\\" node' in out


def test_dot_write_to_file(project_with_graph) -> None:
    root, *_ = project_with_graph
    target = root / "reports" / "exports" / "graph.dot"
    dot.write(ProjectPaths(root), target, view="cld")
    assert target.is_file()
    content = target.read_text(encoding="utf-8")
    assert content.startswith("digraph ")
