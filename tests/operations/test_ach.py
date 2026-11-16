"""ACH: weighted inconsistency, diagnosticity, linchpins with source checks, and the surfaces."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import ach
from latris.operations import nodes as node_ops
from latris.operations.init import init_project
from latris.operations.readiness import assess_readiness

HYPS = ["Hardware failure", "Software bug", "Cyber attack"]
# item: (credibility, relevance, ratings per hypothesis)
ITEMS = {
    "Disk errors in logs": ("medium", "medium", ["C", "N", "N"]),
    "Outage began right after a deploy": ("high", "high", ["I", "CC", "C"]),
    "No unusual network traffic": ("high", "high", ["C", "C", "II"]),
    "Restart fixed it": ("medium", "medium", ["C", "C", "C"]),
}


def test_kernel_scores_and_leaders():
    s = ach.scores(["a", "b"], ["x", "y"], {("x", "a"): "I", ("x", "b"): "C", ("y", "a"): "N", ("y", "b"): "II"},
                   {"x": 1.0, "y": 0.4})
    assert s == {"a": 1.0, "b": pytest.approx(0.8)} and ach.leaders(s) == ["b"]
    assert ach.item_weight(None) == pytest.approx(0.49)


@pytest.fixture
def project(tmp_path: Path, git_identity, monkeypatch):
    root = tmp_path / "outage"
    init_project(root, statement="Why did the service go down on Tuesday?")
    for label in [*HYPS, *ITEMS]:
        node_ops.add_node(label, root=root)
    monkeypatch.chdir(root)
    return root


def _build(root, *, rate_all=True):
    for h in HYPS:
        ach.set_element(h, "hypothesis", root=root)
    for item, (cred, rel, ratings) in ITEMS.items():
        ach.set_element(item, "evidence_item", root=root)
        ach.set_item(item, credibility=cred, relevance=rel, root=root)
        for h, r in zip(HYPS, ratings, strict=True):
            if rate_all or h != "Cyber attack":
                ach.set_rating(item, h, r, rationale="test", root=root)


def test_readiness(project):
    assert {"ach_too_few_hypotheses", "ach_no_items"} <= {g.gap_type for g in assess_readiness("ach", root=project).gaps}
    _build(project, rate_all=False)
    assert {g.gap_type for g in assess_readiness("ach", root=project).gaps} == {"ach_missing_rating"}
    _build(project)
    assert assess_readiness("ach", root=project).can_switch


def test_analysis(project):
    _build(project)
    p = ach.analyse(root=project)
    assert p["leading"] == ["Software bug"]
    by = {r["hypothesis"]: r for r in p["ranking"]}
    assert by["Software bug"]["inconsistency"] == 0
    assert by["Hardware failure"]["inconsistency"] == pytest.approx(1.0)
    assert by["Cyber attack"]["inconsistency"] == pytest.approx(2.0)
    assert by["Cyber attack"]["against"] == ["No unusual network traffic"]
    assert set(p["non_diagnostic"]) == {"Restart fixed it"}
    # Without either, another hypothesis would tie with the software bug.
    assert {x["item"] for x in p["linchpins"]} == {"No unusual network traffic", "Outage began right after a deploy"}
    assert "Software bug has the least evidence against it" in ach.describe(p)


def test_linchpin_and_source_status(project):
    from latris.operations.evidence import add_evidence
    from latris.operations.references import add_reference

    _build(project)
    # Make the deploy evidence the only thing separating software from hardware.
    ach.set_rating("No unusual network traffic", "Cyber attack", "C", root=project)
    ach.set_rating("Disk errors in logs", "Software bug", "I", root=project)
    p = ach.analyse(root=project)
    assert [x["item"] for x in p["linchpins"]] and all(x["sources"] == "none" for x in p["linchpins"])
    add_reference("deploylog", "Deploy log, Tuesday", root=project)
    add_evidence("Outage began right after a deploy", "description", "deploylog", root=project)
    p = ach.analyse(root=project)
    item = next(m for m in p["matrix"] if m["item"] == "Outage began right after a deploy")
    assert item["sources"] == "cited"


def test_setters(project):
    _build(project)
    with pytest.raises(ValueError, match="isn't a rating"):
        ach.set_rating("Restart fixed it", "Software bug", "maybe", root=project)
    with pytest.raises(ValueError, match="not a hypothesis"):
        ach.set_rating("Restart fixed it", "Restart fixed it", "C", root=project)
    entry, _ = ach.set_rating("Restart fixed it", "Software bug", "cc", root=project)
    assert entry.rating == "CC"
    entry, _ = ach.set_item("Restart fixed it", relevance="low", root=project)
    assert entry.credibility == "medium" and entry.relevance == "low"
    from latris.operations.view_roles import set_role

    with pytest.raises(ValueError, match="competing hypotheses"):
        set_role("Software bug", "ach", "outcome", root=project)


SPEC = """
model_type: ach
factors: [{label: Insider}, {label: Outsider}, {label: Badge log shows entry}, {label: Window forced}]
ach:
  elements:
    - {node: Insider, type: hypothesis}
    - {node: Outsider, type: hypothesis}
    - {node: Badge log shows entry, type: evidence_item}
    - {node: Window forced, type: evidence_item}
  items:
    - {node: Badge log shows entry, credibility: high, relevance: high, verified: true}
  ratings:
    - {item: Badge log shows entry, hypothesis: Insider, rating: CC}
    - {item: Badge log shows entry, hypothesis: Outsider, rating: II, rationale: Outsiders have no badge}
    - {item: Window forced, hypothesis: Insider, rating: I}
    - {item: Window forced, hypothesis: Outsider, rating: C}
