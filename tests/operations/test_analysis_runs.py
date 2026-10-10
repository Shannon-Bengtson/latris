"""AnalysisRun log — record + read roundtrip."""

from __future__ import annotations

from pathlib import Path

from latris.operations import analysis_runs as runs_ops
from latris.operations.init import init_project


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "demo"
    init_project(root, statement="analysis run test")
    return root


def test_record_and_list_roundtrip(tmp_path, git_identity):
    root = _project(tmp_path)
    rec, sha = runs_ops.record_run(
        purpose="parameter-estimation",
        algorithm="bayesian-BDeu",
        library_version="9.9.9",
        hyperparameters={"equivalent_sample_size": 5},
        input_dataset_ids=["dataset_X"],
        metrics={"rows_used": 100},
        affected_target_ids=["node_A"],
        root=root,
    )
    assert sha
    assert rec.id.startswith("analysis-run_")
    assert rec.run_by.name  # filled from git identity
    assert rec.input_model_commit  # HEAD captured

    got = runs_ops.list_runs(root=root)
    assert len(got) == 1
    assert got[0].id == rec.id
    assert got[0].purpose == "parameter-estimation"
    assert got[0].hyperparameters == {"equivalent_sample_size": 5}
    assert got[0].metrics == {"rows_used": 100}


def test_list_filters_by_purpose_newest_first(tmp_path, git_identity):
    root = _project(tmp_path)
    r1, _ = runs_ops.record_run(
        purpose="parameter-estimation", algorithm="mle", library_version="1", root=root
    )
    r2, _ = runs_ops.record_run(
        purpose="sensitivity-analysis", algorithm="one-way", library_version="1", root=root
    )
    r3, _ = runs_ops.record_run(
        purpose="parameter-estimation", algorithm="bayesian", library_version="1", root=root
    )

    all_runs = runs_ops.list_runs(root=root)
    assert [r.id for r in all_runs] == [r3.id, r2.id, r1.id]  # newest first

    est = runs_ops.list_runs(purpose="parameter-estimation", root=root)
    assert [r.id for r in est] == [r3.id, r1.id]


def test_no_log_returns_empty(tmp_path, git_identity):
    root = _project(tmp_path)
    assert runs_ops.list_runs(root=root) == []
