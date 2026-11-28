"""Decision trees: rollback, EVPI, thresholds, structure checks and the surfaces."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import decision_tree as dt
from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations.init import init_project
from latris.operations.readiness import assess_readiness

# Launch, license or do nothing; demand High (0.4) or Low (0.6) whichever you choose.
NODES = {
    "Strategy": "decision",
    "Demand if launched": "chance", "Demand if licensed": "chance",
    "Launched, high": "terminal", "Launched, low": "terminal",
    "Licensed, high": "terminal", "Licensed, low": "terminal", "Do nothing": "terminal",
}
PAYOFFS = {"Launched, high": 500, "Launched, low": -200, "Licensed, high": 150, "Licensed, low": 50, "Do nothing": 0}
BRANCHES = [
    ("Strategy", "Demand if launched", "Launch", None), ("Strategy", "Demand if licensed", "License", None),
    ("Strategy", "Do nothing", "Do nothing", None),
    ("Demand if launched", "Launched, high", "High", 0.4), ("Demand if launched", "Launched, low", "Low", 0.6),
    ("Demand if licensed", "Licensed, high", "High", 0.4), ("Demand if licensed", "Licensed, low", "Low", 0.6),
]


@pytest.fixture
def project(tmp_path: Path, git_identity, monkeypatch):
    root = tmp_path / "launch"
    init_project(root, statement="Should we launch the product ourselves, license it, or do nothing?")
    for n in NODES:
        node_ops.add_node(n, root=root)
    for a, b, _, _ in BRANCHES:
        edge_ops.add_edge(a, b, kind="conditional", root=root)
    monkeypatch.chdir(root)
    return root


def _build(root, *, probs=True, group=True):
    for n, k in NODES.items():
        dt.set_element(n, k, root=root)
    for a, b, label, p in BRANCHES:
        dt.set_branch(f"{a} -> {b}", label=label, **({"probability": p} if (p is not None and probs) else {}),
                      root=root)
    for n, v in PAYOFFS.items():
        dt.set_payoff(n, v, root=root)
    if group:
        dt.set_uncertainty("Demand if launched", "Demand", root=root)
        dt.set_uncertainty("Demand if licensed", "Demand", root=root)
    dt.set_settings(objective="maximise", units="$k", root=root)


def test_readiness_and_structure(project):
    assert not assess_readiness("decision_tree", root=project).can_switch
    _build(project, probs=False)
    kinds = {g.gap_type for g in assess_readiness("decision_tree", root=project).gaps}
    assert kinds == {"dt_no_probability"}
    _build(project)
    assert assess_readiness("decision_tree", root=project).can_switch
    dt.set_branch("Demand if launched -> Launched, low", probability=0.5, root=project)
    assert {p.gap_type for p in dt.structure_problems(root=project)} == {"dt_probabilities_sum"}


def test_not_a_tree(project):
    _build(project)
    edge_ops.add_edge("Demand if licensed", "Do nothing", root=project)
    assert "dt_not_tree" in {p.gap_type for p in dt.structure_problems(root=project)}


def _problems(root) -> list[tuple[str | None, str]]:
    t = dt.load_tree(root=root)
    return [(t.labels.get(p.target_id or "", None), p.gap_type) for p in t.problems]


def test_structure_problems_in_order(project):
    """Each structure problem a tree can have, in the order they're reported, and when it has a root."""
    assert _problems(project) == [(None, "dt_no_root")]  # no nodes typed yet
    _build(project)
    for n in ("Second choice", "Loose chance"):
        node_ops.add_node(n, root=project)
    dt.set_element("Second choice", "decision", root=project)  # a second root, with no branches
    dt.set_element("Loose chance", "chance", root=project)
    edge_ops.add_edge("Strategy", "Loose chance", kind="conditional", root=project)  # a chance node, no branches
    edge_ops.add_edge("Launched, high", "Demand if licensed", kind="conditional", root=project)  # past a terminal
    dt.set_payoff("Do nothing", 0, root=project)
    t = dt.load_tree(root=project)
    assert t.root is None
    assert _problems(project) == [
        ("Strategy", "dt_many_roots"), ("Demand if licensed", "dt_not_tree"),
        ("Launched, high", "dt_terminal_has_children"), ("Second choice", "dt_dead_end"),
        ("Loose chance", "dt_dead_end")]