analyses:
  - kind: ach_analyse
"""


@pytest.fixture
def built(tmp_path: Path, git_identity, monkeypatch):
    from latris.operations.build import build_from_spec, load_spec

    root = tmp_path / "built"
    init_project(root, statement="Who got in?")
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
    p = ach.analyse(root=root)
    assert p["leading"] == ["Insider"] and [x["item"] for x in p["linchpins"]] == ["Badge log shows entry"]
    _, spec = export_spec(model_type="ach", root=root)
    assert spec.ach and len(spec.ach.ratings) == 4
    copy = tmp_path / "copy"
    init_project(copy, statement="copy")
    build_from_spec(spec, root=copy)
    assert ach.analyse(root=copy)["ranking"] == p["ranking"]
    md = render(ProjectPaths(root), model_type="ach", ai=False)
    assert "Competing hypotheses" in md and "Linchpins" in md and "Analysis of competing hypotheses" in md
    src = mermaid(ProjectPaths(root), model_type="ach")
    assert "-.->|II|" in src
    impl = extract_claims("implications", "ach", root=root)
    assert any("Check the sources behind these linchpins first: Badge log shows entry" in c for c in impl)
    sens = extract_claims("sensitivity", "ach", root=root)
    assert any("turns on Badge log shows entry" in c for c in sens)


def test_routes_and_cli(built):
    from fastapi.testclient import TestClient
    from typer.testing import CliRunner

    from latris.cli.app import app
    from latris.server.app import create_app

    root, _ = built
    c = TestClient(create_app(project_root=root))
    assert c.get("/api/ach/check").json()["ready"] is True
    assert c.post("/api/ach/rating", json={"item": "Window forced", "hypothesis": "Insider",
                                           "rating": "Z"}).status_code == 400
    r = c.post("/api/ach/analyse", json={"record": False}).json()
    assert r["commit_sha"] is None and r["result"]["leading"] == ["Insider"]
    runner = CliRunner()
    assert "Window forced" in runner.invoke(app, ["ach", "show"]).output
    out = runner.invoke(app, ["ach", "analyse"])
    assert out.exit_code == 0 and "Linchpin" in out.output and "recorded" in out.output
    assert runner.invoke(app, ["ach", "check"]).exit_code == 0
