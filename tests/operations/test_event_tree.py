"""Event trees on a project: elements, heading order, sequences, completeness and quantification."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import event_tree as et
from latris.operations import nodes as node_ops
from latris.operations.analysis_results import report_results
from latris.operations.init import init_project
from latris.operations.readiness import assess_readiness

ELEMENTS = {
    "Gas release": "initiating_event",
    "Gas detected": "functional_event", "Isolation succeeds": "functional_event", "Ignition": "functional_event",
    "Contained release": "end_state", "Fire": "end_state", "Gas cloud dispersed": "end_state",
}
SEQUENCES = [
    ("Contained release", ["Gas detected=yes", "Isolation succeeds=yes"]),
    ("Fire", ["Gas detected=yes", "Isolation succeeds=no", "Ignition=yes"]),
    ("Gas cloud dispersed", ["Gas detected=yes", "Isolation succeeds=no", "Ignition=no"]),
    ("Fire", ["Gas detected=no", "Ignition=yes"]),
    ("Gas cloud dispersed", ["Gas detected=no", "Ignition=no"]),
]


@pytest.fixture
def project(tmp_path: Path, git_identity, monkeypatch):
    root = tmp_path / "release"
    init_project(root, statement="How often does a gas release end in a fire?")
    for label in ELEMENTS:
        node_ops.add_node(label, kind="event", root=root)
    monkeypatch.chdir(root)
    return root


def _build(root, *, sequences=SEQUENCES):
    for label, el in ELEMENTS.items():
        et.set_element(label, el, root=root)
    et.set_order(["Gas detected", "Isolation succeeds", "Ignition"], root=root)
    for end, answers in sequences:
        et.set_sequence(end, et.parse_answers(answers), root=root)


def _quantify(root):
    et.set_probability("Gas detected", 0.9, source_id="detector-data", verification="human-verified", root=root)
    et.set_probability("Isolation succeeds", 0.95, root=root)
    et.set_probability("Ignition", 0.1, root=root)
    et.set_probability("Ignition", 0.3, given=[("Gas detected", "no")], root=root)
    et.set_frequency("Gas release", 0.02, source_id="incident-log", root=root)


def test_readiness(project):
    assert {g.gap_type for g in assess_readiness("event_tree", root=project).gaps} >= {"et_no_initiator"}
    _build(project)
    r = assess_readiness("event_tree", root=project)
    assert r.can_switch, r.gaps


def test_missing_branch_and_overlap(project):
    _build(project, sequences=SEQUENCES[:-1])
    probs = et.structure_problems(root=project)
    assert [p.gap_type for p in probs] == ["et_missing_branch"]
    assert "Gas detected=no, Ignition=no" in probs[0].message
    et.set_sequence("Fire", [("Gas detected", "no")], root=project)  # ends while a sibling continues
    assert "et_overlap" in {p.gap_type for p in et.structure_problems(root=project)}


def test_inconsistent_next_question(project):
    seqs = SEQUENCES[:3] + [("Fire", ["Gas detected=no", "Isolation succeeds=yes"]),
                            ("Fire", ["Gas detected=no", "Ignition=no"])]
    _build(project, sequences=seqs)
    assert "et_inconsistent" in {p.gap_type for p in et.structure_problems(root=project)}


def test_unordered_unused(project):
    _build(project)
    node_ops.add_node("Deluge works", root=project)
    et.set_element("Deluge works", "functional_event", root=project)
    node_ops.add_node("Explosion", root=project)
    et.set_element("Explosion", "end_state", root=project)
    kinds = {p.gap_type for p in et.structure_problems(root=project)}
    assert {"et_heading_unordered", "et_end_state_unused"} <= kinds


def _problems(root) -> list[tuple[str | None, str]]:
    t = et.load_tree(root=root)
    return [(t.labels.get(p.target_id or "", None), p.gap_type) for p in t.problems]


def test_element_problems_in_order(project):
    _build(project)
    node_ops.add_node("Second release", root=project)
    et.set_element("Second release", "initiating_event", root=project)
    et.set_element("Ignition", "end_state", root=project)  # still in the heading order, no longer a heading
    assert _problems(project) == [("Second release", "et_many_initiators"), ("Ignition", "et_bad_heading"),
                                  ("Ignition", "et_end_state_unused")]
    p = et.analyse(root=project)
    assert p["initiator"] is None and p["sequences"] == [] and not p["quantified"] and len(p["problems"]) == 3


def test_bad_sequence_and_unused_heading(project):
    _build(project)
    node_ops.add_node("Deluge works", root=project)
    et.set_element("Deluge works", "functional_event", root=project)
    et.set_order(["Gas detected", "Isolation succeeds", "Ignition", "Deluge works"], root=project)
    assert _problems(project) == [("Deluge works", "et_heading_unused")]
    et.set_element("Fire", "functional_event", root=project)  # two sequences now end in a heading
    assert _problems(project) == [("Fire", "et_heading_unordered"), ("Fire", "et_bad_sequence"),
                                  ("Fire", "et_bad_sequence"), ("Deluge works", "et_heading_unused")]


def test_quantified_without_a_frequency(project):
    _build(project)
    _quantify(project)
    et.set_element("Gas release", "end_state", root=project)  # no initiator: a structure problem
    assert not et.analyse(root=project)["quantified"]
    et.set_element("Gas release", "initiating_event", root=project)
    p = et.analyse(root=project)
    assert p["quantified"] and p["frequency"] == {"per_year": 0.02, "origin": "human-direct",
                                                  "source": "incident-log", "weak": True}


def test_probabilities_without_a_frequency(project, tmp_path):
    _build(project)
    for args in (("Gas detected", 0.9), ("Isolation succeeds", 0.95), ("Ignition", 0.1)):
        et.set_probability(*args, root=project)
    p = et.analyse(root=project)
    assert p["quantified"] and p["frequency"] is None
    assert all(r["frequency"] is None for r in p["sequences"])
    assert all(d["frequency"] is None for d in p["end_states"])
    assert [v["heading"] for v in p["values"]] == ["Gas detected", "Isolation succeeds", "Ignition"]


def test_setters_refuse(project):
    _build(project)
    with pytest.raises(ValueError, match="Fire is an end state, not a heading"):
        et.set_probability("Fire", 0.5, root=project)
    with pytest.raises(ValueError, match="own answer"):
        et.set_probability("Ignition", 0.5, given=[("Ignition", "no")], root=project)
    with pytest.raises(ValueError, match="yes or no"):
        et.set_sequence("Fire", [("Ignition", "maybe")], root=project)
    with pytest.raises(ValueError, match="'Heading=yes'"):
        et.parse_answers(["Ignition"])
    from latris.operations.view_roles import set_role

    with pytest.raises(ValueError, match="end_state"):
        set_role("Fire", "event_tree", "outcome", root=project)


def test_sequence_replaced_and_removed(project):
    _build(project)
    et.set_sequence("Gas cloud dispersed", [("Gas detected", "yes"), ("Isolation succeeds", "yes")], root=project)
    s = et.get_structure(root=project)
    assert len(s.sequences) == 5
    et.remove_sequence([("Isolation succeeds", "yes"), ("Gas detected", "yes")], root=project)
    assert len(et.get_structure(root=project).sequences) == 4
    with pytest.raises(ValueError, match="no sequence"):
        et.remove_sequence([("Gas detected", "yes")], root=project)


def test_quantification(project):
    _build(project)
    p = et.analyse(root=project)
    assert not p["quantified"] and len(p["missing"]) == 4  # isolation, detected, ignition ×2 branches
    _quantify(project)
    p = et.analyse(root=project)
    assert p["quantified"] and p["total_probability"] == pytest.approx(1.0)
    ends = {d["end_state"]: d for d in p["end_states"]}
    assert ends["Fire"]["probability"] == pytest.approx(0.9 * 0.05 * 0.1 + 0.1 * 0.3)
    assert ends["Fire"]["frequency"] == pytest.approx(0.02 * 0.0345)
    assert ends["Contained release"]["probability"] == pytest.approx(0.855)
    assert ends["Fire"]["dominant"]["text"] == "Gas detected=no, Ignition=yes"
    assert p["end_states"][0]["end_state"] == "Contained release"
    assert "Isolation succeeds" in p["sequences"][0]["unverified"]
    assert "Gas detected" not in p["sequences"][0]["unverified"]
    assert "per year" in et.describe(p)


def test_ambiguous_probability(project):
    _build(project)
    _quantify(project)
    et.set_probability("Ignition", 0.5, given=[("Isolation succeeds", "no")], root=project)
    # Branch Gas detected=no doesn't ask isolation, so no clash there; on detected=yes, isolation=no the
    # 1-condition entry wins. Add a rival with the same specificity to make it ambiguous.
    et.set_probability("Ignition", 0.2, given=[("Gas detected", "yes")], root=project)
    p = et.analyse(root=project)
    assert not p["quantified"] and any("disagree" in m for m in p["missing"])


def test_record_and_stale(project):
    _build(project)
    _quantify(project)
    sha, run_id = et.record(et.analyse(root=project), root=project)
    res = report_results(model_types=["event_tree"], root=project)
    assert [r.run.id for r in res] == [run_id] and not res[0].stale
    et.set_probability("Ignition", 0.2, root=project)
    assert report_results(model_types=["event_tree"], root=project)[0].stale


# ── surfaces ────────────────────────────────────────────────────────

SPEC = """
model_type: event_tree
factors:
  - {label: Gas release, kind: event}
  - {label: Gas detected, kind: event}
  - {label: Ignition, kind: event}
  - {label: Contained release, kind: event}
  - {label: Fire, kind: event}
