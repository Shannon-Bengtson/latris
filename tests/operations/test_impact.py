"""Impact estimation on a theory of change: interrupted time series and difference-in-differences."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from latris.operations import edges as edge_ops
from latris.operations import impact, toc
from latris.operations import nodes as node_ops
from latris.operations.datasets import upload_dataset
from latris.operations.init import init_project

LEVEL, SLOPE = 5.0, 0.5  # true step and change of slope at the start


def _series(n_pre=24, n_post=24, seed=3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    k = np.arange(n_pre + n_post)
    post = k >= n_pre
    y = 50 + 0.2 * k + LEVEL * post + SLOPE * np.where(post, k - n_pre, 0) + rng.normal(0, 1, len(k))
    months = pd.date_range("2022-01-01", periods=len(k), freq="MS")
    return pd.DataFrame({"month": months.strftime("%Y-%m-%d"), "attendance_rate": y})


def _panel(seed=5, parallel=True) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for school in range(30):
        treated = school < 15
        for year in range(2018, 2024):
            post = year >= 2021
            trend = 1.0 * (year - 2018) + (0.0 if parallel or not treated else 3.0 * (year - 2018))
            y = 60 + 4 * treated + trend + 3.0 * (treated and post) + rng.normal(0, 1)
            rows.append({"school": f"s{school:02d}", "arm": "mentoring" if treated else "control",
                         "year": year, "Attendance": y})
    return pd.DataFrame(rows)


@pytest.fixture
def project(tmp_path: Path, git_identity, monkeypatch):
    root = tmp_path / "mentoring"
    init_project(root, statement="Did mentoring raise attendance?")
    for label in ("Mentoring", "Attendance"):
        node_ops.add_node(label, kind="variable", root=root)
    edge_ops.add_edge("Mentoring", "Attendance", kind="causal", root=root)
    toc.set_level("Mentoring", "activity", root=root)
    toc.set_level("Attendance", "impact", root=root)
    for name, df in (("monthly", _series()), ("short", _series(4, 4)), ("panel", _panel()),
                     ("diverging", _panel(parallel=False))):
        csv = tmp_path / f"{name}.csv"
        df.to_csv(csv, index=False)
        upload_dataset(csv, name=name, root=root)
    monkeypatch.chdir(root)
    return root


def test_its_recovers_step_and_slope(project):
    p = impact.estimate("Attendance", "monthly", time="month", at="2024-01-01", column="attendance_rate",
                        root=project)
    assert p["method"] == "its" and p["time_is_date"]
    assert p["periods_before"] == 24 and p["periods_after"] == 24
    lv, sl = p["level_change"], p["slope_change"]
    assert lv["ci_low"] < LEVEL < lv["ci_high"] and sl["ci_low"] < SLOPE < sl["ci_high"]
    true_end = LEVEL + SLOPE * 23
    assert p["effect"]["ci_low"] < true_end < p["effect"]["ci_high"]
    assert p["se_type"].startswith("GLS with AR(1) errors")
    assert not any("period(s) before" in w for w in p["warnings"])
    # the projected counterfactual is the pre-trend carried on
    last = p["series"][-1]
    assert last["fitted"] - last["counterfactual"] == pytest.approx(p["effect"]["estimate"])
    assert "Interrupted time series for Attendance" in impact.describe(p)


def _ar1_frame(seed: int, rho: float, n_pre=24, n_post=12) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = n_pre + n_post
    e = np.zeros(n)
    e[0] = rng.normal(0, 0.6 / np.sqrt(1 - rho**2))
    for i in range(1, n):
        e[i] = rho * e[i - 1] + rng.normal(0, 0.6)
    k = np.arange(n, dtype=float)
    frame = pd.DataFrame({"t": k, "y": 82 + 0.05 * k + 2.5 * (k >= n_pre) + e})
    frame.attrs["at"] = float(n_pre)
    return frame


def test_its_interval_keeps_near_nominal_coverage_under_autocorrelation():
    # Newey–West errors covered the true step only ~75% of the time here; AR(1) GLS stays near 90%.
    hits = sum(
        (r := impact._its(_ar1_frame(seed, 0.6), []))["level_change"]["ci_low"] < 2.5 < r["level_change"]["ci_high"]
        for seed in range(200)
    )
    assert hits / 200 >= 0.85
    warnings: list[str] = []
    impact._its(_ar1_frame(1, 0.8), warnings)
    assert any("autocorrelated" in w for w in warnings)


def test_its_short_series_warns_and_too_short_refuses(project):
    p = impact.estimate("Attendance", "short", time="month", at="2022-05-01", column="attendance_rate",
                        root=project)
    assert any("only 4 period(s) before" in w for w in p["warnings"])
    with pytest.raises(impact.ImpactError, match="at least 3 periods"):
        impact.estimate("Attendance", "short", time="month", at="2022-07-01", column="attendance_rate",
                        root=project)


def test_did_recovers_effect_and_clusters(project):
    p = impact.estimate("Attendance", "panel", time="year", at=2021, group="school",
                        treated=[f"s{i:02d}" for i in range(15)], root=project)
    assert p["method"] == "did"
    assert p["effect"]["ci_low"] < 3.0 < p["effect"]["ci_high"]
    assert p["se_type"].startswith("cluster-robust") and p["groups"] == 30
    assert p["pre_trend_difference"]["testable"] and p["pre_trend_difference"]["p"] > 0.1
    assert not p["warnings"]


def test_did_two_arms_and_diverging_pre_trends_warn(project):
    p = impact.estimate("Attendance", "diverging", time="year", at=2021, group="arm", treated=["mentoring"],
                        root=project)
    assert any("too few to cluster" in w for w in p["warnings"])
    assert any("trends already differ" in w for w in p["warnings"])


def test_refusals(project):
    with pytest.raises(impact.ImpactError, match="no column for Attendance"):
        impact.estimate("Attendance", "monthly", time="month", at="2024-01-01", root=project)
    with pytest.raises(impact.ImpactError, match="--treated"):
        impact.estimate("Attendance", "panel", time="year", at=2021, group="arm", root=project)
    with pytest.raises(impact.ImpactError, match="no row's group"):
        impact.estimate("Attendance", "panel", time="year", at=2021, group="arm", treated=["nope"], root=project)
    with pytest.raises(impact.ImpactError, match="isn't a date"):
        impact.estimate("Attendance", "monthly", time="month", at="soon", column="attendance_rate", root=project)
    node_ops.add_node("Weather", kind="variable", root=project)
    with pytest.raises(impact.ImpactError, match="no theory-of-change level"):
        impact.estimate("Weather", "panel", time="year", at=2021, root=project)


def test_record(project):
    from latris.operations.analysis_results import report_results

    p = impact.estimate("Attendance", "panel", time="year", at=2021, group="arm", treated=["mentoring"],
                        root=project)
    sha, run_id = impact.record(p, root=project)
    assert sha and run_id
    assert any(r.run.result_kind == "toc-impact" for r in report_results(root=project))


def test_build_spec_report_share_link_cli_and_route(project):
    from fastapi.testclient import TestClient
    from typer.testing import CliRunner

    from latris.cli.app import app
    from latris.exporters.markdown import render
    from latris.operations.formalisms import for_analysis
    from latris.operations.interpret import extract_claims
    from latris.operations.share_link import export_spec
    from latris.repo.layout import ProjectPaths
    from latris.schema.build_spec import SpecAnalysis
    from latris.server.app import create_app

    a = SpecAnalysis(kind="toc_impact", outcome="Attendance", dataset="monthly", time="month", at="2024-01-01",
                     columns={"Attendance": "attendance_rate"})
    assert for_analysis("toc_impact").run(a, project)
    md = render(ProjectPaths(project), model_type="theory_of_change", ai=False)
    assert "Theory of change: impact estimate" in md and "Step at the start" in md
    assert "Impact estimation: interrupted time series" in md  # foundations
    answer = extract_claims("answer_to_question", "theory_of_change", root=project)
    assert any(c.startswith("Interrupted time series for Attendance") for c in answer)
    _, spec = export_spec(model_type="theory_of_change", root=project)
    (again,) = [x for x in spec.analyses if x.kind == "toc_impact"]
    assert (again.time, again.at, again.columns) == ("month", "2024-01-01", {"Attendance": "attendance_rate"})

    r = CliRunner().invoke(app, ["toc", "impact", "Attendance", "--dataset", "diverging", "--time", "year",
                                 "--at", "2021", "--group", "arm", "--treated", "mentoring", "--no-record"])
    assert r.exit_code == 0, r.output
    assert "Difference-in-differences" in r.output and "caution" in r.output

    client = TestClient(create_app(project_root=project))
    r = client.post("/api/toc/impact", json={"outcome": "Attendance", "dataset": "panel", "time": "year",
                                             "at": 2021, "group": "arm", "record": False})
    assert r.status_code == 422 and "--treated" in r.json()["detail"]
    r = client.post("/api/toc/impact", json={"outcome": "Attendance", "dataset": "panel", "time": "year",
                                             "at": 2021, "group": "arm", "treated": ["mentoring"]})
    assert r.status_code == 200 and r.json()["commit_sha"]
