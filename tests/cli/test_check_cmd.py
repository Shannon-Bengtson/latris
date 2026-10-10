"""CLI integration tests for the check command group."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from latris.cli.app import app
from latris.operations import attributes as attr_ops
from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations import view_attributes as va
from latris.operations.init import init_project

runner = CliRunner()


@pytest.fixture
def contradictory_project(tmp_path: Path, git_identity, monkeypatch):
    """Project with one coherent edge and one description-vs-polarity conflict.

    Mirrors the 4DWW capability run's actual defect: edge has description
    "reduces stress" (decrease verb) but polarity '+'.
    """
    root = tmp_path / "demo"
    init_project(root, statement="Conflict?")
    a, _ = node_ops.add_node("Client Coverage", root=root)
    b, _ = node_ops.add_node("Employee Well-being", root=root)
    c, _ = node_ops.add_node("Productivity", root=root)
    # Coherent edge: increases X → polarity +
    coherent, _ = edge_ops.add_edge(a.id, c.id, kind="causal", root=root)
    attr_ops.set_attribute(coherent.id, "description", "Coverage drives productivity.", root=root)
    va.set_view_attribute(coherent.id, "cld", "polarity", "+", root=root)
    # Contradictory edge: reduces stress → polarity + (should be -)
    bad, _ = edge_ops.add_edge(a.id, b.id, kind="causal", root=root)
    attr_ops.set_attribute(bad.id, "description", "Strong coverage reduces stress and burnout.", root=root)
    va.set_view_attribute(bad.id, "cld", "polarity", "+", root=root)

    monkeypatch.chdir(root)
    return root, coherent, bad


def test_coherence_check_flags_contradictory_edge(contradictory_project):
    root, coherent, bad = contradictory_project
    result = runner.invoke(app, ["check", "coherence"])
    # Likely conflict → exit code 1 by design.
    assert result.exit_code == 1
    # Bad edge appears in output, coherent edge doesn't trigger.
    assert bad.id[:18] in result.stdout
    assert "likely" in result.stdout.lower()
    assert "1 finding(s)" in result.stdout


def test_coherence_check_clean_project_exits_zero(tmp_path, git_identity, monkeypatch):
    root = tmp_path / "clean"
    init_project(root, statement="Q?")
    a, _ = node_ops.add_node("A", root=root)
    b, _ = node_ops.add_node("B", root=root)
    edge, _ = edge_ops.add_edge(a.id, b.id, kind="causal", root=root)
    attr_ops.set_attribute(edge.id, "description", "A drives B forward.", root=root)
    va.set_view_attribute(edge.id, "cld", "polarity", "+", root=root)
    monkeypatch.chdir(root)

    result = runner.invoke(app, ["check", "coherence"])
    assert result.exit_code == 0
    assert "No polarity ↔ description contradictions" in result.stdout
