"""Fault trees on a project: events, gates, probabilities, readiness and analysis."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import edges as edge_ops
from latris.operations import fault_tree as ft
from latris.operations import nodes as node_ops
from latris.operations.analysis_results import report_results
from latris.operations.init import init_project
from latris.operations.readiness import assess_readiness

# Loss of cooling = (Pump A fails AND Pump B fails) OR Power lost; power lost = 2-of-3 supplies.
EVENTS = {
    "Loss of cooling": "top_event",
    "Both pumps fail": "intermediate_event",
    "Power lost": "intermediate_event",
    "Pump A fails": "basic_event",
    "Pump B fails": "basic_event",
    "Supply 1 fails": "basic_event",
    "Supply 2 fails": "basic_event",
    "Supply 3 fails": "basic_event",
}
LINKS = [
    ("Both pumps fail", "Loss of cooling"), ("Power lost", "Loss of cooling"),
    ("Pump A fails", "Both pumps fail"), ("Pump B fails", "Both pumps fail"),
    ("Supply 1 fails", "Power lost"), ("Supply 2 fails", "Power lost"), ("Supply 3 fails", "Power lost"),
]


@pytest.fixture
def project(tmp_path: Path, git_identity, monkeypatch):
    root = tmp_path / "cooling"
    init_project(root, statement="How likely is a loss of cooling, and what drives it?")
    for label in EVENTS:
        node_ops.add_node(label, kind="event", root=root)
    for a, b in LINKS:
        edge_ops.add_edge(a, b, kind="logical", root=root)
    monkeypatch.chdir(root)
    return root


def _classify(root, *, gates=True, probs=True):
    for label, t in EVENTS.items():
        ft.set_event(label, t, root=root)
    if gates:
        ft.set_gate("Loss of cooling", "or", root=root)
        ft.set_gate("Both pumps fail", "and", root=root)
        ft.set_gate("Power lost", "vote", k=2, root=root)
    if probs:
        for label, p in (("Pump A fails", 0.01), ("Pump B fails", 0.02), ("Supply 1 fails", 0.001),
                         ("Supply 2 fails", 0.001), ("Supply 3 fails", 0.001)):
            ft.set_probability(label, p, source_id="oreda", root=root)


def test_readiness_gaps_then_ready(project):
    r = assess_readiness("fault_tree", root=project)
    assert not r.can_switch and {g.gap_type for g in r.gaps} == {"ft_no_top"}
    _classify(project, gates=False, probs=False)
    r = assess_readiness("fault_tree", root=project)
    assert {g.gap_type for g in r.gaps} == {"ft_no_gate"}
    _classify(project, probs=False)
    assert assess_readiness("fault_tree", root=project).can_switch  # probabilities aren't needed to be ready


def test_structure_problems(project):
    _classify(project, probs=False)
    edge_ops.add_edge("Loss of cooling", "Pump A fails", kind="logical", root=project)  # loop + leaf with input
    kinds = {p.gap_type for p in ft.structure_problems(root=project)}
    assert {"ft_cycle", "ft_leaf_has_inputs"} <= kinds


def test_vote_k_too_big_and_orphan(project):
    _classify(project, probs=False)
    ft.set_gate("Power lost", "vote", k=4, root=project)
    node_ops.add_node("Valve stuck", kind="event", root=project)
    ft.set_event("Valve stuck", "basic_event", root=project)
    kinds = {p.gap_type for p in ft.structure_problems(root=project)}
    assert {"ft_vote_k", "ft_not_in_tree"} <= kinds


def _problems(root) -> list[tuple[str | None, str]]:
    t = ft.load_tree(root=root)
    return [(t.labels.get(p.target_id or "", None), p.gap_type) for p in t.problems]


def test_structure_problems_in_order(project):
    _classify(project, probs=False)
    node_ops.add_node("Second top", kind="event", root=project)
    ft.set_event("Second top", "top_event", root=project)  # no gate, no inputs, and a second top
    assert _problems(project) == [("Second top", "ft_many_tops"), ("Second top", "ft_no_gate"),
                                  ("Second top", "ft_no_inputs")]
    assert ft.load_tree(root=project).top is None


def test_a_leaf_with_inputs_and_a_duplicate_link(project):
    _classify(project, probs=False)
    edge_ops.add_edge("Supply 1 fails", "Pump A fails", kind="logical", root=project)
    edge_ops.add_edge("Supply 1 fails", "Pump A fails", kind="causal", root=project)  # the same input twice
    t = ft.load_tree(root=project)
    assert _problems(project) == [("Pump A fails", "ft_leaf_has_inputs")]
    assert t.inputs[t.top] and [t.labels[i] for i in t.inputs[next(k for k, v in t.labels.items()
                                                                   if v == "Pump A fails")]] == ["Supply 1 fails"]


def test_setters_refuse_wrong_event_types(project):
    _classify(project, gates=False, probs=False)
    with pytest.raises(ValueError, match="only a top or intermediate event has a gate"):
        ft.set_gate("Pump A fails", "and", root=project)
    with pytest.raises(ValueError, match="only basic and undeveloped events take a probability"):
        ft.set_probability("Loss of cooling", 0.1, root=project)
    with pytest.raises(ValueError, match="not a fault-tree event type"):
        ft.set_event("Pump A fails", "gate", root=project)
    from latris.operations.view_roles import set_role

    with pytest.raises(ValueError, match="top_event"):
        set_role("Loss of cooling", "fault_tree", "outcome", root=project)


def test_unclassified_input_is_left_out_and_reported(project):
    _classify(project)
    node_ops.add_node("Operator error", root=project)
    edge_ops.add_edge("Operator error", "Both pumps fail", root=project)
    payload = ft.analyse(root=project)
    assert payload["outside_inputs"] == ["Operator error → Both pumps fail"]
    assert payload["problems"] == []


def test_analysis_qualitative_then_quantified(project):
    _classify(project, probs=False)
    payload = ft.analyse(root=project)
    assert payload["cut_sets_total"] == 4  # {A,B} and three pairs of supplies
    assert payload["by_order"] == {2: 4}
    assert payload["single_points"] == []
    assert not payload["quantified"] and len(payload["missing_probabilities"]) == 5
    assert "not quantified" in ft.describe(payload)

    _classify(project)
    payload = ft.analyse(root=project)
    p_pumps, q = 0.01 * 0.02, 0.001
    p_power = 3 * q * q * (1 - q) + q ** 3
    assert payload["probability"]["exact"] == pytest.approx(1 - (1 - p_pumps) * (1 - p_power))
    assert payload["importance"][0]["event"] in ("Pump A fails", "Pump B fails")
    assert all(i["weak"] for i in payload["importance"])  # nothing human-verified
    assert payload["cut_sets"][0]["events"] == ["Pump A fails", "Pump B fails"]  # most likely pair first


def test_single_point_of_failure(project):
    _classify(project)
    node_ops.add_node("Control fault", kind="event", root=project)
    ft.set_event("Control fault", "basic_event", root=project)
    edge_ops.add_edge("Control fault", "Loss of cooling", kind="logical", root=project)
    payload = ft.analyse(root=project)
    assert payload["single_points"] == ["Control fault"]
    assert payload["missing_probabilities"] == ["Control fault"]


def test_max_order_limits_listing_not_probability(project):
    _classify(project)
    full = ft.analyse(root=project)
    short = ft.analyse(max_order=1, root=project)
    assert short["cut_sets_total"] == 0
    assert short["probability"]["exact"] == pytest.approx(full["probability"]["exact"])


def test_record_and_stale_on_probability_change(project):
    _classify(project)
    sha, run_id = ft.record(ft.analyse(root=project), root=project)
    res = report_results(model_types=["fault_tree"], root=project)
    assert [r.run.id for r in res] == [run_id] and not res[0].stale
    ft.set_probability("Pump A fails", 0.05, root=project)
    assert report_results(model_types=["fault_tree"], root=project)[0].stale


# ── surfaces ────────────────────────────────────────────────────────

SPEC = """
model_type: fault_tree
outcome: Loss of cooling
factors:
  - {label: Loss of cooling, kind: event}
  - {label: Both pumps fail, kind: event}
  - {label: Pump A fails, kind: event}
  - {label: Pump B fails, kind: event}
  - {label: Control fault, kind: event}
