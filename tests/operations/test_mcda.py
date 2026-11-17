"""MCDA: values, ranking, dominance, rank-reversal weights, and the project surfaces."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import mcda
from latris.operations import nodes as node_ops
from latris.operations.init import init_project
from latris.operations.readiness import assess_readiness

# Choosing a site: cost (lower better, $m), travel time (lower better, min), capacity (higher better, beds).
SCORES = {
    "Site A": {"Cost": 40, "Travel time": 25, "Capacity": 300},
    "Site B": {"Cost": 55, "Travel time": 15, "Capacity": 320},
    "Site C": {"Cost": 60, "Travel time": 30, "Capacity": 250},
}


def test_values_rank_reversal_kernel():
    opts, crits = ["a", "b"], ["x", "y"]
    v = {("a", "x"): 1.0, ("a", "y"): 0.0, ("b", "x"): 0.0, ("b", "y"): 1.0}
    rr = mcda.rank_reversal(v, opts, crits, {"x": 0.6, "y": 0.4})
    assert rr["x"]["down"] == {"weight": pytest.approx(0.5), "option": "b", "tie": False} \
        and rr["x"]["up"] is None
    vals, used, notes = mcda.values({("a", "x"): 5, ("b", "x"): 5}, opts, ["x"], {"x": "higher"}, {"x": None})
    assert notes == ["flat:x"] and vals[("a", "x")] == 1.0
    vals, used, notes = mcda.values({("a", "x"): 12, ("b", "x"): 0}, opts, ["x"], {"x": "lower"}, {"x": (10, 0)})
    assert vals[("a", "x")] == 0.0 and vals[("b", "x")] == 1.0 and "outside:a:x" in notes


@pytest.fixture
def project(tmp_path: Path, git_identity, monkeypatch):
    root = tmp_path / "site"
    init_project(root, statement="Which site should the new hospital go on?")
    for label in [*SCORES, "Cost", "Travel time", "Capacity"]:
        node_ops.add_node(label, root=root)
    monkeypatch.chdir(root)
    return root


def _build(root, *, weights=(50, 30, 20)):
    for o in SCORES:
        mcda.set_element(o, "option", root=root)
    for c, w, d in zip(("Cost", "Travel time", "Capacity"), weights, ("lower", "lower", "higher"), strict=True):
        mcda.set_element(c, "criterion", root=root)
        mcda.set_criterion(c, weight=w, direction=d, root=root)
    for o, row in SCORES.items():
        for c, x in row.items():
            mcda.set_score(o, c, x, root=root)


def test_readiness(project):
    assert {"mcda_too_few_options", "mcda_no_criterion"} <= {
        g.gap_type for g in assess_readiness("mcda", root=project).gaps}
    _build(project)
    assert assess_readiness("mcda", root=project).can_switch


def test_ranking_and_contributions(project):
    _build(project)
    p = mcda.analyse(root=project)
    r = {x["option"]: x for x in p["ranking"]}
    # Local scales: cost 60→40, travel 30→15, capacity 250→320.
    a = 100 * (0.5 * 1 + 0.3 * (5 / 15) + 0.2 * (50 / 70))
    assert r["Site A"]["total"] == pytest.approx(a)
    assert p["ranking"][0]["option"] == "Site A"
    assert p["dominated"] == [{"option": "Site C", "by": "Site A"}]
    assert all(w["local_scale"] for w in p["weights"])
    near = mcda.closest_reversal(p)
    assert near and near["option"] == "Site B"
    assert "ranks first" in mcda.describe(p)
    assert p["margin"]["first"] == "Site A" and p["margin"]["unverified_scores"]


def test_stated_scale_and_setter_rules(project):
    _build(project)
    entry, _ = mcda.set_criterion("Cost", worst=100, best=0, root=project)
    assert entry.weight == 50 and entry.direction == "lower"  # untouched fields kept
    p = mcda.analyse(root=project)
    cost = next(w for w in p["weights"] if w["criterion"] == "Cost")
    assert not cost["local_scale"] and cost["worst"] == 100
    with pytest.raises(ValueError, match="best must be"):
        mcda.set_criterion("Capacity", worst=400, best=0, root=project)
    with pytest.raises(ValueError, match="not a criterion"):
        mcda.set_score("Site A", "Site B", 1, root=project)
    with pytest.raises(ValueError, match="nothing to set"):
        mcda.set_criterion("Cost", root=project)
    from latris.operations.view_roles import set_role

    with pytest.raises(ValueError, match="ranking"):
        set_role("Site A", "mcda", "outcome", root=project)


def test_missing_score_blocks(project):
    _build(project)
    node_ops.add_node("Site D", root=project)
    mcda.set_element("Site D", "option", root=project)
    p = mcda.analyse(root=project)
    assert {x["gap_type"] for x in p["problems"]} == {"mcda_missing_score"}


SPEC = """
model_type: mcda
factors: [{label: Site A}, {label: Site B}, {label: Cost}, {label: Travel time}]
mcda:
  elements:
    - {node: Site A, type: option}
    - {node: Site B, type: option}
    - {node: Cost, type: criterion}
    - {node: Travel time, type: criterion}
  criteria:
    - {node: Cost, weight: 60, direction: lower, worst: 80, best: 20, units: $m, source: board-workshop}
    - {node: Travel time, weight: 40, direction: lower}
  scores:
    - {option: Site A, criterion: Cost, value: 40, source: quote-a, verified: true}
    - {option: Site A, criterion: Travel time, value: 25}
    - {option: Site B, criterion: Cost, value: 55}
    - {option: Site B, criterion: Travel time, value: 15}
