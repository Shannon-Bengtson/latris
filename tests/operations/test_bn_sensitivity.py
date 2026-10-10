"""BN sensitivity — ranking + provenance overlay + run recording."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import analysis_runs as runs_ops
from latris.operations import bn as bn_ops
from latris.operations import bn_sensitivity
from latris.operations.edges import add_edge
from latris.operations.init import init_project
from latris.operations.nodes import add_node
from latris.repo.project import require_project
from latris.schema.bn import CPTEntry, CPTRow, CPTSet

pytest.importorskip("pgmpy")


@pytest.fixture
def project(tmp_path: Path, git_identity):
    """A -> T (strong), plus an irrelevant isolated node N.

    A's prior dominates P(T=t0); the T|a0 row is human-verified; N can't move T.
    """
    root = tmp_path / "demo"
    init_project(root, statement="sensitivity test")
    a, _ = add_node("A", kind="variable", root=root)
    t, _ = add_node("T", kind="variable", root=root)
    n, _ = add_node("N", kind="variable", root=root)
    add_edge(a.id, t.id, kind="causal", root=root)
    bn_ops.set_state_space("A", ["a0", "a1"], root=root)
    bn_ops.set_state_space("T", ["t0", "t1"], root=root)
    bn_ops.set_state_space("N", ["n0", "n1"], root=root)

    paths = require_project(root)
    store = CPTSet(entries=[
        CPTEntry(target_id=a.id, parents=[], states=["a0", "a1"],
                 rows=[CPTRow(p=[0.5, 0.5], origin="human-direct", verification="unverified")]),
        CPTEntry(target_id=t.id, parents=[a.id], states=["t0", "t1"], rows=[
            CPTRow(parent_states={a.id: "a0"}, p=[0.9, 0.1],
                   origin="human-elicited", verification="human-verified"),
            CPTRow(parent_states={a.id: "a1"}, p=[0.1, 0.9], origin="human-direct"),
        ]),
        CPTEntry(target_id=n.id, parents=[], states=["n0", "n1"],
                 rows=[CPTRow(p=[0.5, 0.5])]),
    ])
    bn_ops._dump(bn_ops._cpt_path(paths), store)
    return root, a.id, t.id, n.id


def test_ranks_influential_parameter_first_and_flags_weak(project):
    root, a_id, t_id, n_id = project
    res = bn_sensitivity.sensitivity("T", "t0", root=root)

    assert res.baseline == pytest.approx(0.5)  # 0.5·0.9 + 0.5·0.1
    top = res.findings[0]
    assert top.node_id == a_id          # A's prior dominates
    assert top.influence == pytest.approx(0.8, abs=1e-9)
    assert top.weak is True             # A's prior is unverified -> flagged

    # The human-verified T|a0 row is not flagged weak.
    t_findings = [f for f in res.findings if f.node_id == t_id and f.verification == "human-verified"]
    assert t_findings and all(f.weak is False for f in t_findings)

    # The irrelevant node can't move the target.
    n_finding = next(f for f in res.findings if f.node_id == n_id)
    assert n_finding.influence == pytest.approx(0.0, abs=1e-9)


def test_evidence_node_excluded_and_recording(project):
    root, a_id, t_id, n_id = project
    res = bn_sensitivity.sensitivity("T", "t0", evidence={"A": "a0"}, root=root)
    # With A observed, no finding may come from A (it's clamped).
    assert all(f.node_id != a_id for f in res.findings)
    assert res.baseline == pytest.approx(0.9)  # P(T=t0 | A=a0)

    sha, run_id = bn_sensitivity.record_sensitivity(res, root=root)
    assert sha and run_id
    runs = runs_ops.list_runs(purpose="sensitivity-analysis", root=root)
    assert len(runs) == 1
    assert runs[0].output_artifacts  # artifact path recorded
    artifact = require_project(root).root / runs[0].output_artifacts[0]
    assert artifact.exists()


def test_stored_cpts_unchanged_after_sensitivity(project):
    root, a_id, t_id, n_id = project
    before = bn_ops.get_cpts(root=root).model_dump(mode="json")
    bn_sensitivity.sensitivity("T", "t0", root=root)
    after = bn_ops.get_cpts(root=root).model_dump(mode="json")
    assert before == after  # read-only on the stored CPTs


def test_cli_sensitivity(project, monkeypatch):
    from typer.testing import CliRunner

    from latris.cli.app import app

    root, a_id, t_id, n_id = project
    monkeypatch.chdir(root)
    r = CliRunner().invoke(app, ["bn", "sensitivity", "T", "--state", "t0", "--no-record"])
    assert r.exit_code == 0, r.stdout
    assert "Sensitivity" in r.stdout