def test_a_loop_has_no_root(project):
    _build(project)
    edge_ops.add_edge("Do nothing", "Strategy", kind="conditional", root=project)  # back to the top
    problems = _problems(project)
    assert problems[0] == (None, "dt_no_root") and (None, "dt_cycle") in problems
    assert dt.load_tree(root=project).root is None


def test_terminal_without_payoff_and_no_decision(project):
    for n in ("Demand if launched", "Launched, high", "Launched, low"):
        dt.set_element(n, NODES[n], root=project)
    for a, b, label, p in BRANCHES[3:5]:
        dt.set_branch(f"{a} -> {b}", label=label, probability=p, root=project)
    dt.set_payoff("Launched, high", 500, root=project)
    assert _problems(project) == [(None, "dt_no_decision"), ("Launched, low", "dt_no_payoff")]


def test_rollback_evpi_thresholds(project):
    _build(project)
    p = dt.analyse(root=project)
    ev = {o["option"]: o["ev"] for o in p["options"]}
    assert ev == {"Launch": pytest.approx(80), "License": pytest.approx(90), "Do nothing": 0}
    assert p["best"] == "License" and p["ev"] == pytest.approx(90)
    demand = p["evpi"]["per_uncertainty"][0]
    assert demand["uncertainty"] == "Demand" and demand["evpi"] == pytest.approx(140)
    assert demand["by_state"]["High"]["choice"] == "Launch" and demand["by_state"]["Low"]["choice"] == "License"
    th = p["thresholds"][0]
    assert th["state"] == "High" and th["up"]["p"] == pytest.approx(5 / 12, abs=1e-6)
    assert th["up"]["option"] == "Launch" and th["down"] is None
    assert "perfect information on Demand is worth up to 140 $k" in dt.describe(p)
    assert p["unverified_on_path"]


def test_inconsistent_uncertainty_not_priced(project):
    _build(project)
    dt.set_branch("Demand if licensed -> Licensed, high", probability=0.5, root=project)
    dt.set_branch("Demand if licensed -> Licensed, low", probability=0.5, root=project)
    p = dt.analyse(root=project)
    assert p["evpi"]["per_uncertainty"] == [] and "depends on the choice" in p["evpi"]["skipped"][0]


def test_ungrouped_uncertainties_and_joint(project):
    _build(project, group=False)
    p = dt.analyse(root=project)
    names = {x["uncertainty"] for x in p["evpi"]["per_uncertainty"]}
    assert names == {"Demand if launched", "Demand if licensed"}
    assert p["evpi"]["all"] is not None and p["evpi"]["all"]["evpi"] >= max(
        x["evpi"] for x in p["evpi"]["per_uncertainty"])


def test_minimise_and_branch_values(project):
    _build(project)
    dt.set_settings(objective="minimise", root=project)
    assert dt.analyse(root=project)["best"] == "Do nothing"
    dt.set_settings(objective="maximise", root=project)
    dt.set_branch("Strategy -> Demand if licensed", value=-20, root=project)  # a licensing fee
    p = dt.analyse(root=project)
    assert {o["option"]: o["ev"] for o in p["options"]}["License"] == pytest.approx(70)
    assert p["best"] == "Launch"


def test_setter_rules(project):
    _build(project)
    with pytest.raises(ValueError, match="only branches from a chance node"):
        dt.set_branch("Strategy -> Do nothing", probability=0.5, root=project)
    with pytest.raises(ValueError, match="not a terminal node"):
        dt.set_payoff("Strategy", 1, root=project)
    with pytest.raises(ValueError, match="nothing to set"):
        dt.set_branch("Strategy -> Do nothing", root=project)
    from latris.operations.view_roles import set_role

    with pytest.raises(ValueError, match="best choice"):
        set_role("Strategy", "decision_tree", "outcome", root=project)


