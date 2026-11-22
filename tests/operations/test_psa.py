"""Probabilistic sensitivity analysis on decision trees and Markov cohort models (operations/psa.py)."""

from __future__ import annotations

import math
from statistics import NormalDist

import pytest

from latris.operations import markov, psa
from latris.repo.layout import ProjectPaths
from tests.operations import test_decision_tree as DT
from tests.operations import test_markov as MK

dt_project = DT.project
mk_project = MK.project


def test_moments_give_that_mean_and_sd():
    a = psa.moments("beta", 0.1, 0.02)
    mean = a["alpha"] / (a["alpha"] + a["beta"])
    var = a["alpha"] * a["beta"] / ((a["alpha"] + a["beta"]) ** 2 * (a["alpha"] + a["beta"] + 1))
    assert mean == pytest.approx(0.1) and math.sqrt(var) == pytest.approx(0.02)
    g = psa.moments("gamma", 3000, 600)
    assert g["shape"] * g["scale"] == pytest.approx(3000) and math.sqrt(g["shape"]) * g["scale"] == pytest.approx(600)
    with pytest.raises(ValueError, match="below"):
        psa.moments("beta", 0.5, 0.6)
    with pytest.raises(ValueError, match="beta or gamma"):
        psa.moments("normal", 1, 1)


# ── decision tree ───────────────────────────────────────────────────


def test_dt_payoff_ranges_match_closed_form(dt_project):
    DT._build(dt_project)
    psa.set_range("decision_tree", "Launched, high", "normal", {"mean": 500, "sd": 100}, root=dt_project)
    psa.set_range("decision_tree", "Launched, low", "normal", {"mean": -200, "sd": 60}, root=dt_project)
    p = psa.dt_psa(runs=8000, root=dt_project)
    out = {o["output"]: o for o in p["outputs"]}
    # Launch = 0.4·X + 0.6·Y, normal with mean 80 and sd √(0.16·100² + 0.36·60²); License is fixed at 90.
    sigma = math.sqrt(0.16 * 100**2 + 0.36 * 60**2)
    assert out["Launch"]["point"] == pytest.approx(80) and out["Launch"]["mean"] == pytest.approx(80, abs=1.5)
    assert out["Launch"]["p95"] - out["Launch"]["p5"] == pytest.approx(2 * 1.6449 * sigma, rel=0.05)
    assert out["License"]["p5"] == out["License"]["p95"] == pytest.approx(90)
    z = NormalDist()
    d = 10 / sigma
    assert out["Launch"]["p_best"] == pytest.approx(1 - z.cdf(d), abs=0.02)
    # EVPI = E[max(Launch, 90)] − 90 = E[(Launch − 90)⁺]
    assert p["evpi"] == pytest.approx(sigma * z.pdf(d) - 10 * (1 - z.cdf(d)), rel=0.08)
    assert p["best"] == p["point_best"] == "License" and p["rival"] == "Launch"
    assert p["driver_target"] == "advantage of License over Launch"
    assert {d["input"] for d in p["drivers"]} == {"Launched, high (payoff)", "Launched, low (payoff)"}
    assert "Licensed, high (payoff)" in p["fixed"]
    assert psa.dt_psa(runs=200, root=dt_project) == psa.dt_psa(runs=200, root=dt_project)  # seeded


def test_dt_probability_range_moves_the_whole_uncertainty(dt_project):
    from scipy import stats

    DT._build(dt_project)
    psa.set_range("decision_tree", "Demand if launched -> Launched, high", "beta", {"mean": 0.4, "sd": 0.1},
                  root=dt_project)
    p = psa.dt_psa(runs=8000, root=dt_project)
    out = {o["output"]: o for o in p["outputs"]}
    # Demand is one uncertainty: licensing takes the same sampled P(high) as launching.
    assert out["License"]["mean"] == pytest.approx(90, abs=0.5) and out["License"]["p95"] > out["License"]["p5"]
    # Launch (700p − 200) beats License (100p + 50) iff p > 5/12.
    a = psa.moments("beta", 0.4, 0.1)
    assert out["Launch"]["p_best"] == pytest.approx(stats.beta(a["alpha"], a["beta"]).sf(5 / 12), abs=0.02)
    (drv,) = p["drivers"]
    assert drv["input"] == "P(Demand = High)" and drv["spearman"] < -0.9

    psa.clear_range("decision_tree", "Demand if launched -> Launched, high", root=dt_project)
    psa.set_range("decision_tree", "Demand if licensed", "dirichlet", {"n": 30}, root=dt_project)
    p = psa.dt_psa(runs=4000, root=dt_project)
    assert next(o for o in p["outputs"] if o["output"] == "License")["mean"] == pytest.approx(90, abs=1)
    psa.set_range("decision_tree", "Demand if launched", "dirichlet", {"n": 10}, root=dt_project)
    with pytest.raises(ValueError, match="more than one probability range"):
        psa.dt_psa(runs=50, root=dt_project)


