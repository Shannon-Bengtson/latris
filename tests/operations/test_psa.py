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


def test_markov_psa_without_a_willingness_to_pay(mk_project):
    """Two strategies and no WTP: no cost-effectiveness choice; the drivers explain the outcome gained."""
    MK._full(mk_project)
    with pytest.raises(ValueError, match="no input has a range yet"):
        psa.markov_psa(runs=50, root=mk_project)
    markov.set_settings(wtp=None, root=mk_project)
    psa.set_range("markov", "Sick", "beta", {"mean": 0.6, "sd": 0.05}, quantity="utility", root=mk_project)
    p = psa.markov_psa(runs=200, root=mk_project)
    assert p["wtp"] is None and "choice" not in p and "evpi" not in p
    assert all("nmb" not in s for s in p["strategies"])
    assert p["driver_target"] in {"QALY gained by New drug over Standard care",
                                  "QALY gained by Standard care over New drug"}
    assert [d["input"] for d in p["drivers"]] == ["Sick utility"]
    assert "Sick cost" in p["fixed"] and p["correlations"] == []


def test_markov_psa_refuses_an_incomplete_model(mk_project):
    with pytest.raises(ValueError, match="the Markov model is incomplete"):
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
    r = client.post("/api/dt/correlation", json={"target": "Launched, high", "other": "Launched, low", "rho": 0.5,
                                                 "reason": "one finance model"})
    assert r.status_code == 200 and r.json()["result"]["rho"] == 0.5
    p = client.post("/api/dt/psa", json={"runs": 100, "record": False}).json()["result"]
    assert p["correlations"][0]["reason"] == "one finance model" and p["evppi"]


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


def test_partial_evpi_matches_the_closed_form(dt_project):
    DT._build(dt_project)
    psa.set_range("decision_tree", "Launched, high", "normal", {"mean": 500, "sd": 100}, root=dt_project)
    psa.set_range("decision_tree", "Launched, low", "normal", {"mean": -200, "sd": 60}, root=dt_project)
    p = psa.dt_psa(runs=10000, root=dt_project)
    z = NormalDist()

    def gain(sigma: float) -> float:  # E[(N(80, σ) − 90)⁺]: knowing one payoff, the other still at its mean
        d = 10 / sigma
        return sigma * z.pdf(d) - 10 * (1 - z.cdf(d))

    by = {r["input"]: r["evppi"] for r in p["evppi"]}
    assert by["Launched, high (payoff)"] == pytest.approx(gain(0.4 * 100), rel=0.15)
    assert by["Launched, low (payoff)"] == pytest.approx(gain(0.6 * 60), rel=0.15)
    assert max(by.values()) <= p["evpi"] + 1e-9  # one input can't be worth more than all of them


def test_partial_evpi_of_a_set_by_regression():
    import numpy as np

    rng = np.random.default_rng(1)
    x = rng.dirichlet([8, 12], size=4000)
    nb = np.column_stack([np.full(4000, 90.0), 700 * x[:, 0] - 200])  # licence vs launch, as in the tree
    exact = np.mean(np.maximum(90, 700 * x[:, 0] - 200)) - max(90, (700 * x[:, 0] - 200).mean())
    assert psa.evppi(nb, x) == pytest.approx(exact, rel=0.1)
    assert psa.evppi(nb, rng.random((4000, 1))) == 0  # an unrelated input is worth nothing


def _two_options(seed: int, runs: int):
    """Do nothing (0) or act (x + z), x and z standard normal: knowing x is worth E[x⁺] = 1/√(2π)."""
    import numpy as np

    rng = np.random.default_rng(seed)
    x, z = rng.normal(size=runs), rng.normal(size=runs)
    return rng, x, np.column_stack([np.zeros(runs), x + z])


def test_partial_evpi_of_an_irrelevant_input_is_zero():
    """The regression's own noise mustn't pass for value: binned means gave a pure-noise input 5–8% of the EVPI."""
    import numpy as np

    single, sets = [], []
    for seed in range(20):
        rng, _, nb = _two_options(seed, 1000)
        single.append(psa.evppi(nb, rng.lognormal(size=1000)))
        sets.append(psa.evppi(nb, rng.dirichlet([5, 5, 5, 5], size=1000)))
    evpi = nb.max(axis=1).mean() - nb.mean(axis=0).max()
    assert sum(v > 0 for v in single) <= 2 and sum(v > 0 for v in sets) <= 2
    assert np.mean(single) < 0.02 * evpi and np.mean(sets) < 0.02 * evpi
    assert psa.evppi(nb, np.ones(1000)) == 0  # nor an input that doesn't vary


