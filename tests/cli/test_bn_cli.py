"""CLI integration tests for the `bn` command group."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from latris.cli.app import app
from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations.init import init_project

runner = CliRunner()

pytest.importorskip("pgmpy")


@pytest.fixture
def project(tmp_path: Path, git_identity, monkeypatch):
    """rain -> wet."""
    root = tmp_path / "demo"
    init_project(root, statement="BN CLI test")
    rain, _ = node_ops.add_node("Rain", kind="variable", root=root)
    wet, _ = node_ops.add_node("Wet", kind="variable", root=root)
    edge_ops.add_edge(rain.id, wet.id, kind="causal", root=root)
    monkeypatch.chdir(root)
    return root, rain, wet


def _quantify(project) -> None:
    """Fully specify the rain->wet BN via the CLI."""
    root, rain, wet = project
    assert runner.invoke(app, ["bn", "set-state-space", "Rain", "yes,no"]).exit_code == 0
    assert runner.invoke(app, ["bn", "set-state-space", "Wet", "yes,no"]).exit_code == 0
    assert runner.invoke(app, ["bn", "set-cpt", "Rain", "--probs", "0.2,0.8"]).exit_code == 0
    r = runner.invoke(app, ["bn", "set-cpt", "Wet", "--parents", "Rain", "--probs", "0.9,0.1,0.1,0.9"])
    assert r.exit_code == 0, r.stdout


def test_set_state_space(project):
    result = runner.invoke(app, ["bn", "set-state-space", "Rain", "yes,no"])
    assert result.exit_code == 0
    assert "set" in result.stdout.lower()
    r2 = runner.invoke(app, ["bn", "state-spaces"])
    assert r2.exit_code == 0
    assert "Rain" in r2.stdout and "yes" in r2.stdout


def test_set_cpt_shape_error(project):
    runner.invoke(app, ["bn", "set-state-space", "Rain", "yes,no"])
    runner.invoke(app, ["bn", "set-state-space", "Wet", "yes,no"])
    # Wet has parent Rain (2 states) × 2 states = 4 probs expected; give 2.
    result = runner.invoke(app, ["bn", "set-cpt", "Wet", "--parents", "Rain", "--probs", "0.9,0.1"])
    assert result.exit_code != 0
    assert "expected 4 probabilities" in result.stdout


def test_set_cpt_requires_state_space_first(project):
    result = runner.invoke(app, ["bn", "set-cpt", "Rain", "--probs", "0.2,0.8"])
    assert result.exit_code != 0
    assert "state space" in result.stdout.lower()


def test_check_reports_gaps_then_passes(project):
    before = runner.invoke(app, ["bn", "check"])
    assert before.exit_code == 1
    assert "missing_state_space" in before.stdout or "missing_cpt" in before.stdout

    _quantify(project)
    after = runner.invoke(app, ["bn", "check"])
    assert after.exit_code == 0
    assert "ready" in after.stdout.lower()


def test_cpts_list(project):
    _quantify(project)
    result = runner.invoke(app, ["bn", "cpts"])
    assert result.exit_code == 0
    assert "Rain" in result.stdout and "Wet" in result.stdout


def test_marginals(project):
    _quantify(project)
    result = runner.invoke(app, ["bn", "marginals"])
    assert result.exit_code == 0
    # P(wet=yes) = 0.26
    assert "0.260" in result.stdout


def test_query_with_evidence(project):
    _quantify(project)
    result = runner.invoke(app, ["bn", "query", "--evidence", "Wet=yes", "--query", "Rain"])
    assert result.exit_code == 0
    # P(rain=yes | wet=yes) = 0.692
    assert "0.692" in result.stdout

    bad = runner.invoke(app, ["bn", "query", "--evidence", "Wet=maybe"])
    assert bad.exit_code != 0
