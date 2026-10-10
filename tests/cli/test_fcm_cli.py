"""CLI integration tests for FCM commands."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from latris.cli.app import app
from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations.init import init_project

runner = CliRunner()


@pytest.fixture
def project(tmp_path: Path, git_identity, monkeypatch):
    """Project with triangle: A → B → C → A."""
    root = tmp_path / "demo"
    init_project(root, statement="FCM test")
    a, _ = node_ops.add_node("Investment", kind="variable", root=root)
    b, _ = node_ops.add_node("Growth", kind="variable", root=root)
    c, _ = node_ops.add_node("Revenue", kind="variable", root=root)
    e1, _ = edge_ops.add_edge(a.id, b.id, kind="causal", root=root)
    e2, _ = edge_ops.add_edge(b.id, c.id, kind="causal", root=root)
    e3, _ = edge_ops.add_edge(c.id, a.id, kind="causal", root=root)
    monkeypatch.chdir(root)
    return root, a, b, c, e1, e2, e3


def test_set_weight(project):
    _, _, _, _, e1, _, _ = project
    result = runner.invoke(app, ["fcm", "set-weight", e1.id, "0.7"])
    assert result.exit_code == 0
    assert "0.7" in result.stdout


def test_weights_list(project):
    _, _, _, _, e1, e2, _ = project
    r1 = runner.invoke(app, ["fcm", "set-weight", e1.id, "0.7"])
    assert r1.exit_code == 0
    r2 = runner.invoke(app, ["fcm", "set-weight", e2.id, "--", "-0.3"])
    assert r2.exit_code == 0
    result = runner.invoke(app, ["fcm", "weights"])
    assert result.exit_code == 0
    # Check that at least some weights are shown (not all dashes)
    assert "0.7" in result.stdout or "+0.7" in result.stdout
    assert "0.3" in result.stdout or "-0.3" in result.stdout


def test_infer_without_weights(project):
    """Inference with no weights should still work (all zero weights)."""
    result = runner.invoke(app, ["fcm", "infer"])
    assert result.exit_code == 0
    assert "converged" in result.stdout.lower()


def test_infer_with_weights(project):
    _, _, _, _, e1, e2, e3 = project
    runner.invoke(app, ["fcm", "set-weight", e1.id, "0.8"])
    runner.invoke(app, ["fcm", "set-weight", e2.id, "0.6"])
    runner.invoke(app, ["fcm", "set-weight", e3.id, "0.4"])
    result = runner.invoke(app, ["fcm", "infer"])
    assert result.exit_code == 0
    assert "converged" in result.stdout.lower()
    assert "Investment" in result.stdout


def test_infer_with_clamp(project):
    _, a, _, _, e1, _, _ = project
    runner.invoke(app, ["fcm", "set-weight", e1.id, "0.8"])
    result = runner.invoke(app, ["fcm", "infer", "--clamp", "Investment=1.0"])
    assert result.exit_code == 0
    assert "clamped" in result.stdout.lower()


def test_set_weight_out_of_range(project):
    _, _, _, _, e1, _, _ = project
    result = runner.invoke(app, ["fcm", "set-weight", e1.id, "2.5"])
    assert result.exit_code != 0
    assert "[-1" in result.stdout or "error" in result.stdout.lower() or "must be" in result.stdout.lower()