links:
  - {from: Both pumps fail, to: Loss of cooling, kind: logical}
  - {from: Control fault, to: Loss of cooling, kind: logical}
  - {from: Pump A fails, to: Both pumps fail, kind: logical}
  - {from: Pump B fails, to: Both pumps fail, kind: logical}
ft:
  events:
    - {node: Both pumps fail, type: intermediate_event}
    - {node: Pump A fails, type: basic_event}
    - {node: Pump B fails, type: basic_event}
    - {node: Control fault, type: undeveloped_event}
  gates:
    - {node: Loss of cooling, gate: or}
    - {node: Both pumps fail, gate: and}
  probabilities:
    - {node: Pump A fails, probability: 0.01, source: oreda2015, origin: data-derived, verified: true}
    - {node: Pump B fails, probability: 0.02, source: oreda2015, origin: data-derived}
    - {node: Control fault, probability: 0.001, notes: engineering judgement}
analyses:
  - kind: ft_analyse
"""


@pytest.fixture
def built(tmp_path: Path, git_identity, monkeypatch):
    from latris.operations.build import build_from_spec, load_spec

    root = tmp_path / "built"
    init_project(root, statement="How likely is a loss of cooling?")
    monkeypatch.chdir(root)
    result = build_from_spec(load_spec(SPEC), root=root)
    return root, result


def test_build_spec(built):
    root, result = built
    assert result.analyses and not result.notes
    assert ft.get_events(root=root)[next(iter(k for k, v in ft.get_events(root=root).items()
                                               if v == "top_event"))] == "top_event"
    payload = ft.analyse(root=root)
    assert payload["single_points"] == ["Control fault"]
    assert payload["probability"]["exact"] == pytest.approx(1 - (1 - 0.0002) * (1 - 0.001))
    verified = {i["event"]: i["verification"] for i in payload["importance"]}
    assert verified == {"Pump A fails": "human-verified", "Pump B fails": "unverified", "Control fault": "unverified"}


def test_build_spec_checks(tmp_path, git_identity):
    from latris.operations.build import build_from_spec, load_spec

    root = tmp_path / "bad"
    init_project(root, statement="Q?")
    bad = SPEC.replace("- {node: Loss of cooling, gate: or}", "- {node: Loss of cooling, gate: vote}\n"
                       "    - {node: Nowhere, gate: or}")
    with pytest.raises(ValueError) as exc:
        build_from_spec(load_spec(bad), root=root)
    assert "no factor named 'Nowhere'" in str(exc.value) and "k goes with a vote gate" in str(exc.value)


def test_share_link_round_trip(built, tmp_path, git_identity):
    from latris.operations.build import build_from_spec
    from latris.operations.share_link import export_spec

    root, _ = built
    _, spec = export_spec(model_type="fault_tree", root=root)
    assert spec.ft and len(spec.ft.events) == 5 and len(spec.ft.probabilities) == 3
    assert [a.kind for a in spec.analyses] == ["ft_analyse"]
    copy = tmp_path / "copy"
    init_project(copy, statement="copy")
    build_from_spec(spec, root=copy)
    assert ft.analyse(root=copy)["probability"] == ft.analyse(root=root)["probability"]


def test_report_and_diagram(built):
    from latris.exporters.markdown import render
    from latris.exporters.mermaid import render as mermaid
    from latris.repo.layout import ProjectPaths

    root, _ = built
    md = render(ProjectPaths(root), model_type="fault_tree", ai=False)
    assert "Fault tree: cut sets, probability and importance" in md
    assert "Fault tree analysis" in md  # methods and foundations
    src = mermaid(ProjectPaths(root), model_type="fault_tree")
    assert src.startswith("flowchart TB") and "<br/>OR" in src and "<br/>AND" in src and "p = 0.01" in src


def test_claims(built):
    from latris.operations.interpret import extract_claims

    root, _ = built
    answer = extract_claims("answer_to_question", "fault_tree", root=root)
    assert any("Single points of failure" in c and "Control fault" in c for c in answer)
    sens = extract_claims("sensitivity", "fault_tree", root=root)
    assert sens[0].startswith("Basic events by importance") and not any("betweenness" in c for c in sens)
    impl = extract_claims("implications", "fault_tree", root=root)
    assert any("Control fault" in c for c in impl) and not any("intervention points" in c for c in impl)
    gaps = extract_claims("evidence_gaps", "fault_tree", root=root)
    assert any("no stated source: Control fault" in c for c in gaps)


def test_routes(built):
    from fastapi.testclient import TestClient

    from latris.server.app import create_app

    root, _ = built
    c = TestClient(create_app(project_root=root))
    assert c.get("/api/ft/check").json()["ready"] is True
    assert len(c.get("/api/ft/tree").json()["events"]) == 5
    assert c.post("/api/ft/gate", json={"node": "Both pumps fail", "gate": "vote"}).status_code == 422
    assert c.post("/api/ft/probability", json={"node": "Loss of cooling", "probability": 0.1}).status_code == 422
    r = c.post("/api/ft/probability", json={"node": "Pump B fails", "probability": 0.03})
    assert r.status_code == 200 and r.json()["commit_sha"]
    r = c.post("/api/ft/analyse", json={"record": False}).json()
    assert r["commit_sha"] is None and r["result"]["quantified"]


def test_cli(project):
    from typer.testing import CliRunner

    from latris.cli.app import app

    runner = CliRunner()
    assert runner.invoke(app, ["ft", "check"]).exit_code == 1
    for label, t in EVENTS.items():
        assert runner.invoke(app, ["ft", "event", label, t]).exit_code == 0
    assert runner.invoke(app, ["ft", "gate", "Loss of cooling", "or"]).exit_code == 0
    assert runner.invoke(app, ["ft", "gate", "Both pumps fail", "and"]).exit_code == 0
    assert runner.invoke(app, ["ft", "gate", "Power lost", "vote", "--k", "2"]).exit_code == 0
    out = runner.invoke(app, ["ft", "check"])
    assert out.exit_code == 0, out.output
    for label in ("Pump A fails", "Pump B fails", "Supply 1 fails", "Supply 2 fails", "Supply 3 fails"):
        assert runner.invoke(app, ["ft", "probability", label, "0.01", "--source", "oreda"]).exit_code == 0
    out = runner.invoke(app, ["ft", "show"])
    assert out.exit_code == 0 and "VOTE 2" in out.output
    out = runner.invoke(app, ["ft", "analyse"])
    assert out.exit_code == 0, out.output
    assert "Top-event probability" in out.output and "recorded" in out.output
    assert runner.invoke(app, ["ft", "probability", "Loss of cooling", "0.5"]).exit_code != 0