def test_dt_range_refusals(dt_project):
    DT._build(dt_project)
    with pytest.raises(ValueError, match="lies outside"):
        psa.set_range("decision_tree", "Launched, high", "normal", {"mean": 100, "sd": 10}, root=dt_project)
    with pytest.raises(ValueError, match="Dirichlet goes on a whole set"):
        psa.set_range("decision_tree", "Launched, high", "dirichlet", {"n": 5}, root=dt_project)
    with pytest.raises(ValueError, match="worth n observations"):
        psa.set_range("decision_tree", "Demand if launched", "beta", {"alpha": 2, "beta": 3}, root=dt_project)
    with pytest.raises(ValueError, match="isn't a terminal node"):
        psa.set_range("decision_tree", "Strategy", "normal", {"mean": 0, "sd": 1}, root=dt_project)
    with pytest.raises(ValueError, match=r"must lie in \[0, 1\]"):
        psa.set_range("decision_tree", "Demand if launched -> Launched, high", "uniform", {"min": 0.2, "max": 1.4},
                      root=dt_project)
    with pytest.raises(ValueError, match="no input has a range"):
        psa.dt_psa(root=dt_project)


# ── Markov ──────────────────────────────────────────────────────────


def test_markov_tiny_model_by_hand(mk_project):
    MK._tiny(mk_project)
    # Two yearly cycles, no discounting: cost = 100 + 100·(1 − p), outcome = 1 + (1 − p); E[p] = 0.5.
    psa.set_range("markov", "Healthy -> Dead", "uniform", {"min": 0.4, "max": 0.6}, root=mk_project)
    p = psa.markov_psa(runs=2000, root=mk_project)
    (s,) = p["strategies"]
    assert s["strategy"] == "Base case"
    assert s["cost"]["point"] == pytest.approx(150) and s["cost"]["mean"] == pytest.approx(150, abs=0.1)
    assert (s["cost"]["min"], s["cost"]["max"]) == (pytest.approx(140, abs=0.1), pytest.approx(160, abs=0.1))
    assert s["outcome"]["mean"] == pytest.approx(1.5, abs=0.001)
    assert p["incremental"] == [] and "choice" not in p
    assert p["driver_target"] == "outcome of Base case" and p["drivers"][0]["spearman"] == pytest.approx(-1)