analyses:
  - kind: mcda_analyse
"""


@pytest.fixture
def built(tmp_path: Path, git_identity, monkeypatch):
    from latris.operations.build import build_from_spec, load_spec

    root = tmp_path / "built"
    init_project(root, statement="Which site?")
    monkeypatch.chdir(root)
    return root, build_from_spec(load_spec(SPEC), root=root)


def test_build_spec_and_share_link(built, tmp_path, git_identity):
    from latris.operations.build import build_from_spec
    from latris.operations.share_link import export_spec

    root, result = built
    assert result.analyses and not result.notes
    p = mcda.analyse(root=root)
    cost = next(w for w in p["weights"] if w["criterion"] == "Cost")
    assert cost["weight"] == pytest.approx(0.6) and cost["worst"] == 80
    _, spec = export_spec(model_type="mcda", root=root)
    assert spec.mcda and len(spec.mcda.scores) == 4 and [a.kind for a in spec.analyses] == ["mcda_analyse"]
    copy = tmp_path / "copy"
    init_project(copy, statement="copy")
    build_from_spec(spec, root=copy)
    assert mcda.analyse(root=copy)["ranking"] == p["ranking"]


def test_report_diagram_claims(built):
    from latris.exporters.markdown import render
    from latris.exporters.mermaid import render as mermaid
    from latris.operations.interpret import extract_claims
    from latris.repo.layout import ProjectPaths

    root, _ = built
    md = render(ProjectPaths(root), model_type="mcda", ai=False)
    assert "Multi-criteria decision analysis" in md and "Swing weights" in md
    assert "Multi-criteria decision analysis (additive value model)" in md
    src = mermaid(ProjectPaths(root), model_type="mcda")
    assert 'goal(["Choice"])' in src and "Cost<br/>60%" in src
    answer = extract_claims("answer_to_question", "mcda", root=root)
    assert any("ranks first" in c for c in answer)
    impl = extract_claims("implications", "mcda", root=root)
    assert any("weight on" in c or "No single weight" in c for c in impl)
    gaps = extract_claims("evidence_gaps", "mcda", root=root)
    assert any("Weights with no recorded source" in c and "Travel time" in c for c in gaps)
    sens = extract_claims("sensitivity", "mcda", root=root)
    assert any("Cost (weight 60%)" in c for c in sens) and not any("betweenness" in c for c in sens)


def test_routes(built):
    from fastapi.testclient import TestClient

    from latris.server.app import create_app

    root, _ = built
    c = TestClient(create_app(project_root=root))
    assert c.get("/api/mcda/check").json()["ready"] is True
    r = c.post("/api/mcda/criterion", json={"node": "Travel time", "weight": 10})
    assert r.status_code == 200 and r.json()["result"]["direction"] == "lower"
    assert c.post("/api/mcda/score", json={"option": "Cost", "criterion": "Cost", "value": 1}).status_code == 400
    r = c.post("/api/mcda/analyse", json={"record": False}).json()
    assert r["commit_sha"] is None and r["result"]["ranking"]


def test_cli(project):
    from typer.testing import CliRunner

    from latris.cli.app import app

    runner = CliRunner()
    assert runner.invoke(app, ["mcda", "check"]).exit_code == 1
    for o in SCORES:
        assert runner.invoke(app, ["mcda", "element", o, "option"]).exit_code == 0
    for c, w, d in (("Cost", "50", "lower"), ("Travel time", "30", "lower"), ("Capacity", "20", "higher")):
        assert runner.invoke(app, ["mcda", "element", c, "criterion"]).exit_code == 0
        out = runner.invoke(app, ["mcda", "criterion", c, "--weight", w, "--direction", d])
        assert out.exit_code == 0, out.output
    for o, row in SCORES.items():
        for c, x in row.items():
            assert runner.invoke(app, ["mcda", "score", o, c, str(x)]).exit_code == 0
    assert runner.invoke(app, ["mcda", "check"]).exit_code == 0
    assert "Site A" in runner.invoke(app, ["mcda", "show"]).output
    out = runner.invoke(app, ["mcda", "analyse"])
    assert out.exit_code == 0, out.output
    assert "ranks first" in out.output and "Dominated" in out.output and "recorded" in out.output


def test_flat_criterion_reversal_is_a_boundary_tie(project):
    """A flat criterion can only tie at 100%, never take the lead — reported as a tie, not a winner."""
    _build(project)
    for o in SCORES:
        mcda.set_score(o, "Capacity", 300, root=project)  # flat: every option identical
    p = mcda.analyse(root=project)
    assert p["flat"] == ["Capacity"]
    cap = next(r for r in p["rank_reversal"] if r["criterion"] == "Capacity")
    side = cap["up"] or cap["down"]
    assert side and side["tie"] is True

    from latris.operations.formalisms.mcda import _reversal_lines

    line = next(x for x in _reversal_lines(p) if x.startswith("Capacity"))
    assert "ties with" in line and "first" not in line


def test_outside_scale_scores_surfaced(project):
    """Scores beyond a stated scale are clamped and named, not silently swallowed."""
    _build(project)
    mcda.set_criterion("Capacity", worst=0, best=350, root=project)
    mcda.set_score("Site A", "Capacity", 500, root=project)
    p = mcda.analyse(root=project)
    assert p["outside"] == ["Site A on Capacity"]

    from typer.testing import CliRunner

    from latris.cli.app import app

    out = CliRunner().invoke(app, ["mcda", "analyse", "--no-record"])
    assert out.exit_code == 0, out.output
    assert "outside the stated scale" in out.output and "Site A on Capacity" in out.output


def test_report_render_mentions_flat_and_outside(project):
    from latris.operations.formalisms.mcda import _render

    _build(project)
    mcda.set_criterion("Capacity", worst=0, best=350, root=project)
    for o in SCORES:
        mcda.set_score(o, "Capacity", 500, root=project)  # flat, and beyond the stated scale
    p = mcda.analyse(root=project)
    text = "\n".join(_render(p))
    assert "can't separate them" in text
    assert "outside the stated scale" in text and "Site A on Capacity" in text


def test_describe_reports_boundary_tie_as_tie():
    """When the nearest 'reversal' is a boundary tie, describe says so instead of naming a winner."""
    payload = {"problems": [],
               "ranking": [{"option": "a", "total": 100.0}, {"option": "b", "total": 50.0}],
               "rank_reversal": [{"criterion": "y", "weight": 0.1,
                                  "up": {"weight": 1.0, "option": "b", "tie": True}, "down": None}],
               "dominated": []}
    text = mcda.describe(payload)
    assert "only draws level" in text and "b first" not in text
