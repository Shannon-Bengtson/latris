"""CLI integration tests for the analyse command group."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from latris.cli.app import app
from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations import view_attributes as va
from latris.operations.init import init_project

runner = CliRunner()


@pytest.fixture
def project(tmp_path: Path, git_identity, monkeypatch):
    """Project with a triangle: A →(+) B →(+) C →(−) A (balancing loop)."""
    root = tmp_path / "demo"
    init_project(root, statement="Test")
    a, _ = node_ops.add_node("Emissions", kind="variable", root=root)
    b, _ = node_ops.add_node("Pollution", kind="variable", root=root)
    c, _ = node_ops.add_node("Regulation", kind="variable", root=root)
    e1, _ = edge_ops.add_edge(a.id, b.id, kind="causal", root=root)
    e2, _ = edge_ops.add_edge(b.id, c.id, kind="causal", root=root)
    e3, _ = edge_ops.add_edge(c.id, a.id, kind="causal", root=root)
    va.set_view_attribute(e1.id, "cld", "polarity", "+", root=root)
    va.set_view_attribute(e2.id, "cld", "polarity", "+", root=root)
    va.set_view_attribute(e3.id, "cld", "polarity", "-", root=root)
    monkeypatch.chdir(root)
    return root, a, b, c


@pytest.fixture
def dag_project(tmp_path: Path, git_identity, monkeypatch):
    """Acyclic project: Z → X → Y, Z → Y (confounder Z)."""
    root = tmp_path / "dag"
    init_project(root, statement="Causal test")
    z, _ = node_ops.add_node("Confounder", kind="variable", root=root)
    x, _ = node_ops.add_node("Exposure", kind="variable", root=root)
    y, _ = node_ops.add_node("Outcome", kind="variable", root=root)
    edge_ops.add_edge(z.id, x.id, kind="causal", root=root)
    edge_ops.add_edge(z.id, y.id, kind="causal", root=root)
    edge_ops.add_edge(x.id, y.id, kind="causal", root=root)
    monkeypatch.chdir(root)
    return root, z, x, y


# ── loops ────────────────────────────────────────────────────────────────


def test_loops_finds_balancing(project):
    result = runner.invoke(app, ["analyse", "loops"])
    assert result.exit_code == 0
    assert "B" in result.stdout
    assert "1 loop" in result.stdout


def test_loops_empty_dag(dag_project):
    result = runner.invoke(app, ["analyse", "loops"])
    assert result.exit_code == 0
    assert "no feedback loops" in result.stdout.lower()


# ── propagate ────────────────────────────────────────────────────────────


def test_propagate(project):
    result = runner.invoke(app, ["analyse", "propagate", "Emissions"])
    assert result.exit_code == 0
    assert "Pollution" in result.stdout


# ── d-sep ────────────────────────────────────────────────────────────────


def test_d_sep_not_separated(dag_project):
    result = runner.invoke(app, ["analyse", "d-sep", "Exposure", "Outcome"])
    assert result.exit_code == 0
    assert "NOT d-separated" in result.stdout


def test_d_sep_given_confounder(dag_project):
    """X and Y should still be connected given Z (direct path X → Y)."""
    result = runner.invoke(app, ["analyse", "d-sep", "Exposure", "Outcome", "--given", "Confounder"])
    assert result.exit_code == 0
    # Still not d-separated because of direct path X → Y
    assert "NOT d-separated" in result.stdout


# ── blanket ──────────────────────────────────────────────────────────────


def test_blanket(dag_project):
    result = runner.invoke(app, ["analyse", "blanket", "Exposure"])
    assert result.exit_code == 0
    assert "Confounder" in result.stdout
    assert "Outcome" in result.stdout


# ── paths ────────────────────────────────────────────────────────────────


def test_paths(dag_project):
    result = runner.invoke(app, ["analyse", "paths", "Confounder", "Outcome"])
    assert result.exit_code == 0
    assert "path(s) found" in result.stdout


def test_paths_no_connection(dag_project):
    """Outcome has no path to Confounder in the undirected graph — actually
    it does, via X or directly. Test that we find 2 paths."""
    result = runner.invoke(app, ["analyse", "paths", "Confounder", "Outcome"])
    assert result.exit_code == 0
    assert "2 path" in result.stdout


# ── adjustment-sets ─────────────────────────────────────────────────────


def test_adjustment_sets_with_confounder(dag_project):
    """Z confounds X → Y; adjusting for Z blocks the backdoor path."""
    result = runner.invoke(app, ["analyse", "adjustment-sets", "Exposure", "Outcome"])
    assert result.exit_code == 0
    assert "Confounder" in result.stdout


def test_adjustment_sets_no_backdoor(dag_project):
    """Confounder → Outcome has no backdoor path (Z has no parents)."""
    result = runner.invoke(app, ["analyse", "adjustment-sets", "Confounder", "Outcome"])
    assert result.exit_code == 0
    # Either empty set (no adjustment needed) or no valid sets
    assert "empty set" in result.stdout.lower() or "no valid" in result.stdout.lower()
