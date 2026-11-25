"""Markov cohort model: the trace, discounting, half-cycle correction, incremental analysis, surfaces."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import edges as edge_ops
from latris.operations import markov
from latris.operations import nodes as node_ops
from latris.operations.init import init_project
from latris.operations.readiness import assess_readiness


def test_incremental_dominance_and_extended_dominance():
    rows = markov.incremental([
        {"strategy": "A", "cost": 0, "outcome": 0}, {"strategy": "B", "cost": 100, "outcome": 1.0},
        {"strategy": "C", "cost": 300, "outcome": 1.5}, {"strategy": "D", "cost": 400, "outcome": 2.0},
        {"strategy": "E", "cost": 350, "outcome": 0.9},
    ])
    by = {r["strategy"]: r for r in rows}
    assert by["E"]["status"] == "dominated" and by["E"]["versus"] == "B"
    assert by["C"]["status"] == "extendedly dominated"
    assert by["B"]["icer"] == pytest.approx(100)
    assert by["D"]["icer"] == pytest.approx(300) and by["D"]["versus"] == "B"


@pytest.fixture
def project(tmp_path: Path, git_identity, monkeypatch):
    root = tmp_path / "cohort"
    init_project(root, statement="Is the new drug worth its cost?")
    for n in ("Healthy", "Sick", "Dead", "Standard care", "New drug"):
        node_ops.add_node(n, root=root)
    for a, b in (("Healthy", "Sick"), ("Healthy", "Dead"), ("Sick", "Dead")):
        edge_ops.add_edge(a, b, root=root)
    monkeypatch.chdir(root)
    return root


def _tiny(root):
    """Healthy → Dead at 0.5 per cycle; Healthy costs 100 and is worth 1 a year; two yearly cycles."""
    for s in ("Healthy", "Dead"):
        markov.set_element(s, "state", root=root)
    markov.set_transition("Healthy -> Dead", 0.5, root=root)
    markov.set_reward("Healthy", cost=100, utility=1, root=root)
    markov.set_start("Healthy", 1, root=root)
    markov.set_settings(num_cycles=2, discount_rate=0, half_cycle_correction=False, root=root)


def test_trace_by_hand(project):
    _tiny(project)
    r = markov.analyse(root=project)["results"][0]
    assert r["strategy"] == "Base case"
    assert r["cost"] == pytest.approx(150) and r["outcome"] == pytest.approx(1.5)
    assert r["final"] == {"Healthy": pytest.approx(0.25), "Dead": pytest.approx(0.75)}
    markov.set_settings(half_cycle_correction=True, root=project)
    r = markov.analyse(root=project)["results"][0]
    assert r["cost"] == pytest.approx(112.5) and r["outcome"] == pytest.approx(1.125)
    markov.set_settings(half_cycle_correction=False, discount_rate=0.1, outcome_discount_rate=0.0, root=project)
    r = markov.analyse(root=project)["results"][0]
    assert r["cost"] == pytest.approx(100 + 50 / 1.1) and r["outcome"] == pytest.approx(1.5)
    markov.set_settings(time_units="months", root=project)
    r = markov.analyse(root=project)["results"][0]
    assert r["outcome"] == pytest.approx(1.5 / 12)  # utility accrues per year


def _full(root):
    for s in ("Healthy", "Sick", "Dead"):
        markov.set_element(s, "state", root=root)
    for s in ("Standard care", "New drug"):
        markov.set_element(s, "strategy", root=root)
    markov.set_transition("Healthy -> Sick", 0.10, source_id="registry", root=root)
    markov.set_transition("Healthy -> Sick", 0.06, strategy="New drug", source_id="trial", root=root)
    markov.set_transition("Healthy -> Dead", 0.01, root=root)
    markov.set_transition("Sick -> Dead", 0.20, root=root)
    markov.set_reward("Healthy", cost=500, utility=0.95, root=root)
    markov.set_reward("Healthy", cost=1500, strategy="New drug", root=root)  # drug cost while healthy
    markov.set_reward("Sick", cost=3000, utility=0.6, root=root)
    markov.set_reward("Dead", cost=0, utility=0, root=root)
    markov.set_start("Healthy", 1, root=root)
    markov.set_settings(num_cycles=30, wtp=20000, cost_units="£", outcome_units="QALY", root=root)


def test_readiness_and_problems(project):
    assert {"mk_too_few_states", "mk_no_start"} <= {g.gap_type for g in assess_readiness("markov", root=project).gaps}
    _full(project)
    assert assess_readiness("markov", root=project).can_switch
    markov.set_transition("Healthy -> Dead", 0.95, root=project)
    assert {p.gap_type for p in markov.structure_problems(root=project)} == {"mk_prob_sum"}


def test_cost_effectiveness(project):
    _full(project)
    p = markov.analyse(root=project)
    res = {r["strategy"]: r for r in p["results"]}
    assert res["New drug"]["cost"] > res["Standard care"]["cost"]
    assert res["New drug"]["outcome"] > res["Standard care"]["outcome"]
    inc = {r["strategy"]: r for r in p["incremental"]}
    icer = ((res["New drug"]["cost"] - res["Standard care"]["cost"])
            / (res["New drug"]["outcome"] - res["Standard care"]["outcome"]))
    assert inc["New drug"]["icer"] == pytest.approx(icer) and inc["New drug"]["versus"] == "Standard care"
    nmb = {k: 20000 * res[k]["outcome"] - res[k]["cost"] for k in res}
    assert p["choice"] == max(nmb, key=nmb.get)
    assert "ICER of New drug vs Standard care" in markov.describe(p)


def test_setter_rules(project):
    _full(project)
    with pytest.raises(ValueError, match="between two states"):
        node_ops.add_node("Clinic", root=project)
        edge_ops.add_edge("Clinic", "Sick", root=project)
        markov.set_transition("Clinic -> Sick", 0.1, root=project)
    with pytest.raises(ValueError, match="not a strategy"):
        markov.set_transition("Healthy -> Sick", 0.1, strategy="Sick", root=project)
    with pytest.raises(ValueError, match="nothing to set"):
        markov.set_reward("Sick", root=project)
    from latris.operations.view_roles import set_role

    with pytest.raises(ValueError, match="costs and outcomes"):
        set_role("Sick", "markov", "outcome", root=project)


SPEC = """
model_type: markov
factors: [{label: Well}, {label: Ill}, {label: Dead}, {label: Usual care}, {label: Screening}]
links:
  - {from: Well, to: Ill}
  - {from: Ill, to: Dead}