def test_markov_ceac_evpi_and_strategy_scope(mk_project):
    MK._full(mk_project)
    point = {r["strategy"]: r for r in markov.analyse(root=mk_project)["results"]}
    # A range on the cost of being sick moves costs only; its mean is the point value.
    psa.set_range("markov", "Sick", "gamma", {"mean": 3000, "sd": 600}, quantity="cost", root=mk_project)
    p = psa.markov_psa(runs=2000, root=mk_project)
    for s in p["strategies"]:
        assert s["cost"]["mean"] == pytest.approx(point[s["strategy"]]["cost"], rel=0.005)
        assert s["outcome"]["p5"] == pytest.approx(s["outcome"]["p95"])
    # A Dirichlet on leaving Healthy, for standard care only, leaves the new drug's results exact.
    psa.set_range("markov", "Healthy", "dirichlet", {"n": 200}, quantity="leaving", strategy="Standard care",
                  root=mk_project)
    psa.set_range("markov", "Sick", "beta", {"mean": 0.6, "sd": 0.05}, quantity="utility", root=mk_project)
    p = psa.markov_psa(runs=1000, root=mk_project)
    drug = next(s for s in p["strategies"] if s["strategy"] == "New drug")
    assert drug["outcome"]["p95"] > drug["outcome"]["p5"]  # the sick utility still moves it
    psa.clear_range("markov", "Sick", quantity="utility", root=mk_project)
    p = psa.markov_psa(runs=1000, root=mk_project)
    drug = next(s for s in p["strategies"] if s["strategy"] == "New drug")
    assert drug["outcome"]["p5"] == pytest.approx(drug["outcome"]["p95"])
    c = p["ceac"]
    assert len(c["wtp"]) == psa.CEAC_POINTS and c["wtp"][0] == 0
    for i in range(len(c["wtp"])):
        assert sum(col[i] for col in c["p"]) == pytest.approx(1)
        assert c["evpi"][i] >= -1e-9
    sc = c["strategies"].index("Standard care")
    assert c["p"][sc][0] == 1.0 and c["frontier"][0] == "Standard care"  # at £0 the cheaper wins
    assert p["choice"] in c["strategies"] and 0 <= p["p_cost_effective"] <= 1 and p["evpi"] >= 0
    labels = {d["input"] for d in p["drivers"]}
    assert {"P(Healthy → Sick) under Standard care", "P(Healthy → Dead) under Standard care",
            "Sick cost"} == labels
    assert "P(Healthy → Sick) under New drug" in p["fixed"]


def test_markov_rescales_and_refuses(mk_project):
    MK._full(mk_project)
    with pytest.raises(ValueError, match="for one strategy needs that strategy's own value"):
        psa.set_range("markov", "Healthy -> Dead", "beta", {"mean": 0.01, "sd": 0.002}, strategy="New drug",
                      root=mk_project)
    with pytest.raises(ValueError, match="say what about Sick"):
        psa.set_range("markov", "Sick", "gamma", {"mean": 3000, "sd": 600}, root=mk_project)
    markov.set_transition("Healthy -> Sick", 0.5, root=mk_project)
    markov.set_transition("Healthy -> Dead", 0.45, root=mk_project)
    psa.set_range("markov", "Healthy -> Sick", "uniform", {"min": 0.3, "max": 0.7}, root=mk_project)
    psa.set_range("markov", "Healthy -> Dead", "uniform", {"min": 0.25, "max": 0.65}, root=mk_project)
    p = psa.markov_psa(runs=200, root=mk_project)
    assert p["rescaled_runs"] > 0
    psa.set_range("markov", "Healthy", "dirichlet", {"n": 50}, quantity="leaving", root=mk_project)
    with pytest.raises(ValueError, match="keep one"):
        psa.markov_psa(runs=50, root=mk_project)


# ── surfaces ────────────────────────────────────────────────────────


