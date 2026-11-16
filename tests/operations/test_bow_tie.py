"""Bow-ties on a project: elements, barriers, readiness, flags and LOPA frequencies."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import bow_tie as bt
from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations.analysis_results import report_results
from latris.operations.init import init_project
from latris.operations.readiness import assess_readiness

ELEMENTS = {
    "Flammable gas under pressure": "hazard",
    "Loss of containment": "top_event",
    "Corrosion": "threat", "Overpressure": "threat", "Impact damage": "threat",
    "Inspection programme": "barrier", "Corrosion inhibitor": "barrier", "Pressure relief valve": "barrier",
    "Gas detection": "barrier", "Emergency shutdown": "barrier", "Bypass permit": "barrier",
    "Fire": "consequence", "Toxic exposure": "consequence",
    "Detector bypassed for maintenance": "escalation_factor", "Relief valve not tested": "escalation_factor",
}
LINKS = [
    ("Flammable gas under pressure", "Loss of containment"),
    ("Corrosion", "Inspection programme"), ("Inspection programme", "Corrosion inhibitor"),
    ("Corrosion inhibitor", "Loss of containment"),
    ("Overpressure", "Pressure relief valve"), ("Pressure relief valve", "Loss of containment"),
    ("Impact damage", "Loss of containment"),
    ("Loss of containment", "Gas detection"), ("Gas detection", "Emergency shutdown"), ("Emergency shutdown", "Fire"),
    ("Gas detection", "Toxic exposure"),
    ("Detector bypassed for maintenance", "Bypass permit"), ("Bypass permit", "Gas detection"),
    ("Relief valve not tested", "Pressure relief valve"),
]


@pytest.fixture
def project(tmp_path: Path, git_identity, monkeypatch):
    root = tmp_path / "gas"
    init_project(root, statement="How well protected are we against a loss of containment?")
    for label in ELEMENTS:
        node_ops.add_node(label, kind="event", root=root)
    for a, b in LINKS:
        edge_ops.add_edge(a, b, root=root)
    monkeypatch.chdir(root)
    return root


def _classify(root):
    for label, el in ELEMENTS.items():
        bt.set_element(label, el, root=root)


def _quantify(root):
    for t, f in (("Corrosion", 0.1), ("Overpressure", 0.5), ("Impact damage", 0.01)):
        bt.set_frequency(t, f, root=root)
    for b, p in (("Inspection programme", 0.1), ("Corrosion inhibitor", 0.1), ("Pressure relief valve", 0.01),
                 ("Gas detection", 0.1), ("Emergency shutdown", 0.05), ("Bypass permit", 0.5)):
        bt.set_barrier(b, pfd=p, owner="Ops", root=root)


def test_readiness(project):
    r = assess_readiness("bow_tie", root=project)
    assert not r.can_switch and {"bt_no_top", "bt_no_threat", "bt_no_consequence"} <= {g.gap_type for g in r.gaps}
    _classify(project)
    r = assess_readiness("bow_tie", root=project)
    assert r.can_switch, r.gaps


def test_structure_problems(project):
    _classify(project)
    edge_ops.add_edge("Corrosion", "Fire", root=project)  # threat straight to a consequence
    node_ops.add_node("Spare barrier", root=project)
    bt.set_element("Spare barrier", "barrier", root=project)
    kinds = {p.gap_type for p in bt.structure_problems(root=project)}
    assert {"bt_bad_link", "bt_barrier_off_line"} <= kinds


def test_barrier_on_both_sides_is_a_loop(project):
    _classify(project)
    edge_ops.add_edge("Loss of containment", "Pressure relief valve", root=project)
    edge_ops.add_edge("Pressure relief valve", "Fire", root=project)
    assert {p.gap_type for p in bt.structure_problems(root=project)} == {"bt_cycle"}


def test_setters(project):
    _classify(project)
    with pytest.raises(ValueError, match="only a barrier takes"):
        bt.set_barrier("Corrosion", pfd=0.1, root=project)
    with pytest.raises(ValueError, match="only a threat takes a frequency"):
        bt.set_frequency("Gas detection", 0.1, root=project)
    with pytest.raises(ValueError, match="nothing to set"):
        bt.set_barrier("Gas detection", root=project)
    bt.set_barrier("Gas detection", barrier_type="active_hardware", owner="Instrument tech", root=project)
    entry, _ = bt.set_barrier("Gas detection", pfd=0.1, source_id="vendor", root=project)
    assert (entry.barrier_type, entry.owner, entry.pfd, entry.source_id) == ("active_hardware", "Instrument tech",
                                                                            0.1, "vendor")
    from latris.operations.view_roles import set_role

    with pytest.raises(ValueError, match="top_event"):
        set_role("Loss of containment", "bow_tie", "outcome", root=project)


def test_lines_and_flags(project):
    _classify(project)
    payload = bt.analyse(root=project)
    assert payload["hazard"] == "Flammable gas under pressure"
    f = bt.flags(payload)
    assert f["unprotected"] == ["Impact damage → Loss of containment"]
    assert sorted(f["single_barrier"]) == ["Loss of containment → Toxic exposure",
                                           "Overpressure → Loss of containment"]
    assert f["shared"] == ["Gas detection"]
    assert f["uncontrolled_escalation"] == ["Relief valve not tested → Pressure relief valve"]
    gd = next(b for b in payload["barriers"] if b["barrier"] == "Gas detection")
    assert gd["escalation_factors"] == [{"factor": "Detector bypassed for maintenance", "controls": ["Bypass permit"]}]
    permit = next(b for b in payload["barriers"] if b["barrier"] == "Bypass permit")
    assert permit["side"] == "escalation control"
    assert not payload["quantified"] and "Corrosion (frequency)" in payload["missing"]


def test_degraded_barrier_not_effective(project):
    _classify(project)
    bt.set_barrier("Corrosion inhibitor", status="degraded", root=project)
    f = bt.flags(bt.analyse(root=project))
    assert "Corrosion → Loss of containment" in f["single_barrier"]
    assert f["not_in_place"] == ["Corrosion inhibitor"]


def test_lopa_frequencies(project):
    _classify(project)
    _quantify(project)
    p = bt.analyse(root=project)
    f_top = 0.1 * 0.1 * 0.1 + 0.5 * 0.01 + 0.01 * 1.0
    assert p["frequency"]["top"] == pytest.approx(f_top)
    assert p["frequency"]["consequences"]["Fire"] == pytest.approx(f_top * 0.1 * 0.05)
    assert p["frequency"]["consequences"]["Toxic exposure"] == pytest.approx(f_top * 0.1)
    relief = next(b for b in p["barriers"] if b["barrier"] == "Pressure relief valve")
    assert relief["raw"] == pytest.approx((0.001 + 0.5 + 0.01) / f_top)
    # Not in place counts as always failing.
    bt.set_barrier("Pressure relief valve", status="not_in_place", root=project)
    assert bt.analyse(root=project)["frequency"]["top"] == pytest.approx(0.001 + 0.5 + 0.01)


def test_shared_barrier_counted_once_across_routes(project):
    _classify(project)
    _quantify(project)
    # A second route from Overpressure that also passes the relief valve: P(through) stays 0.01, not 1-(0.99)^2.
    node_ops.add_node("Operator response", root=project)
    bt.set_element("Operator response", "barrier", root=project)
    edge_ops.add_edge("Pressure relief valve", "Operator response", root=project)
    edge_ops.add_edge("Operator response", "Loss of containment", root=project)
    bt.set_barrier("Operator response", pfd=0.5, root=project)
    p = bt.analyse(root=project)
    over = 0.5 * 0.01  # either route needs the relief valve to fail; the direct route needs nothing else
    assert p["frequency"]["top"] == pytest.approx(0.001 + over + 0.01)


def test_record_and_stale(project):
    _classify(project)
    _quantify(project)
    sha, run_id = bt.record(bt.analyse(root=project), root=project)
    res = report_results(model_types=["bow_tie"], root=project)
    assert [r.run.id for r in res] == [run_id] and not res[0].stale
    bt.set_barrier("Gas detection", pfd=0.2, root=project)
    assert report_results(model_types=["bow_tie"], root=project)[0].stale


# ── surfaces ────────────────────────────────────────────────────────

SPEC = """
model_type: bow_tie
outcome: Loss of containment
factors:
  - {label: Loss of containment, kind: event}
  - {label: Corrosion, kind: event}
  - {label: Inspection programme}
  - {label: Gas detection}
  - {label: Fire, kind: event}