def test_partial_evpi_recovers_a_known_value_and_stays_under_the_total():
    import numpy as np

    exact = 1 / math.sqrt(2 * math.pi)
    values = []
    for seed in range(10):
        _, x, nb = _two_options(seed, 4000)
        values.append(psa.evppi(nb, x))
        assert values[-1] <= nb.max(axis=1).mean() - nb.mean(axis=0).max()
        assert psa.evppi(nb, np.exp(x)) == pytest.approx(values[-1])  # ranks: any monotone rescaling
    assert np.mean(values) == pytest.approx(exact, rel=0.06)
    # A threshold the choice turns on, which no polynomial follows: act pays 1 above the 70th percentile.
    rng = np.random.default_rng(3)
    u = rng.random(8000)
    nb = np.column_stack([np.zeros(8000), np.where(u > 0.7, 1.0, -0.2) + rng.normal(size=8000) * 0.5])
    assert psa.evppi(nb, u) == pytest.approx(0.3 - 0.16, rel=0.12)


def test_correlated_ranges(mk_project):
    from fastapi.testclient import TestClient
    from typer.testing import CliRunner

    from latris.cli.app import app
    from latris.operations import global_sensitivity as gs
    from latris.operations._sampling import spearman
    from latris.operations.analysis_results import is_stale, report_results
    from latris.operations.share_link import export_spec
    from latris.server.app import create_app

    root = mk_project
    MK._full(root)
    psa.set_range("markov", "Healthy -> Sick", "beta", {"mean": 0.10, "sd": 0.02}, root=root)
    psa.set_range("markov", "Healthy -> Sick", "beta", {"mean": 0.06, "sd": 0.015}, strategy="New drug", root=root)
    psa.set_range("markov", "Sick", "gamma", {"mean": 3000, "sd": 600}, quantity="cost", root=root)
    apart = psa.markov_psa(runs=1000, root=root)
    psa.record(apart, root=root)
    (run,) = [x.run for x in report_results(root=root) if x.run.result_kind == "markov-psa"]

    # Both rates come from one registry: a cohort that progresses faster does so on either strategy.
    r = CliRunner().invoke(app, ["markov", "correlate", "Healthy -> Sick", "Healthy -> Sick", "0.8",
                                 "--other-strategy", "New drug", "--reason", "same registry cohort"])
    assert r.exit_code == 0, r.output
    assert is_stale(run, ProjectPaths(root))  # a correlation ages the PSA
    together = psa.markov_psa(runs=1000, root=root)
    assert together["correlations"] == [{"a": "P(Healthy → Sick)", "b": "P(Healthy → Sick) under New drug",
                                         "rho": 0.8, "reason": "same registry cohort", "weak": True}]
    # Sampled together, the drug's advantage is surer: the rates' noise largely cancels in the difference.
    assert together["p_cost_effective"] > apart["p_cost_effective"]
    m = MK.markov.load(root=root)
    scalar, sets, *_ = psa._mk_inputs(m, psa.ranges("markov", ProjectPaths(root)))
    draws = psa._draws(scalar, sets, 2000, 1, "lhs", psa.correlations("markov", paths=ProjectPaths(root)))
    a, b = sorted(k for k in scalar if "transition" in k)
    assert spearman([d[a] for d in draws], [d[b] for d in draws]) == pytest.approx(0.8, abs=0.05)

    with pytest.raises(ValueError, match="positive definite"):  # an impossible set is refused
        psa.set_correlation("markov", "Healthy -> Sick", "Sick", -0.9, other_quantity="cost", root=root)
        psa.set_correlation("markov", "Healthy -> Sick", "Sick", 0.9, strategy="New drug", other_quantity="cost",
                            root=root)
    with pytest.raises(ValueError, match="no range yet"):
        psa.set_correlation("markov", "Healthy -> Sick", "Healthy -> Dead", 0.5, root=root)
    with pytest.raises(ValueError, match="with itself"):
        psa.set_correlation("markov", "Sick", "Sick", 0.5, quantity="cost", other_quantity="cost", root=root)

    _, spec = export_spec(model_type="markov", root=root)
    assert {(c.target, c.other_strategy, c.rho) for c in spec.markov.correlations} >= {
        ("Healthy -> Sick", "New drug", 0.8)}
    g = gs.analyse("markov", method="morris", n=4, root=root)
    assert any("is ignored" in note for note in g["notes"])

    client = TestClient(create_app(project_root=root))
    listed = client.get("/api/markov/range").json()
    assert len(listed["correlations"]) >= 1
    res = client.post("/api/markov/correlation", json={"target": "Healthy -> Sick", "other": "Healthy -> Sick",
                                                       "other_strategy": "New drug", "clear": True})
    assert res.status_code == 200
    bad = client.post("/api/markov/correlation", json={"target": "Healthy -> Sick", "other": "Sick", "rho": 1.5,
                                                       "other_quantity": "cost"})
    assert bad.status_code == 422
    # Clearing a range takes its correlations with it.
    psa.set_correlation("markov", "Healthy -> Sick", "Sick", 0.3, other_quantity="cost", root=root)
    psa.clear_range("markov", "Sick", quantity="cost", root=root)
    assert psa.correlations("markov", paths=ProjectPaths(root)) == {}