event_tree:
  elements:
    - {node: Gas release, type: initiating_event}
    - {node: Gas detected, type: functional_event}
    - {node: Ignition, type: functional_event}
    - {node: Contained release, type: end_state}
    - {node: Fire, type: end_state}
  order: [Gas detected, Ignition]
  sequences:
    - {answers: {Gas detected: "yes"}, end_state: Contained release}
    - {answers: {Gas detected: "no", Ignition: "yes"}, end_state: Fire}
    - {answers: {Gas detected: "no", Ignition: "no"}, end_state: Contained release}
  probabilities:
    - {node: Gas detected, p_yes: 0.9, source: detector-data, verified: true}
    - {node: Ignition, p_yes: 0.3, given: {Gas detected: "no"}}
  frequency: {node: Gas release, frequency: 0.02, source: incident-log, origin: data-derived}
analyses:
  - kind: et_analyse
"""


@pytest.fixture
def built(tmp_path: Path, git_identity, monkeypatch):
    from latris.operations.build import build_from_spec, load_spec

    root = tmp_path / "built"
    init_project(root, statement="How often does a gas release end in a fire?")
    monkeypatch.chdir(root)
    result = build_from_spec(load_spec(SPEC), root=root)
    return root, result


def test_build_spec(built):
    root, result = built
    assert result.analyses and not result.notes
    ends = {d["end_state"]: d for d in et.analyse(root=root)["end_states"]}
    assert ends["Fire"]["frequency"] == pytest.approx(0.02 * 0.1 * 0.3)
    assert ends["Contained release"]["probability"] == pytest.approx(0.97)


def test_build_spec_checks(tmp_path, git_identity):
    from latris.operations.build import build_from_spec, load_spec

    root = tmp_path / "bad"
    init_project(root, statement="Q?")
    bad = SPEC.replace("model_type: event_tree", "model_type: event_tree\noutcome: Fire").replace(
        "order: [Gas detected, Ignition]", "order: [Gas detected, Nowhere]")
    with pytest.raises(ValueError) as exc:
        build_from_spec(load_spec(bad), root=root)
    assert "its end states" in str(exc.value) and "no factor named 'Nowhere'" in str(exc.value)


def test_share_link_round_trip(built, tmp_path, git_identity):
    from latris.operations.build import build_from_spec
    from latris.operations.share_link import export_spec

    root, _ = built
    _, spec = export_spec(model_type="event_tree", root=root)
    assert spec.event_tree and spec.event_tree.order == ["Gas detected", "Ignition"]
    assert [a.kind for a in spec.analyses] == ["et_analyse"]
    copy = tmp_path / "copy"
    init_project(copy, statement="copy")
    build_from_spec(spec, root=copy)
    assert et.analyse(root=copy)["end_states"] == et.analyse(root=root)["end_states"]


def test_report_diagram_claims(built):
    from latris.exporters.markdown import render
    from latris.exporters.mermaid import render as mermaid
    from latris.operations.interpret import extract_claims
    from latris.repo.layout import ProjectPaths

    root, _ = built
    md = render(ProjectPaths(root), model_type="event_tree", ai=False)
    assert "Event tree: sequences and end states" in md and "Event tree analysis" in md
    src = mermaid(ProjectPaths(root), model_type="event_tree")
    assert src.startswith("flowchart LR") and 'q1{"Gas detected?"}' in src
    assert "q1 -->|no| q2" in src and "q2 -->|yes| e2" in src and "s0 --> q1" in src
    answer = extract_claims("answer_to_question", "event_tree", root=root)
    assert any(c.startswith("Fire:") and "per year" in c for c in answer)
    sens = extract_claims("sensitivity", "event_tree", root=root)
    assert any("Ignition" in c for c in sens) and not any("betweenness" in c for c in sens)
    impl = extract_claims("implications", "event_tree", root=root)
    assert any("To make Fire rarer" in c for c in impl)


_CLAIM_SECTIONS = ("structure", "answer", "sensitivity", "implications", "gaps", "other")


def test_claims_for_every_section_as_the_tree_fills_in(project):
    """What each report section claims: with structure problems, unquantified, without a frequency, and done."""
    from latris.operations.formalisms import event_tree as fet
    from latris.repo.layout import ProjectPaths

    def claims():
        return {s: fet._claims(ProjectPaths(project), s) for s in _CLAIM_SECTIONS}

    got = {"problems": claims()}
    _build(project)
    got["unquantified"] = claims()
    for args in (("Gas detected", 0.9), ("Isolation succeeds", 0.95), ("Ignition", 0.1)):
        et.set_probability(*args, root=project)
    got["no_frequency"] = claims()
    et.set_probability("Gas detected", 0.9, source_id="detector-data", verification="human-verified", root=project)
    et.set_probability("Ignition", 0.3, given=[("Gas detected", "no")], root=project)
    et.set_frequency("Gas release", 0.02, source_id="incident-log", root=project)
    got["quantified"] = claims()
    assert got == (
    {'problems': {'structure': ['The event tree is incomplete: 3 structure problem(s) (e.g. (tree): No initiating '
                                'event: say what starts the sequence.)'],
                  'answer': [],
                  'sensitivity': [],
                  'implications': [],
                  'gaps': [],
                  'other': []},
     'unquantified': {'structure': ['Gas release: 3 heading(s), 5 sequence(s), 3 end state(s); 4 probability(ies) '
                                    'missing, so not quantified.',
                                    'Headings, in order: Gas detected → Isolation succeeds → Ignition.'],
                      'answer': [],
                      'sensitivity': [],
                      'implications': [],
                      'gaps': ['Not quantified — missing: P(Gas detected=yes given (start)); P(Isolation succeeds=yes '
                               'given Gas detected=yes); P(Ignition=yes given Gas detected=yes, Isolation '
                               'succeeds=no); P(Ignition=yes given Gas detected=no).',
                               'No frequency for Gas release, so results are conditional probabilities.'],
                      'other': []},
     'no_frequency': {'structure': ['Gas release: 3 heading(s), 5 sequence(s), 3 end state(s); probability given the '
                                    'initiating event: Contained release 0.855, Gas cloud dispersed 0.131, Fire '
                                    '0.0145.',
                                    'Headings, in order: Gas detected → Isolation succeeds → Ignition.'],
                      'answer': ['Contained release: probability 0.855, mostly through Gas detected=yes, Isolation '
                                 'succeeds=yes (100%).',
                                 'Gas cloud dispersed: probability 0.131, mostly through Gas detected=no, Ignition=no '
                                 '(69%).',
                                 'Fire: probability 0.0145, mostly through Gas detected=no, Ignition=yes (69%).',
                                 'These are probabilities given that Gas release happens; give it a frequency for '
                                 'rates per year.'],
                      'sensitivity': ['Branch probabilities on the dominant sequences that nobody has verified: Gas '
                                      'detected, Ignition, Isolation succeeds — these move the answer most directly.'],
                      'implications': ['To make Contained release rarer, look first at sequence #1: Gas detected=yes, '
                                       'Isolation succeeds=yes.',
                                       'To make Gas cloud dispersed rarer, look first at sequence #5: Gas detected=no, '
                                       'Ignition=no.',
                                       'To make Fire rarer, look first at sequence #4: Gas detected=no, Ignition=yes.'],
                      'gaps': ['No frequency for Gas release, so results are conditional probabilities.',
                               'Branch probabilities with no stated source: Gas detected, Ignition, Isolation '
                               'succeeds.'],
                      'other': []},
     'quantified': {'structure': ['Gas release: 3 heading(s), 5 sequence(s), 3 end state(s); per year: Contained '
                                  'release 0.0171/year, Gas cloud dispersed 0.00221/year, Fire 0.00069/year.',
                                  'Headings, in order: Gas detected → Isolation succeeds → Ignition.'],
                    'answer': ['Contained release: 0.0171 per year, mostly through Gas detected=yes, Isolation '
                               'succeeds=yes (100%).',
                               'Gas cloud dispersed: 0.00221 per year, mostly through Gas detected=no, Ignition=no '
                               '(63%).',
                               'Fire: 0.00069 per year, mostly through Gas detected=no, Ignition=yes (87%).'],
                    'sensitivity': ['Branch probabilities on the dominant sequences that nobody has verified: '
                                    'Ignition, Isolation succeeds — these move the answer most directly.',
                                    "The frequency of Gas release scales every result and hasn't been verified."],
                    'implications': ['To make Contained release rarer, look first at sequence #1: Gas detected=yes, '
                                     'Isolation succeeds=yes.',
                                     'To make Gas cloud dispersed rarer, look first at sequence #5: Gas detected=no, '
                                     'Ignition=no.',
                                     'To make Fire rarer, look first at sequence #4: Gas detected=no, Ignition=yes.'],
                    'gaps': ['Branch probabilities with no stated source: Ignition, Isolation succeeds.'],
                    'other': []}}
    )


def test_routes(built):
    from fastapi.testclient import TestClient

    from latris.server.app import create_app

    root, _ = built
    c = TestClient(create_app(project_root=root))
    assert c.get("/api/et/check").json()["ready"] is True
    assert len(c.get("/api/et/tree").json()["structure"]["sequences"]) == 3
    r = c.post("/api/et/sequence/remove", json={"answers": [{"heading": "Gas detected", "answer": "yes"}]})
    assert r.status_code == 200
    assert c.get("/api/et/check").json()["ready"] is False
    r = c.post("/api/et/sequence", json={"end_state": "Contained release",
                                         "answers": [{"heading": "Gas detected", "answer": "yes"}]})
    assert r.status_code == 200
    assert c.post("/api/et/probability", json={"node": "Fire", "p_yes": 0.5}).status_code == 422
    r = c.post("/api/et/analyse", json={"record": False}).json()
    assert r["commit_sha"] is None and r["result"]["quantified"]


def test_cli(project):
    from typer.testing import CliRunner

    from latris.cli.app import app

    runner = CliRunner()
    assert runner.invoke(app, ["et", "check"]).exit_code == 1
    for label, el in ELEMENTS.items():
        assert runner.invoke(app, ["et", "element", label, el]).exit_code == 0
    assert runner.invoke(app, ["et", "order", "Gas detected", "Isolation succeeds", "Ignition"]).exit_code == 0
    for end, answers in SEQUENCES:
        out = runner.invoke(app, ["et", "sequence", end, *answers])
        assert out.exit_code == 0, out.output
    assert runner.invoke(app, ["et", "check"]).exit_code == 0
    for args in (["Gas detected", "0.9", "--verified"], ["Isolation succeeds", "0.95"], ["Ignition", "0.1"],
                 ["Ignition", "0.3", "--given", "Gas detected=no"]):
        assert runner.invoke(app, ["et", "probability", *args]).exit_code == 0
    assert runner.invoke(app, ["et", "frequency", "Gas release", "0.02"]).exit_code == 0
    out = runner.invoke(app, ["et", "show"])
    assert out.exit_code == 0 and "Contained" in out.output
    out = runner.invoke(app, ["et", "analyse"])
    assert out.exit_code == 0, out.output
    assert "Dominant" in out.output and "recorded" in out.output
    out = runner.invoke(app, ["et", "remove-sequence", "Gas detected=no", "Ignition=no"])
    assert out.exit_code == 0 and runner.invoke(app, ["et", "check"]).exit_code == 1


def test_no_centrality_claims_for_risk_formalisms(built):
    from latris.operations import edges as edge_ops
    from latris.operations.interpret import extract_claims

    root, _ = built
    edge_ops.add_edge("Gas release", "Gas detected", root=root)
    edge_ops.add_edge("Gas detected", "Fire", root=root)
    for section in ("answer_to_question", "key_findings"):
        claims = extract_claims(section, "event_tree", root=root)
        assert not any("Key factors" in c or "causal paths run through" in c for c in claims), claims