SPEC = """
model_type: decision_tree
factors: [{label: Strategy}, {label: Demand}, {label: Launch high}, {label: Launch low}, {label: Stay out}]
links:
  - {from: Strategy, to: Demand, kind: conditional}
  - {from: Strategy, to: Stay out, kind: conditional}
  - {from: Demand, to: Launch high, kind: conditional}
  - {from: Demand, to: Launch low, kind: conditional}
decision_tree:
  objective: maximise
  units: $k
  elements:
    - {node: Strategy, type: decision}
    - {node: Demand, type: chance}
    - {node: Launch high, type: terminal}
    - {node: Launch low, type: terminal}
    - {node: Stay out, type: terminal}
  branches:
    - {link: Strategy -> Demand, label: Launch, value: -50, source: capex-estimate}
    - {link: Demand -> Launch high, label: High, probability: 0.3, source: market-survey}
    - {link: Demand -> Launch low, label: Low, probability: 0.7}
  payoffs:
    - {node: Launch high, value: 400, verified: true}
    - {node: Launch low, value: 20}
    - {node: Stay out, value: 0}
  uncertainties:
    - {node: Demand, name: Market demand}
analyses:
  - kind: dt_analyse
"""


@pytest.fixture
def built(tmp_path: Path, git_identity, monkeypatch):
    from latris.operations.build import build_from_spec, load_spec

    root = tmp_path / "built"
    init_project(root, statement="Launch?")
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
    p = dt.analyse(root=root)
    assert p["best"] == "Launch" and p["ev"] == pytest.approx(0.3 * 400 + 0.7 * 20 - 50)
    _, spec = export_spec(model_type="decision_tree", root=root)
    assert spec.decision_tree and spec.decision_tree.units == "$k" and len(spec.decision_tree.branches) == 3
    assert spec.decision_tree.elements and spec.decision_tree.uncertainties[0].name == "Market demand"
    copy = tmp_path / "copy"
    init_project(copy, statement="copy")
    build_from_spec(spec, root=copy)
    assert dt.analyse(root=copy)["options"] == p["options"]
    md = render(ProjectPaths(root), model_type="decision_tree", ai=False)
    assert "Decision tree: best choice and the value of information" in md and "Raiffa" in md
    src = mermaid(ProjectPaths(root), model_type="decision_tree")
    assert src.startswith("flowchart LR") and "linkStyle" in src and '|"High 0.3"|' in src
    impl = extract_claims("implications", "decision_tree", root=root)
    assert any("Finding out Market demand before choosing is worth up to" in c for c in impl)
    answer = extract_claims("answer_to_question", "decision_tree", root=root)
    assert any("Best first choice: Launch" in c for c in answer)


def test_routes_and_cli(built):
    from fastapi.testclient import TestClient
    from typer.testing import CliRunner

    from latris.cli.app import app
    from latris.server.app import create_app

    root, _ = built
    c = TestClient(create_app(project_root=root))
    assert c.get("/api/dt/check").json()["ready"] is True
    t = c.get("/api/dt/tree").json()
    assert "decision" in t["elements"].values() and t["branches"] and t["payoffs"]
    assert t["settings"]["objective"] in ("maximise", "minimise")
    assert c.post("/api/dt/branch", json={"link": "Strategy -> Stay out", "probability": 0.1}).status_code == 422
    r = c.post("/api/dt/analyse", json={"record": False}).json()
    assert r["commit_sha"] is None and r["result"]["best"] == "Launch"
    runner = CliRunner()
    out = runner.invoke(app, ["dt", "show"])
    assert out.exit_code == 0 and "□ Strategy" in out.output and "→ [Launch" in out.output
    out = runner.invoke(app, ["dt", "analyse"])
    assert out.exit_code == 0 and "Value of perfect information" in out.output and "recorded" in out.output
    assert runner.invoke(app, ["dt", "check"]).exit_code == 0
