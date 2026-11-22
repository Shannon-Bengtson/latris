"""Global sensitivity analysis: Sobol indices and Morris screening (operations/global_sensitivity.py)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from latris.operations import global_sensitivity as gs
from latris.operations import psa
from latris.repo.layout import ProjectPaths
from tests.operations import test_decision_tree as DT
from tests.operations import test_markov as MK

dt_project = DT.project
mk_project = MK.project


def _ishigami(u):
    x = -math.pi + 2 * math.pi * u
    return (np.sin(x[:, 0]) + 7 * np.sin(x[:, 1]) ** 2 + 0.1 * x[:, 2] ** 4 * np.sin(x[:, 0]))[:, None]


def test_sobol_recovers_the_ishigami_indices():
    a, b = 7, 0.1
    v = a**2 / 8 + b * math.pi**4 / 5 + b**2 * math.pi**8 / 18 + 0.5
    v1, v2, v13 = 0.5 * (1 + b * math.pi**4 / 5) ** 2, a**2 / 8, b**2 * math.pi**8 * (1 / 18 - 1 / 50)
    r = gs.sobol_indices(_ishigami, 3, 4096, seed=1)
    assert r["S1"][:, 0] == pytest.approx([v1 / v, v2 / v, 0.0], abs=0.03)
    assert r["ST"][:, 0] == pytest.approx([(v1 + v13) / v, v2 / v, v13 / v], abs=0.03)
    assert r["runs"] == 4096 * 5
    assert (r["ST_conf"] > 0).all() and (r["ST_conf"] < 0.1).all()


def test_morris_gives_slopes_of_a_linear_model_and_flags_interaction():
    r = gs.morris_effects(lambda u: (3 * u[:, 0] + u[:, 1])[:, None], 3, 10, seed=1)
    assert r["mu_star"][:, 0] == pytest.approx([3, 1, 0]) and r["sigma"][:, 0] == pytest.approx([0, 0, 0], abs=1e-9)
    assert r["runs"] == 40
    r = gs.morris_effects(lambda u: (u[:, 0] * u[:, 1])[:, None], 2, 30, seed=1)
    assert (r["sigma"][:, 0] > 0.3 * r["mu_star"][:, 0]).all()  # a product: each effect depends on the other


def test_decision_tree_indices_match_the_closed_form(dt_project):
    DT._build(dt_project)
    with pytest.raises(ValueError, match="at least two inputs"):
        gs.analyse("decision_tree", root=dt_project)
    psa.set_range("decision_tree", "Launched, high", "normal", {"mean": 500, "sd": 100}, root=dt_project)
    psa.set_range("decision_tree", "Launched, low", "normal", {"mean": -200, "sd": 60}, root=dt_project)
    p = gs.analyse("decision_tree", n=2048, root=dt_project)
    # License − Launch = 90 − (0.4·X + 0.6·Y): additive, so S1 = ST = each term's share of the variance.
    vx, vy = 0.16 * 100**2, 0.36 * 60**2
    assert p["primary"] == "advantage of License over Launch"
    main = p["outputs"][0]
    assert main["output"] == p["primary"] and main["variance"] == pytest.approx(vx + vy, rel=0.05)
    by = {r["input"]: r for r in main["indices"]}
    for name, share in (("Launched, high (payoff)", vx / (vx + vy)), ("Launched, low (payoff)", vy / (vx + vy))):
        assert by[name]["S1"] == pytest.approx(share, abs=0.04) and by[name]["ST"] == pytest.approx(share, abs=0.04)
    assert main["sum_S1"] == pytest.approx(1, abs=0.05)
    assert {o["output"] for o in p["outputs"]} >= {"License (expected value)", "Launch (expected value)"}
    lic = next(o for o in p["outputs"] if o["output"] == "License (expected value)")
    assert lic["variance"] == pytest.approx(0, abs=1e-9)  # nothing licensing depends on is uncertain
    assert "Licensed, high (payoff)" in p["fixed"]
    assert gs.describe(p).startswith("Sobol indices for advantage of License over Launch over 8192 runs")
    m = gs.analyse("decision_tree", method="morris", n=10, root=dt_project)
    by = {r["input"]: r for r in m["outputs"][0]["indices"]}
    assert by["Launched, high (payoff)"]["sigma"] == pytest.approx(0, abs=1e-6)  # linear: no interaction

    psa.set_range("decision_tree", "Demand if launched", "dirichlet", {"n": 20}, root=dt_project)
    p = gs.analyse("decision_tree", method="morris", n=4, root=dt_project)
    assert any("Dirichlet" in note for note in p["notes"])
    for bad, msg in (({"method": "sobol", "n": 100}, "power of two"), ({"method": "morris", "n": 2}, "at least 4"),
                     ({"method": "fast"}, "method must be"), ({"variable": "X"}, "system dynamics")):
        with pytest.raises(ValueError, match=msg):
            gs.analyse("decision_tree", root=dt_project, **bad)
    with pytest.raises(ValueError, match="no single output"):
        gs.analyse("decision_tree", method="morris", n=4, output="Nothing like it", root=dt_project)


def test_markov_headline_is_the_net_benefit(mk_project):
    MK._full(mk_project)
    psa.set_range("markov", "Healthy -> Sick", "beta", {"mean": 0.06, "sd": 0.015}, strategy="New drug",
                  root=mk_project)
    psa.set_range("markov", "Sick", "gamma", {"mean": 3000, "sd": 600}, quantity="cost", root=mk_project)
    p = gs.analyse("markov", n=64, root=mk_project)
    assert p["primary"] == "net monetary benefit of New drug over Standard care"
    top = p["outputs"][0]["indices"][0]
    assert top["input"] == "P(Healthy → Sick) under New drug" and top["ST"] > 0.9
    sc = next(o for o in p["outputs"] if o["output"] == "Standard care QALY")
    assert sc["variance"] == pytest.approx(0, abs=1e-12)  # its costs vary, its outcome doesn't


def test_surfaces(dt_project):
    from fastapi.testclient import TestClient
    from typer.testing import CliRunner

    from latris.cli.app import app
    from latris.exporters.markdown import render
    from latris.operations.build import build_from_spec
    from latris.operations.formalisms import for_analysis
    from latris.operations.init import init_project
    from latris.operations.interpret import extract_claims
    from latris.operations.share_link import export_spec
    from latris.server.app import create_app

    root = dt_project
    DT._build(root)
    psa.set_range("decision_tree", "Launched, high", "normal", {"mean": 500, "sd": 100}, root=root)
    psa.set_range("decision_tree", "Demand if launched -> Launched, high", "beta", {"mean": 0.4, "sd": 0.1},
                  root=root)
    r = CliRunner().invoke(app, ["analyse", "global-sensitivity", "decision_tree", "-n", "64"])
    assert r.exit_code == 0, r.output
    assert "Global sensitivity of advantage of License over Launch" in r.output and "Total (ST)" in r.output

    md = render(ProjectPaths(root), model_type="decision_tree", ai=False, chart_markers=True)
    assert "Decision tree: global sensitivity of advantage of License over Launch" in md
    assert "gsa-indices" in md and "Global sensitivity analysis: Sobol indices and Morris screening" in md
    assert any(c.startswith("Sobol indices for advantage") for c in extract_claims("sensitivity", "decision_tree",
                                                                                 root=root))
    assert any("nobody has checked" in c for c in extract_claims("open_questions", "decision_tree", root=root))

    _, spec = export_spec(model_type="decision_tree", root=root)
    (a,) = [x for x in spec.analyses if x.kind == "dt_gsa"]
    assert (a.method, a.n, a.output) == ("sobol", 64, "advantage of License over Launch")
    assert for_analysis("dt_gsa").run(a, root)
    other = root.parent / "rebuilt"
    init_project(other, statement="Q?")
    assert any(x.startswith("analysis-run") for x in build_from_spec(spec, root=other).analyses)

    client = TestClient(create_app(project_root=root))
    res = client.post("/api/analysis/global-sensitivity", json={"model_type": "decision_tree", "method": "morris",
                                                                "n": 4, "record": False})
    assert res.status_code == 200 and res.json()["result"]["method"] == "morris" and res.json()["commit_sha"] is None
    bad = client.post("/api/analysis/global-sensitivity", json={"model_type": "cld"})
    assert bad.status_code == 422
