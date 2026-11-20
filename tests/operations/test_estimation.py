"""Effect estimation on a DAG: measured adjustment sets, OLS / logistic fits, and honest refusals."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from latris.operations import edges as edge_ops
from latris.operations import estimation as est
from latris.operations import nodes as node_ops
from latris.operations.analysis_results import report_results
from latris.operations.datasets import upload_dataset
from latris.operations.init import init_project

TRUE_EFFECT = 2.0


def _data(n=2000, seed=7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    age = rng.uniform(20, 80, n)
    exercise = 10 - 0.1 * age + rng.normal(0, 1, n)
    heart = 50 + TRUE_EFFECT * exercise - 0.5 * age + rng.normal(0, 2, n)
    attack_p = 1 / (1 + np.exp(-(-1 + 0.04 * (age - 50) - 0.3 * (exercise - 5))))
    return pd.DataFrame({"Age": age, "exercise_hours": exercise, "Heart health": heart,
                         "Heart attack": np.where(rng.uniform(size=n) < attack_p, "yes", "no"),
                         "Smoker": np.where(rng.uniform(size=n) < 0.3, "smoker", "non-smoker")})


@pytest.fixture
def project(tmp_path: Path, git_identity, monkeypatch):
    root = tmp_path / "heart"
    init_project(root, statement="How much does exercise improve heart health?")
    for label in ("Age", "Exercise", "Heart health", "Heart attack"):
        node_ops.add_node(label, kind="variable", root=root)
    for a, b in (("Age", "Exercise"), ("Age", "Heart health"), ("Exercise", "Heart health"),
                 ("Age", "Heart attack"), ("Exercise", "Heart attack")):
        edge_ops.add_edge(a, b, kind="causal", root=root)
    csv = tmp_path / "survey.csv"
    _data().to_csv(csv, index=False)
    upload_dataset(csv, name="survey", root=root)
    monkeypatch.chdir(root)
    return root


COLS = {"Exercise": "exercise_hours"}


def test_adjusted_estimate_recovers_the_effect(project):
    p = est.estimate("Exercise", "Heart health", "survey", columns=COLS, root=project)
    assert p["adjustment"] == ["Age"] and p["adjustment_how"].startswith("smallest")
    e = p["effect"]
    assert e["ci_low"] < TRUE_EFFECT < e["ci_high"]
    assert abs(p["unadjusted"]["estimate"] - TRUE_EFFECT) > 1  # confounded by age
    assert p["model"] == "linear" and p["se_type"] == "HC3 robust" and p["n"] == 2000
    assert "Effect of Exercise on Heart health" in est.describe(p)


def test_no_adjustment_needed(project):
    p = est.estimate("Age", "Exercise", "survey", columns=COLS, root=project)
    assert p["adjustment"] == []


def test_logistic_outcome(project):
    p = est.estimate("Exercise", "Heart attack", "survey", columns=COLS, root=project)
    assert p["model"] == "logistic" and p["coding"]["Heart attack"] == {"0": "no", "1": "yes"}
    assert p["effect"]["odds_ratio"] < 1 and p["effect"]["marginal_effect"] < 0
    with pytest.raises(est.EstimationError, match="two-valued outcome"):
        est.estimate("Exercise", "Heart health", "survey", columns=COLS, estimator="logistic", root=project)


def test_unmeasured_confounder_is_refused_with_what_to_measure(project):
    node_ops.add_node("Income", root=project)
    edge_ops.add_edge("Income", "Exercise", root=project)
    edge_ops.add_edge("Income", "Heart health", root=project)
    with pytest.raises(est.EstimationError, match="Measure one of: Income"):
        est.estimate("Exercise", "Heart health", "survey", columns=COLS, root=project)


def test_given_adjustment_is_checked(project):
    with pytest.raises(est.EstimationError, match="backdoor path"):
        est.estimate("Exercise", "Heart health", "survey", columns=COLS, adjust=[], root=project)
    node_ops.add_node("Fitness", root=project)
    edge_ops.add_edge("Exercise", "Fitness", root=project)
    with pytest.raises(est.EstimationError, match="the treatment affects"):
        est.estimate("Exercise", "Heart health", "survey", columns={**COLS, "Fitness": "Age"},
                     adjust=["Age", "Fitness"], root=project)
    p = est.estimate("Exercise", "Heart health", "survey", columns=COLS, adjust=["Age"], root=project)
    assert p["adjustment_how"] == "given"


def test_missing_columns_and_categories(project):
    with pytest.raises(est.EstimationError, match="no column for Exercise"):
        est.estimate("Exercise", "Heart health", "survey", root=project)
    node_ops.add_node("Smoking", root=project)
    edge_ops.add_edge("Smoking", "Heart health", root=project)
    p = est.estimate("Smoking", "Heart health", "survey", columns={"Smoking": "Smoker"}, root=project)
    assert p["coding"]["Smoking"] == {"0": "non-smoker", "1": "smoker"}


def test_cycle_refused(project):
    edge_ops.add_edge("Heart health", "Age", root=project)
    with pytest.raises(est.EstimationError, match="loop"):
        est.estimate("Exercise", "Heart health", "survey", columns=COLS, root=project)


def test_missing_rows_dropped_and_warned(project, tmp_path):
    df = _data(n=200)
    df.loc[:9, "Age"] = np.nan
    csv = tmp_path / "gappy.csv"
    df.to_csv(csv, index=False)
    upload_dataset(csv, name="gappy", root=project)
    p = est.estimate("Exercise", "Heart health", "gappy", columns=COLS, root=project)
    assert p["dropped"] == 10 and p["n"] == 190 and any("dropped" in w for w in p["warnings"])


def test_measured_search_beyond_minimal_sets():
    from types import SimpleNamespace as E

    # X ← A → B → Y and X ← A; only B is measured: {B} blocks X ← A → B → Y.
    edges = [E(id="1", from_id="A", to_id="X"), E(id="2", from_id="A", to_id="B"),
             E(id="3", from_id="B", to_id="Y"), E(id="4", from_id="X", to_id="Y")]
    z, info = est.choose_adjustment("X", "Y", edges, measured={"X", "Y", "B"})
    assert z == {"B"}
    z, _ = est.choose_adjustment("X", "Y", edges, measured={"X", "Y"})
    assert z is None


def test_record_report_claims_and_stale_on_data_change(project):
    from latris.exporters.markdown import render
    from latris.operations.interpret import extract_claims
    from latris.repo.layout import ProjectPaths

    p = est.estimate("Exercise", "Heart health", "survey", columns=COLS, root=project)
    sha, run_id = est.record(p, root=project)
    res = report_results(model_types=["dag"], root=project)
    assert [r.run.id for r in res] == [run_id] and not res[0].stale
    md = render(ProjectPaths(project), model_type="dag", ai=False)
    assert "Effect estimate" in md and "Unadjusted" in md and "This is the effect only if" in md
    answer = extract_claims("answer_to_question", "dag", root=project)
    assert any("Effect of Exercise on Heart health" in c for c in answer)
    assert any("Adjusting for Age moved the estimate" in c for c in answer)
    limits = extract_claims("assumptions_limitations", "dag", root=project)
    assert any("causal only if the DAG leaves out no common cause" in c for c in limits)
    f = ProjectPaths(project).data_files_dir / "survey.csv"
    f.write_text(f.read_text().replace("\n", "\n", 1) + "")
    with f.open("a") as h:
        h.write("50,5,60,no,smoker\n")
    assert report_results(model_types=["dag"], root=project)[0].stale


def test_cli_data_and_estimate(project, tmp_path):
    from typer.testing import CliRunner

    from latris.cli.app import app

    runner = CliRunner()
    csv = tmp_path / "second.csv"
    _data(n=300).to_csv(csv, index=False)
    out = runner.invoke(app, ["data", "add", str(csv), "--name", "second"])
    assert out.exit_code == 0, out.output
    assert "second" in runner.invoke(app, ["data", "list"]).output
    assert "exercise_hours" in runner.invoke(app, ["data", "show", "second"]).output
    out = runner.invoke(app, ["analyse", "estimate", "Exercise", "Heart health", "--dataset", "second",
                              "--column", "Exercise=exercise_hours"])
    assert out.exit_code == 0, out.output
    assert "Adjusted for: Age" in out.output and "Causal only if" in out.output and "recorded" in out.output
    out = runner.invoke(app, ["analyse", "estimate", "Exercise", "Heart health", "--dataset", "second",
                              "--column", "Exercise=exercise_hours", "--no-adjust"])
    assert out.exit_code != 0 and "backdoor" in out.output


def test_build_spec_runs_and_share_link_replays(project, tmp_path, git_identity):
    from latris.operations.build import build_from_spec, load_spec
    from latris.operations.share_link import export_spec

    spec = load_spec("""
analyses:
  - {kind: dag_estimate, treatment: Exercise, outcome: Heart health, dataset: survey,
     columns: {Exercise: exercise_hours}}
""")
    result = build_from_spec(spec, root=project)
    assert result.analyses and not result.notes
    _, exported = export_spec(model_type="dag", root=project)
    # It read a dataset a link can't carry, so the link carries the result as the sender's instead.
    assert not [a for a in exported.analyses if a.kind == "dag_estimate"]
    (carried,) = [c for c in exported.carried_results if c.kind == "dag-estimate"]
    assert carried.datasets[0]["name"] == "survey"
    copy = tmp_path / "copy"
    init_project(copy, statement="copy")
    out = build_from_spec(exported, root=copy)
    assert out.carried and not out.notes
