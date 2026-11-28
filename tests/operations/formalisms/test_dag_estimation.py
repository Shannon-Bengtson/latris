"""The DAG effect-estimate plugin: its report section and claims for linear and logistic fits, rerun, staleness."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from latris.operations import edges as edge_ops
from latris.operations import estimation as est
from latris.operations import formalisms
from latris.operations import nodes as node_ops
from latris.operations.analysis_results import get_result
from latris.operations.init import init_project
from latris.repo.layout import ProjectPaths
from tests.operations.test_estimation import COLS, _data, _upload


@pytest.fixture
def project(tmp_path, git_identity, monkeypatch):
    root = tmp_path / "heart"
    init_project(root, statement="How much does exercise improve heart health?")
    for label in ("Age", "Exercise", "Heart health", "Heart attack"):
        node_ops.add_node(label, kind="variable", root=root)
    for a, b in (("Age", "Exercise"), ("Age", "Heart health"), ("Exercise", "Heart health"),
                 ("Age", "Heart attack"), ("Exercise", "Heart attack")):
        edge_ops.add_edge(a, b, kind="causal", root=root)
    _upload(root, tmp_path, _data(), "survey")
    monkeypatch.chdir(root)
    return root


SECTIONS = ("answer_to_question", "confidence_assessment", "assumptions_limitations", "open_questions")


def _kind():
    mt, r = formalisms.result_kind("dag-estimate")
    assert mt == "dag"
    return r


def _claims(p):
    out = {k: [] for k in SECTIONS}
    _kind().claims(p, out)
    return out


def test_linear_estimate_reads_and_claims(project):
    p = est.estimate("Exercise", "Heart health", "survey", columns=COLS, root=project)
    text = "\n".join(_kind().render(p))
    assert "Adjusted for Age — the smallest valid backdoor set the dataset measures. Model: linear regression, " \
           "HC3 robust standard errors; 2000 complete rows from survey." in text
    assert "|  | Change in Heart health per unit of Exercise | 95% CI | p |" in text
    assert "| Adjusted |" in text and "| Unadjusted |" in text
    assert "Odds ratio" not in text and "Coded as 0/1" not in text and "Cautions" not in text
    assert "This is the effect only if:" in text
    out = _claims(p)
    # Age confounds upwards (older people exercise less and have worse hearts), so adjusting moves it down.
    (shift,) = [c for c in out["answer_to_question"] if c.startswith("Adjusting for Age moved")]
    assert shift.endswith("(down) from the unadjusted association.")
    assert out["confidence_assessment"] == [] and out["open_questions"] == []
    assert "the linear model's form is right" in out["assumptions_limitations"][0]
    assert _kind().charts(p) == [("estimate-forest", {})]


def test_logistic_estimate_reads_as_odds_ratios_with_its_coding(project):
    p = est.estimate("Exercise", "Heart attack", "survey", columns=COLS, root=project)
    text = "\n".join(_kind().render(p))
    assert "|  | Odds ratio | 95% CI | p |" in text
    assert "Model: logistic regression" in text
    assert "Coded as 0/1: Heart attack: no = 0, yes = 1." in text


def test_no_adjustment_and_an_interval_through_zero(project, tmp_path):
    df = _data(n=40)
    df["Smoker"] = ["smoker"] * 5 + ["non-smoker"] * 35
    _upload(project, tmp_path, df, "small")
    node_ops.add_node("Smoking", root=project)
    edge_ops.add_edge("Smoking", "Heart health", root=project)
    # Smoking has no effect in the data, no backdoor path, and a small group: all three show.
    p = est.estimate("Smoking", "Heart health", "small", columns={"Smoking": "Smoker"}, estimator="linear",
                     root=project)
    assert p["effect"]["ci_low"] <= 0 <= p["effect"]["ci_high"]
    text = "\n".join(_kind().render(p))
    assert "Adjusted for nothing (no backdoor path)" in text
    assert "Coded as 0/1: Smoking: non-smoker = 0, smoker = 1." in text
    assert "Cautions: only 5 row(s) in one treatment group; the estimate is fragile." in text
    out = _claims(p)
    assert not any(c.startswith("Adjusting for") for c in out["answer_to_question"])
    assert out["confidence_assessment"] == [
        "The 95% interval for the effect of Smoking on Heart health includes no effect."]
    assert out["open_questions"] == [
        "Estimate of Smoking → Heart health: only 5 row(s) in one treatment group; the estimate is fragile."]


def test_given_adjustment_reads_as_given_and_reruns(project):
    p = est.estimate("Exercise", "Heart health", "survey", columns=COLS, adjust=["Age"], root=project)
    assert p["adjustment_how"] == "given"
    assert "Adjusted for Age — as given." in "\n".join(_kind().render(p))
    a = _kind().definition(p)
    assert (a.kind, a.treatment, a.outcome, a.dataset) == ("dag_estimate", "Exercise", "Heart health", "survey")
    assert a.adjust == ["Age"] and a.columns == COLS and a.estimator == "linear"
    run, payload = get_result(_kind().run(a, project), root=project)
    assert run.result_kind == "dag-estimate" and payload["effect"] == p["effect"]
    # A found set isn't written into the definition: a rerun finds it again.
    assert _kind().definition(est.estimate("Exercise", "Heart health", "survey", columns=COLS,
                                           root=project)).adjust == []


def test_run_needs_treatment_outcome_and_dataset(project):
    with pytest.raises(ValueError, match="needs treatment, outcome and dataset"):
        _kind().run(SimpleNamespace(treatment="Exercise", outcome="Heart health", dataset=None), project)


def test_fingerprint_is_the_dataset_register_and_its_files(project, tmp_path):
    paths = ProjectPaths(project)
    files = formalisms.fingerprint_files("dag", paths)
    assert files[0] == paths.data_datasets_yaml and any(f.name == "survey.csv" for f in files)
    bare = tmp_path / "bare"
    init_project(bare, statement="No data yet")
    bp = ProjectPaths(bare)
    bp.data_files_dir.rmdir()  # empty in a new project; gone in one that never had data
    assert [f for f in formalisms.fingerprint_files("dag", bp) if f.parent == bp.data_files_dir] == []
