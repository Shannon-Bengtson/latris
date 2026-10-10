"""CLI: Noisy-OR canonical models end-to-end (set, check, list, infer)."""

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
    """Storm -> Outage <- Maintenance (a binary fault node with 2 binary causes)."""
    root = tmp_path / "demo"
    init_project(root, statement="Noisy-OR CLI test")
    outage, _ = node_ops.add_node("Outage", kind="variable", root=root)
    storm, _ = node_ops.add_node("Storm", kind="variable", root=root)
    maint, _ = node_ops.add_node("Maintenance", kind="variable", root=root)
    edge_ops.add_edge(storm.id, outage.id, kind="causal", root=root)
    edge_ops.add_edge(maint.id, outage.id, kind="causal", root=root)
    monkeypatch.chdir(root)
    return root


def _quantify_roots():
    for name in ("Storm", "Maintenance", "Outage"):
        assert runner.invoke(app, ["bn", "set-state-space", name, "yes,no"]).exit_code == 0
    assert runner.invoke(app, ["bn", "set-cpt", "Storm", "--probs", "0.3,0.7"]).exit_code == 0
    assert runner.invoke(app, ["bn", "set-cpt", "Maintenance", "--probs", "0.2,0.8"]).exit_code == 0


def test_noisy_or_makes_model_ready_and_infers(project):
    _quantify_roots()
    r = runner.invoke(app, [
        "bn", "set-noisy-or", "Outage",
        "-c", "Storm=yes:0.6", "-c", "Maintenance=yes:0.3", "--leak", "0.02",
    ])
    assert r.exit_code == 0, r.stdout
    assert "Noisy-OR" in r.stdout

    check = runner.invoke(app, ["bn", "check"])
    assert check.exit_code == 0, check.stdout
    assert "ready" in check.stdout.lower()

    cpts = runner.invoke(app, ["bn", "cpts"])
    assert cpts.exit_code == 0
    assert "Noisy-OR" in cpts.stdout  # expanded + marked

    marg = runner.invoke(app, ["bn", "marginals"])
    assert marg.exit_code == 0
    assert "Outage" in marg.stdout


def test_noisy_or_requires_binary_and_blocks_dual_definition(project):
    _quantify_roots()
    # Tabular CPT first, then Noisy-OR on the same node must be refused.
    assert runner.invoke(app, [
        "bn", "set-cpt", "Outage", "--parents", "Storm,Maintenance",
        "--probs", "0.9,0.1,0.7,0.3,0.5,0.5,0.02,0.98",
    ]).exit_code == 0
    dual = runner.invoke(app, [
        "bn", "set-noisy-or", "Outage", "-c", "Storm=yes:0.6", "-c", "Maintenance=yes:0.3",
    ])
    assert dual.exit_code != 0
    assert "tabular cpt" in dual.stdout.lower()


def test_set_noisy_or_rejects_bad_cause_syntax(project):
    _quantify_roots()
    bad = runner.invoke(app, ["bn", "set-noisy-or", "Outage", "-c", "Storm-yes-0.6"])
    assert bad.exit_code != 0
