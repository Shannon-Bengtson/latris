"""Monte Carlo uncertainty on fault trees, bow-ties and event trees."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from latris.operations import bow_tie as bt
from latris.operations import edges as edge_ops
from latris.operations import event_tree as et
from latris.operations import fault_tree as ft
from latris.operations import nodes as node_ops
from latris.operations import risk_uncertainty as ru
from latris.operations.init import init_project
from tests.operations import test_bow_tie as BT
from tests.operations import test_event_tree as ET
from tests.operations import test_fault_tree as FT


def test_error_factor_lognormal_has_that_median_and_95th_percentile():
    from latris.operations._sampling import Sampler
    from latris.schema.attributes import ParameterUncertainty

    params = ru.error_factor_lognormal(1e-3, 10)
    s = Sampler(ParameterUncertainty(target_id="x", distribution="lognormal", params=params))
    assert s.quantile(0.5) == pytest.approx(1e-3, rel=1e-6)
    assert s.quantile(0.95) == pytest.approx(1e-2, rel=1e-6)
    with pytest.raises(ValueError, match="greater than 1"):
        ru.error_factor_lognormal(1e-3, 1)


# ── fault tree ──────────────────────────────────────────────────────


@pytest.fixture
def cooling(tmp_path: Path, git_identity, monkeypatch):
    root = tmp_path / "cooling"
    init_project(root, statement="How likely is a loss of cooling?")
    for label in FT.EVENTS:
        node_ops.add_node(label, kind="event", root=root)
    for a, b in FT.LINKS:
        edge_ops.add_edge(a, b, kind="logical", root=root)
    FT._classify(root)
    monkeypatch.chdir(root)
    return root


def test_ft_monte_carlo_matches_independent_sampling(cooling):
    root = cooling
    ru.set_uncertainty("fault_tree", "Pump A fails", "lognormal", {"median": 0.01, "error_factor": 3}, root=root)
    ru.set_uncertainty("fault_tree", "Pump B fails", "uniform", {"min": 0.01, "max": 0.03}, root=root)
    p = ru.monte_carlo("fault_tree", runs=20000, seed=1, root=root)
    (top,) = [o for o in p["outputs"] if o["output"] == "Loss of cooling"]
    point = ft.analyse(root=root)["probability"]["exact"]
    assert top["point"] == pytest.approx(point)
    # Independent estimate of the mean: power-loss term exact, pumps by numpy sampling.
    rng = np.random.default_rng(0)
    pa_par = ru.error_factor_lognormal(0.01, 3)
    sig = math.sqrt(math.log(1 + (pa_par["sd"] / pa_par["mean"]) ** 2))
    pa = np.minimum(np.exp(rng.normal(math.log(0.01), sig, 400000)), 1)
    pb = rng.uniform(0.01, 0.03, 400000)
    q = 1e-3
    power = 3 * q**2 * (1 - q) + q**3
    expect = np.mean(1 - (1 - pa * pb) * (1 - power))
    assert top["mean"] == pytest.approx(expect, rel=0.02)
    assert top["mean"] > top["point"]  # skewed inputs: the point estimate is below the mean
    assert top["p5"] < top["p50"] < top["p95"]
    assert {d["input"] for d in p["drivers"]} == {"Pump A fails", "Pump B fails"}
    assert p["drivers"][0]["input"] == "Pump A fails"  # the wider range drives the spread
    assert set(p["fixed"]) == {"Supply 1 fails", "Supply 2 fails", "Supply 3 fails"}
    assert "Loss of cooling: 90% of 20000 runs" in ru.describe(p)


def test_seed_reproduces_and_ranges_are_checked(cooling):
    root = cooling
    ru.set_uncertainty("fault_tree", "Pump A fails", "triangular", {"min": 0.005, "mode": 0.01, "max": 0.05},
                       root=root)
    a = ru.monte_carlo("fault_tree", runs=500, seed=7, root=root)
    b = ru.monte_carlo("fault_tree", runs=500, seed=7, root=root)
    assert a["outputs"] == b["outputs"]
    with pytest.raises(ValueError, match="lies outside"):
        ru.set_uncertainty("fault_tree", "Pump B fails", "uniform", {"min": 0.1, "max": 0.2}, root=root)
    with pytest.raises(ValueError, match="must lie in"):
        ru.set_uncertainty("fault_tree", "Pump B fails", "uniform", {"min": 0.01, "max": 1.5}, root=root)
    with pytest.raises(ValueError, match="basic or undeveloped"):
        ru.set_uncertainty("fault_tree", "Power lost", "uniform", {"min": 0.0, "max": 0.1}, root=root)
    # normal on a probability is truncated to [0, 1]
    e, _ = ru.set_uncertainty("fault_tree", "Pump B fails", "normal", {"mean": 0.02, "sd": 0.02}, root=root)
    assert e.params["min"] == 0.0 and e.params["max"] == 1.0
    ru.clear_uncertainty("fault_tree", "Pump B fails", root=root)
    with pytest.raises(ValueError, match="no uncertainty range"):
        ru.clear_uncertainty("fault_tree", "Pump B fails", root=root)


def test_nothing_uncertain_refuses(cooling):
    with pytest.raises(ValueError, match="no input has an uncertainty range"):
        ru.monte_carlo("fault_tree", runs=100, root=cooling)


def test_record_goes_stale_when_a_range_changes(cooling):
    from latris.operations.analysis_results import report_results

    root = cooling
    ru.set_uncertainty("fault_tree", "Pump A fails", "uniform", {"min": 0.005, "max": 0.02}, root=root)
    sha, run_id = ru.record(ru.monte_carlo("fault_tree", runs=200, root=root), root=root)
    (r,) = [x for x in report_results(root=root) if x.run.result_kind == "ft-monte-carlo"]
    assert not r.stale
    ru.set_uncertainty("fault_tree", "Pump A fails", "uniform", {"min": 0.005, "max": 0.03}, root=root)
    (r,) = [x for x in report_results(root=root) if x.run.result_kind == "ft-monte-carlo"]
    assert r.stale


# ── bow-tie ─────────────────────────────────────────────────────────


@pytest.fixture
def gas(tmp_path: Path, git_identity, monkeypatch):
    root = tmp_path / "gas"
    init_project(root, statement="How well protected are we?")
    for label in BT.ELEMENTS:
        node_ops.add_node(label, kind="event", root=root)
    for a, b in BT.LINKS:
        edge_ops.add_edge(a, b, root=root)
    BT._classify(root)
    BT._quantify(root)
    monkeypatch.chdir(root)
    return root


def test_bowtie_monte_carlo(gas):
    root = gas
    ru.set_uncertainty("bow_tie", "Pressure relief valve", "lognormal", {"median": 0.01, "error_factor": 10},
                       root=root)
    ru.set_uncertainty("bow_tie", "Overpressure", "uniform", {"min": 0.2, "max": 0.8}, root=root)
    with pytest.raises(ValueError, match="neither a barrier nor a threat"):
        ru.set_uncertainty("bow_tie", "Fire", "uniform", {"min": 0.0, "max": 1.0}, root=root)
    p = ru.monte_carlo("bow_tie", runs=4000, seed=3, root=root)
    point = bt.analyse(root=root)["frequency"]
    top = next(o for o in p["outputs"] if o["output"] == p["primary"])
    assert p["primary"] == "Loss of containment (per year)"
    assert top["point"] == pytest.approx(point["top"])
    # f_top is linear in each input here; the mean follows the inputs' means (lognormal mean > median)
    pr = ru.error_factor_lognormal(0.01, 10)["mean"]
    expect = point["top"] - 0.5 * 0.01 + 0.5 * pr  # overpressure mean 0.5 unchanged, relief valve mean pr
    assert top["mean"] == pytest.approx(expect, rel=0.05)
    fire = next(o for o in p["outputs"] if o["output"] == "Fire (per year)")
    assert fire["point"] == pytest.approx(point["consequences"]["Fire"])
    assert {d["input"] for d in p["drivers"]} == {"Pressure relief valve (PFD)", "Overpressure (frequency)"}
    q = ru.monte_carlo("bow_tie", runs=200, output="Fire", root=root)
    assert q["primary"] == "Fire (per year)"


# ── event tree ──────────────────────────────────────────────────────


@pytest.fixture
def release(tmp_path: Path, git_identity, monkeypatch):
    root = tmp_path / "release"
    init_project(root, statement="How often does a gas release end in a fire?")
    for label in ET.ELEMENTS:
        node_ops.add_node(label, kind="event", root=root)
    ET._build(root)
    ET._quantify(root)
    monkeypatch.chdir(root)
    return root


def test_event_tree_monte_carlo_with_conditional_probability(release):
    root = release
    ru.set_uncertainty("event_tree", "Ignition", "beta", {"alpha": 3, "beta": 7}, given=[("Gas detected", "no")],
                       root=root)
    ru.set_uncertainty("event_tree", "Gas release", "lognormal", {"median": 0.02, "error_factor": 3}, root=root)
    with pytest.raises(ValueError, match="no probability given"):
        ru.set_uncertainty("event_tree", "Ignition", "uniform", {"min": 0.0, "max": 1.0},
                           given=[("Isolation succeeds", "no")], root=root)
    p = ru.monte_carlo("event_tree", runs=4000, seed=5, output="Fire", root=root)
    point = {d["end_state"]: d["frequency"] for d in et.analyse(root=root)["end_states"]}
    fire = next(o for o in p["outputs"] if o["output"] == "Fire (per year)")
    assert fire["point"] == pytest.approx(point["Fire"])
    labels = {d["input"] for d in p["drivers"]}
    assert labels == {"P(Ignition=yes | Gas detected=no)", "Gas release (frequency)"}
    # frequency and beta independent: E[fire] = E[f] · (P(det)·P(no iso)·0.1 + P(no det)·E[beta])
    f_mean = ru.error_factor_lognormal(0.02, 3)["mean"]
    expect = f_mean * (0.9 * 0.05 * 0.1 + 0.1 * 0.3)
    assert fire["mean"] == pytest.approx(expect, rel=0.05)
    total = sum(o["mean"] for o in p["outputs"])
    assert total == pytest.approx(f_mean, rel=0.05)  # the end states partition the initiator's frequency


# ── surfaces ────────────────────────────────────────────────────────


def test_report_claims_spec_round_trip_cli_and_routes(release):
    from fastapi.testclient import TestClient
    from typer.testing import CliRunner

    from latris.cli.app import app
    from latris.exporters.markdown import render
    from latris.operations.build import build_from_spec
    from latris.operations.formalisms import for_analysis
    from latris.operations.interpret import extract_claims
    from latris.operations.share_link import export_spec
    from latris.repo.layout import ProjectPaths
    from latris.server.app import create_app

    root = release
    runner = CliRunner()
    r = runner.invoke(app, ["et", "uncertainty", "Ignition", "--given", "Gas detected=no", "--median", "0.3",
                            "--error-factor", "2"])
    assert r.exit_code == 0, r.output
    r = runner.invoke(app, ["et", "uncertainty", "Gas release", "uniform", "--min", "0.01", "--max", "0.04",
                            "--verified"])
    assert r.exit_code == 0, r.output
    r = runner.invoke(app, ["et", "monte-carlo", "--runs", "500", "--output", "Fire"])
    assert r.exit_code == 0, r.output
    assert "What drives Fire (per year)" in r.output

    md = render(ProjectPaths(root), model_type="event_tree", ai=False)
    assert "Event tree: uncertainty (Monte Carlo)" in md and "Rank correlation" in md
    assert "Monte Carlo propagation of parameter uncertainty" in md  # foundations
    sens = extract_claims("sensitivity", "event_tree", root=root)
    assert any(c.startswith("Fire (per year): 90% of 500 runs") for c in sens)
    gaps = extract_claims("open_questions", "event_tree", root=root)
    assert any("haven't been checked" in c for c in gaps)

    _, spec = export_spec(model_type="event_tree", root=root)
    assert {(u.node, tuple(u.given.items()), u.verified) for u in spec.event_tree.uncertainty} == {
        ("Ignition", (("Gas detected", "no"),), False), ("Gas release", (), True)}
    (mc,) = [a for a in spec.analyses if a.kind == "et_monte_carlo"]
    assert (mc.runs, mc.target) == (500, "Fire (per year)")
    assert for_analysis("et_monte_carlo").run(mc, root)

    # rebuild from the exported spec elsewhere: ranges come back
    other = root.parent / "rebuilt"
    from latris.operations.init import init_project

    init_project(other, statement="Q?")
    built = build_from_spec(spec, root=other)
    assert built.analyses
    assert len(ru.specs("event_tree", ProjectPaths(other))) == 2

    client = TestClient(create_app(project_root=root))
    r = client.post("/api/et/uncertainty", json={"target": "Ignition", "distribution": "uniform",
                                                 "params": {"min": 0.0, "max": 0.05}})
    assert r.status_code == 422 and "lies outside" in r.json()["detail"]
    r = client.post("/api/et/uncertainty", json={"target": "Ignition", "params": {"median": 0.1,
                                                                                    "error_factor": 3}})
    assert r.status_code == 200 and r.json()["result"]["distribution"] == "lognormal"
    listed = client.get("/api/et/uncertainty").json()
    assert listed["count"] == 3 and {u["distribution"] for u in listed["uncertainty"]} >= {"lognormal"}
    assert client.get("/api/ft/uncertainty").json()["count"] == 0  # each type lists only its own
    r = client.post("/api/et/monte-carlo", json={"runs": 300, "record": False})
    assert r.status_code == 200 and r.json()["commit_sha"] is None
    assert client.post("/api/ft/monte-carlo", json={"runs": 300}).status_code == 422  # no fault tree here
