"""CLI-level tests for export commands.

These guard against output-formatting regressions (e.g. rich's markup parser
eating ``[...]`` blocks in DOT attribute syntax).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from latris.cli.app import app
from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations import view_attributes as view_attr_ops
from latris.operations.init import init_project


@pytest.fixture
def project(tmp_path: Path, git_identity, monkeypatch):
    root = tmp_path / "demo"
    init_project(root, statement="Q?")
    a, _ = node_ops.add_node("Price", kind="variable", root=root)
    b, _ = node_ops.add_node("Demand", kind="variable", root=root)
    edge, _ = edge_ops.add_edge(a.id, b.id, root=root)
    view_attr_ops.set_view_attribute(edge.id, "cld", "polarity", "-", root=root)
    # `require_project()` with no args uses cwd — make tests location-stable.
    monkeypatch.chdir(root)
    return root, edge


def test_export_dot_stdout_preserves_bracket_syntax(project) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["export", "dot", "--view", "cld"])
    assert result.exit_code == 0, result.output
    # Rich must NOT have eaten the DOT attribute blocks or the edge label.
    assert "[shape=box" in result.output
    assert '[label="-"' in result.output
    assert "digraph" in result.output


def test_export_md_stdout_preserves_content(project) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["export", "md"])
    assert result.exit_code == 0, result.output
    assert "# Q?" in result.output
    assert "## Nodes" in result.output
    assert "Price" in result.output and "Demand" in result.output


def test_export_dot_to_file(project, tmp_path: Path) -> None:
    root, _ = project
    runner = CliRunner()
    target = root / "reports" / "exports" / "graph.dot"
    result = runner.invoke(app, ["export", "dot", "--output", str(target)])
    assert result.exit_code == 0, result.output
    assert target.is_file()
    content = target.read_text(encoding="utf-8")
    assert "digraph" in content
    assert "[shape=box" in content


def test_export_dot_rejects_bad_view(project) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["export", "dot", "--view", "sankey"])
    assert result.exit_code != 0
