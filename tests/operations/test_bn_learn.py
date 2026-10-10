"""BN parameter learning — estimation accuracy + protect-expert merge."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from latris.operations import analysis_runs as runs_ops
from latris.operations import bn as bn_ops
from latris.operations import bn_learn
from latris.operations.datasets import upload_dataset
from latris.operations.edges import add_edge
from latris.operations.init import init_project
from latris.operations.nodes import add_node
from latris.repo.project import require_project
from latris.schema.bn import CPTEntry, CPTRow, CPTSet

pytest.importorskip("pgmpy")


def _write_csv(path: Path) -> None:
    """Deterministic data: P(A=a0)=0.6; P(B=b0|a0)=0.8; P(B=b0|a1)=0.25."""
    rows = (
        [("a0", "b0")] * 480 + [("a0", "b1")] * 120
        + [("a1", "b0")] * 100 + [("a1", "b1")] * 300
    )
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["A", "B"])
        w.writerows(rows)


@pytest.fixture
def project(tmp_path: Path, git_identity):
    """A -> B, both binary, with a registered dataset matching the labels."""
    root = tmp_path / "demo"
    init_project(root, statement="BN learning test")
    a, _ = add_node("A", kind="variable", root=root)
    b, _ = add_node("B", kind="variable", root=root)
    add_edge(a.id, b.id, kind="causal", root=root)
    bn_ops.set_state_space("A", ["a0", "a1"], root=root)
    bn_ops.set_state_space("B", ["b0", "b1"], root=root)
    csv_path = tmp_path / "data.csv"
    _write_csv(csv_path)
    ds, _ = upload_dataset(csv_path, name="obs", root=root)
    return root, a.id, b.id, ds.id


def _cpt_by_node(root):
    return {e.target_id: e for e in bn_ops.get_cpts(root=root).entries}


def test_mle_recovers_generating_distribution(project):
    root, a_id, b_id, ds_id = project
    proposal = bn_learn.learn_cpts("obs", estimator="mle", root=root)
    bn_learn.apply_learned(proposal, root=root)

    cpts = _cpt_by_node(root)
    (a_root_row,) = cpts[a_id].rows
    assert a_root_row.p[0] == pytest.approx(0.6, abs=1e-9)  # P(A=a0)

    b_rows = {r.parent_states[a_id]: r for r in cpts[b_id].rows}
    assert b_rows["a0"].p[0] == pytest.approx(0.8, abs=1e-9)   # P(B=b0|a0)
    assert b_rows["a1"].p[0] == pytest.approx(0.25, abs=1e-9)  # P(B=b0|a1)


def test_learned_rows_are_data_derived_and_sourced(project):
    root, a_id, b_id, ds_id = project
    proposal = bn_learn.learn_cpts("obs", estimator="mle", root=root)
    _, run_id = bn_learn.apply_learned(proposal, root=root)

    cpts = _cpt_by_node(root)
    for row in cpts[b_id].rows:
        assert row.origin == "data-derived"
        assert row.source_id == run_id  # points at the AnalysisRun

    runs = runs_ops.list_runs(root=root)
    assert len(runs) == 1
    assert runs[0].purpose == "parameter-estimation"
    assert runs[0].input_dataset_ids == [ds_id]
    assert runs[0].metrics["rows_used"] == 1000


def test_merge_protects_expert_rows(project):
    root, a_id, b_id, ds_id = project
    # Craft an existing B CPT: a0 row human-elicited (protect), a1 row default.
    paths = require_project(root)
    store = CPTSet(entries=[
        CPTEntry(
            target_id=b_id, parents=[a_id], states=["b0", "b1"],
            rows=[
                CPTRow(parent_states={a_id: "a0"}, p=[0.99, 0.01], origin="human-elicited"),
                CPTRow(parent_states={a_id: "a1"}, p=[0.5, 0.5], origin="human-direct"),
            ],
        )
    ])
    bn_ops._dump(bn_ops._cpt_path(paths), store)

    proposal = bn_learn.learn_cpts("obs", nodes=["B"], estimator="mle", root=root)
    bn_learn.apply_learned(proposal, root=root)

    b = _cpt_by_node(root)[b_id]
    rows = {r.parent_states[a_id]: r for r in b.rows}
    # a0 was expert-elicited → kept verbatim (not the 0.8 from data).
    assert rows["a0"].origin == "human-elicited"
    assert rows["a0"].p[0] == pytest.approx(0.99)
    # a1 was a low-provenance default → overwritten with data (0.25).
    assert rows["a1"].origin == "data-derived"
    assert rows["a1"].p[0] == pytest.approx(0.25, abs=1e-9)
    # Blended table → mixed origin.
    assert b.origin == "mixed"


def test_cli_learn_applies_with_yes(project, monkeypatch):
    from typer.testing import CliRunner

    from latris.cli.app import app

    root, a_id, b_id, ds_id = project
    monkeypatch.chdir(root)
    r = CliRunner().invoke(app, ["bn", "learn", "obs", "--estimator", "mle", "--yes"])
    assert r.exit_code == 0, r.stdout
    assert "applied" in r.stdout.lower()
    # CPTs now exist and are data-derived.
    assert _cpt_by_node(root)[b_id].rows[0].origin == "data-derived"


def test_missing_column_errors(project):
    root, a_id, b_id, ds_id = project
    # Add a third BN node with no matching dataset column.
    c, _ = add_node("C", kind="variable", root=root)
    add_edge(b_id, c.id, kind="causal", root=root)
    bn_ops.set_state_space("C", ["c0", "c1"], root=root)
    with pytest.raises(ValueError, match="missing a column"):
        bn_learn.learn_cpts("obs", root=root)