markov:
  elements:
    - {node: Well, type: state}
    - {node: Ill, type: state}
    - {node: Dead, type: state}
    - {node: Usual care, type: strategy}
    - {node: Screening, type: strategy}
  settings: {num_cycles: 20, wtp: 30000, cost_units: £, outcome_units: QALY}
  transitions:
    - {link: Well -> Ill, probability: 0.05, source: cohort-study, verified: true}
    - {link: Well -> Ill, probability: 0.04, strategy: Screening}
    - {link: Ill -> Dead, probability: 0.15}
  rewards:
    - {state: Well, utility: 1, cost: 0}
    - {state: Well, strategy: Screening, cost: 200}
    - {state: Ill, utility: 0.5, cost: 5000}
    - {state: Dead, utility: 0, cost: 0}
  start: [{state: Well, proportion: 1}]
analyses:
  - kind: markov_analyse
"""


@pytest.fixture
def built(tmp_path: Path, git_identity, monkeypatch):
    from latris.operations.build import build_from_spec, load_spec

    root = tmp_path / "built"
    init_project(root, statement="Screen?")
    monkeypatch.chdir(root)
    return root, build_from_spec(load_spec(SPEC), root=root)


def test_build_spec_share_link_report(built, tmp_path, git_identity):
    from latris.exporters.markdown import render
    from latris.exporters.mermaid import render as mermaid
    from latris.operations.build import build_from_spec
    from latris.operations.interpret import extract_claims
    from latris.operations.share_link import export_spec
    from latris.repo.layout import ProjectPaths

    root, result = built
    assert result.analyses and not result.notes
    p = markov.analyse(root=root)
    assert {r["strategy"] for r in p["results"]} == {"Usual care", "Screening"} and p["choice"]
    _, spec = export_spec(model_type="markov", root=root)
    assert spec.markov and spec.markov.settings.wtp == 30000 and len(spec.markov.transitions) == 3
    copy = tmp_path / "copy"
    init_project(copy, statement="copy")
    build_from_spec(spec, root=copy)
    assert markov.analyse(root=copy)["results"] == p["results"]
    md = render(ProjectPaths(root), model_type="markov", ai=False)
    assert "Markov cohort model: costs, outcomes and cost-effectiveness" in md and "Incremental analysis" in md
    assert "Briggs" in md
    src = mermaid(ProjectPaths(root), model_type="markov")
    assert '[["Dead"]]' in src and '|"0.05"|' in src
    sens = extract_claims("sensitivity", "markov", root=root)
    assert any("ICER is the threshold" in c for c in sens) or any("Never" in c for c in
                                                                  extract_claims("implications", "markov", root=root))
    answer = extract_claims("answer_to_question", "markov", root=root)
    assert any("choose" in c for c in answer)


def test_routes_and_cli(built):
    from fastapi.testclient import TestClient
    from typer.testing import CliRunner

    from latris.cli.app import app
    from latris.server.app import create_app

    root, _ = built
    c = TestClient(create_app(project_root=root))
    assert c.get("/api/markov/check").json()["ready"] is True
    m = c.get("/api/markov/model").json()
    assert "state" in m["elements"].values() and m["transitions"] and m["start"]
    assert c.post("/api/markov/settings", json={"time_units": "fortnights"}).status_code == 422
    r = c.post("/api/markov/analyse", json={"record": False}).json()
    assert r["commit_sha"] is None and r["result"]["choice"]
    runner = CliRunner()
    assert "Transitions per cycle" in runner.invoke(app, ["markov", "show"]).output
    out = runner.invoke(app, ["markov", "analyse"])
    assert out.exit_code == 0 and "Discounted per person" in out.output and "recorded" in out.output
    assert runner.invoke(app, ["markov", "check"]).exit_code == 0


def test_the_horizon_reads_as_a_person_would_say_it():
    from latris.operations.markov import horizon

    assert horizon({"num_cycles": 30, "cycle_length": 1, "time_units": "years"}) == "30 cycles of 1 year"
    assert horizon({"num_cycles": 12, "cycle_length": 3, "time_units": "months"}) == "12 cycles of 3 months"
    assert horizon({"num_cycles": 1, "cycle_length": 0.5, "time_units": "years"}) == "1 cycle of 0.5 years"