def test_dt_report_claims_spec_cli_and_routes(dt_project):
    from fastapi.testclient import TestClient
    from typer.testing import CliRunner

    from latris.cli.app import app
    from latris.exporters.markdown import render
    from latris.operations.analysis_results import is_stale, report_results
    from latris.operations.build import build_from_spec
    from latris.operations.formalisms import for_analysis
    from latris.operations.init import init_project
    from latris.operations.interpret import extract_claims
    from latris.operations.share_link import export_spec
    from latris.server.app import create_app

    root = dt_project
    DT._build(root)
    runner = CliRunner()
    r = runner.invoke(app, ["dt", "range", "Demand if launched -> Launched, high", "beta", "--mean", "0.4",
                            "--sd", "0.1", "--reason", "survey of 200"])
    assert r.exit_code == 0, r.output
    r = runner.invoke(app, ["dt", "range", "Launched, high", "normal", "--mean", "500", "--sd", "100", "--verified"])
    assert r.exit_code == 0, r.output
    r = runner.invoke(app, ["dt", "psa", "--runs", "500"])
    assert r.exit_code == 0, r.output
    assert "What drives the advantage of License over Launch" in r.output

    md = render(ProjectPaths(root), model_type="decision_tree", ai=False)
    assert "Decision tree: probabilistic sensitivity analysis" in md and "Best in" in md
    assert "Probabilistic sensitivity analysis, acceptability curves" in md  # foundations
    assert any(c.startswith("Over 500 runs, License") for c in extract_claims("sensitivity", "decision_tree",
                                                                               root=root))
    assert any("not settled" in c for c in extract_claims("confidence_assessment", "decision_tree", root=root))

    (run,) = [x.run for x in report_results(root=root) if x.run.result_kind == "dt-psa"]
    assert not is_stale(run, ProjectPaths(root))
    psa.set_range("decision_tree", "Launched, low", "normal", {"mean": -200, "sd": 50}, root=root)
    assert is_stale(run, ProjectPaths(root))  # a new range ages the PSA
    psa.record(psa.dt_psa(runs=500, root=root), root=root)

    _, spec = export_spec(model_type="decision_tree", root=root)
    assert {(x.target, x.quantity, x.verified) for x in spec.decision_tree.ranges} == {
        ("Demand if launched -> Launched, high", "probability", False), ("Launched, high", "payoff", True),
        ("Launched, low", "payoff", False)}
    (a,) = [x for x in spec.analyses if x.kind == "dt_psa"]
    assert a.runs == 500 and for_analysis("dt_psa").run(a, root)
    other = root.parent / "rebuilt"
    init_project(other, statement="Q?")
    assert build_from_spec(spec, root=other).analyses
    assert len(psa.ranges("decision_tree", ProjectPaths(other))) == 3

    client = TestClient(create_app(project_root=root))
    r = client.post("/api/dt/range", json={"target": "Launched, low", "distribution": "normal",
                                           "params": {"mean": 100, "sd": 5}})
    assert r.status_code == 422 and "lies outside" in r.json()["detail"]
    r = client.post("/api/dt/range", json={"target": "Licensed, high", "distribution": "gamma",
                                           "params": {"mean": 150, "sd": 30}})
    assert r.status_code == 200 and set(r.json()["result"]["params"]) == {"shape", "scale"}
    assert client.get("/api/dt/range").json()["count"] == 4
    assert client.get("/api/markov/range").json()["count"] == 0  # each type lists only its own
    res = client.post("/api/dt/psa", json={"runs": 100, "record": False}).json()
    assert res["commit_sha"] is None and len(res["result"]["outputs"]) == 3
    r = client.post("/api/dt/range", json={"target": "Licensed, high", "clear": True})
    assert r.status_code == 200 and client.get("/api/dt/range").json()["count"] == 3


def test_markov_report_cli_and_routes(mk_project):
    from fastapi.testclient import TestClient
    from typer.testing import CliRunner

    from latris.cli.app import app
    from latris.exporters.markdown import render
    from latris.operations.interpret import extract_claims
    from latris.server.app import create_app

    root = mk_project
    MK._full(root)
    runner = CliRunner()
    r = runner.invoke(app, ["markov", "range", "Healthy -> Sick", "beta", "--mean", "0.06", "--sd", "0.015",
                            "--strategy", "New drug"])
    assert r.exit_code == 0, r.output
    r = runner.invoke(app, ["markov", "range", "Sick", "gamma", "-q", "cost", "--mean", "3000", "--sd", "600"])
    assert r.exit_code == 0, r.output
    r = runner.invoke(app, ["markov", "psa", "--runs", "200"])
    assert r.exit_code == 0, r.output
    assert "Probability cost-effective" in r.output

    md = render(ProjectPaths(root), model_type="markov", ai=False)
    assert "Markov cohort model: probabilistic sensitivity analysis" in md and "acceptability curve" in md
    md = render(ProjectPaths(root), model_type="markov", ai=False, chart_markers=True)
    assert "markov-ceac" in md
    assert any("most cost-effective in" in c for c in extract_claims("sensitivity", "markov", root=root))

    client = TestClient(create_app(project_root=root))
    r = client.post("/api/markov/range", json={"target": "Sick", "quantity": "utility", "distribution": "beta",
                                               "params": {"mean": 0.6, "sd": 0.05}})
    assert r.status_code == 200
    assert client.get("/api/markov/range").json()["count"] == 3
    res = client.post("/api/markov/psa", json={"runs": 50}).json()
    assert res["commit_sha"] and res["result"]["run_id"]
    assert client.post("/api/markov/range", json={"target": "Sick", "quantity": "utility",
                                                  "clear": True}).status_code == 200