links:
  - {from: Corrosion, to: Inspection programme}
  - {from: Inspection programme, to: Loss of containment}
  - {from: Loss of containment, to: Gas detection}
  - {from: Gas detection, to: Fire}
bowtie:
  elements:
    - {node: Corrosion, type: threat}
    - {node: Inspection programme, type: barrier}
    - {node: Gas detection, type: barrier}
    - {node: Fire, type: consequence}
  barriers:
    - {node: Inspection programme, type: human, owner: Integrity engineer, pfd: 0.1, source: lopa2001, verified: true}
    - {node: Gas detection, type: active_hardware, status: degraded, pfd: 0.2}
  frequencies:
    - {node: Corrosion, frequency: 0.1, source: incident-log, origin: data-derived}
analyses:
  - kind: bowtie_analyse
"""


@pytest.fixture
def built(tmp_path: Path, git_identity, monkeypatch):
    from latris.operations.build import build_from_spec, load_spec

    root = tmp_path / "built"
    init_project(root, statement="How well protected are we against a loss of containment?")
    monkeypatch.chdir(root)
    result = build_from_spec(load_spec(SPEC), root=root)
    return root, result


def test_build_spec(built):
    root, result = built
    assert result.analyses and not result.notes
    p = bt.analyse(root=root)
    assert p["frequency"]["top"] == pytest.approx(0.01)
    assert p["frequency"]["consequences"]["Fire"] == pytest.approx(0.002)
    ins = next(b for b in p["barriers"] if b["barrier"] == "Inspection programme")
    assert (ins["type"], ins["owner"], ins["verification"]) == ("human", "Integrity engineer", "human-verified")
    assert bt.flags(p)["unprotected"] == ["Loss of containment → Fire"]  # the only mitigation barrier is degraded


def test_share_link_round_trip(built, tmp_path, git_identity):
    from latris.operations.build import build_from_spec
    from latris.operations.share_link import export_spec

    root, _ = built
    _, spec = export_spec(model_type="bow_tie", root=root)
    assert spec.bowtie and len(spec.bowtie.elements) == 5 and [a.kind for a in spec.analyses] == ["bowtie_analyse"]
    copy = tmp_path / "copy"
    init_project(copy, statement="copy")
    build_from_spec(spec, root=copy)
    assert bt.analyse(root=copy)["frequency"] == bt.analyse(root=root)["frequency"]


def test_report_diagram_claims(built):
    from latris.exporters.markdown import render
    from latris.exporters.mermaid import render as mermaid
    from latris.operations.interpret import extract_claims
    from latris.repo.layout import ProjectPaths

    root, _ = built
    md = render(ProjectPaths(root), model_type="bow_tie", ai=False)
    assert "Bow-tie: lines, barriers and frequencies" in md and "Bow-tie barrier analysis" in md
    src = mermaid(ProjectPaths(root), model_type="bow_tie")
    assert src.startswith("flowchart LR") and "<br/>degraded" in src and "stroke-dasharray" in src
    answer = extract_claims("answer_to_question", "bow_tie", root=root)
    assert any("no effective barrier" in c for c in answer) and any("per year" in c for c in answer)
    impl = extract_claims("implications", "bow_tie", root=root)
    assert any("degraded or not in place: Gas detection" in c for c in impl)
    assert any("nobody owns: Gas detection" in c for c in impl)
    sens = extract_claims("sensitivity", "bow_tie", root=root)
    assert sens[0].startswith("Barriers by how much they buy")


def test_routes(built):
    from fastapi.testclient import TestClient

    from latris.server.app import create_app

    root, _ = built
    c = TestClient(create_app(project_root=root))
    assert c.get("/api/bowtie/check").json()["ready"] is True
    assert len(c.get("/api/bowtie/elements").json()["elements"]) == 5
    assert c.post("/api/bowtie/frequency", json={"node": "Fire", "frequency": 1}).status_code == 400
    r = c.post("/api/bowtie/barrier", json={"node": "Gas detection", "status": "in_place"})
    assert r.status_code == 200 and r.json()["result"]["pfd"] == 0.2  # untouched fields kept
    r = c.post("/api/bowtie/analyse", json={"record": False}).json()
    assert r["commit_sha"] is None and r["result"]["quantified"]


def test_cli(project):
    from typer.testing import CliRunner

    from latris.cli.app import app

    runner = CliRunner()
    assert runner.invoke(app, ["bowtie", "check"]).exit_code == 1
    for label, el in ELEMENTS.items():
        assert runner.invoke(app, ["bowtie", "element", label, el]).exit_code == 0
    assert runner.invoke(app, ["bowtie", "check"]).exit_code == 0
    out = runner.invoke(app, ["bowtie", "barrier", "Gas detection", "--type", "active_hardware", "--pfd", "0.1",
                              "--owner", "Instrument tech", "--source", "vendor", "--verified"])
    assert out.exit_code == 0, out.output
    assert runner.invoke(app, ["bowtie", "frequency", "Corrosion", "0.1"]).exit_code == 0
    out = runner.invoke(app, ["bowtie", "show"])
    assert out.exit_code == 0 and "(no barrier)" in out.output and "pfd 0.1" in out.output
    out = runner.invoke(app, ["bowtie", "analyse"])
    assert out.exit_code == 0, out.output
    assert "No effective barrier" in out.output and "recorded" in out.output
    assert runner.invoke(app, ["bowtie", "barrier", "Gas detection", "--type", "procedural"]).exit_code != 0
