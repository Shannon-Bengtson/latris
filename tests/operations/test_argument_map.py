"""Argument maps: grounded labelling with support, linchpins, grounds from sources, challenges, surfaces."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import argument_map as am
from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations.init import init_project
from latris.operations.readiness import assess_readiness

# Fund the drug, because it works and we can afford it (one reason), and because patients want it (another).
# "The trial was small" objects to "it works"; "a second trial confirmed it" answers that objection.
# "The budget is overspent" objects to "we can afford it", and nothing answers it.
CLAIMS = ["Fund the drug", "The drug works", "We can afford it", "Patients want it", "The trial was small",
          "A second trial confirmed it", "The budget is overspent"]
LINKS = [
    ("The drug works", "Fund the drug", "supports", "value"),
    ("We can afford it", "Fund the drug", "supports", "value"),
    ("Patients want it", "Fund the drug", "supports", None),
    ("The trial was small", "The drug works", "attacks", None),
    ("A second trial confirmed it", "The trial was small", "attacks", None),
    ("The budget is overspent", "We can afford it", "attacks", None),
]


@pytest.fixture
def project(tmp_path: Path, git_identity, monkeypatch):
    root = tmp_path / "case"
    init_project(root, statement="Should we fund the new drug?")
    for c in CLAIMS:
        node_ops.add_node(c, root=root)
    for a, b, _, _ in LINKS:
        edge_ops.add_edge(a, b, root=root)
    monkeypatch.chdir(root)
    return root


def _build(root):
    am.set_element("Fund the drug", "conclusion", root=root)
    for c in CLAIMS[1:]:
        am.set_element(c, "claim", root=root)
    for a, b, rel, reason in LINKS:
        am.set_link(f"{a} -> {b}", relation=rel, reason=reason, root=root)


def test_readiness(project):
    assert {g.gap_type for g in assess_readiness("argument_map", root=project).gaps} >= {"am_no_conclusion"}
    am.set_element("Fund the drug", "conclusion", root=project)
    assert "am_no_reasons" in {p.gap_type for p in am.structure_problems(root=project)}
    _build(project)
    assert assess_readiness("argument_map", root=project).can_switch
    am.set_element("Patients want it", "conclusion", root=project)
    assert "am_many_conclusions" in {p.gap_type for p in am.structure_problems(root=project)}


def test_labelling(project):
    _build(project)
    lab = {project_label: s for project_label, s in _labels(project).items()}
    assert lab["A second trial confirmed it"] == "in" and lab["The trial was small"] == "out"
    assert lab["The drug works"] == "in"  # its objection is answered
    assert lab["The budget is overspent"] == "in" and lab["We can afford it"] == "out"  # unanswered
    assert lab["Fund the drug"] == "in"  # the linked reason fails, but "patients want it" holds alone

    p = am.analyse(root=project)
    assert p["status"] == "in" and am.describe(p).startswith("Fund the drug stands on 1 reason(s)")
    value = next(r for r in p["reasons"] if r["reason"] == "value")
    assert value["status"] == "fails" and value["premises"] == ["The drug works", "We can afford it"]
    assert [o["objection"] for o in p["unanswered"]] == ["The budget is overspent"]
    assert [x["claim"] for x in p["linchpins"]] == ["Patients want it"]
    assert p["rests_on"]["none"] == ["Patients want it"]  # it stands on an unsourced assertion
    assert len(p["no_warrant"]) == 2


def _labels(root) -> dict[str, str]:
    m = am.load(root=root)
    return {m.labels[c]: s for c, s in am.label(m).items()}


def test_rejection_challenge_and_disputed_source(project):
    from latris.operations import references
    from latris.operations.challenges import open_challenge, resolve_challenge
    from latris.operations.evidence import add_evidence

    _build(project)
    am.set_claim("Patients want it", assessment="rejected", rationale="The survey was of carers.", root=project)
    p = am.analyse(root=project)
    assert p["status"] == "out" and "every reason offered for it fails" in am.describe(p)
    am.set_claim("Patients want it", assessment=None, root=project)

    # An open challenge on the inference counts the reason for nothing until it is resolved.
    ch, _ = open_challenge("Patients want it -> Fund the drug", "Wanting it isn't a reason to fund it.",
                           root=project)
    p = am.analyse(root=project)
    assert p["status"] == "out" and p["challenged"] == ["Patients want it → Fund the drug"]
    resolve_challenge(ch.id, "retained-unchanged", rationale="Patient preference is a funding criterion.",
                      root=project)
    assert am.analyse(root=project)["status"] == "in"

    # A source that disputes a premise taken as given leaves it undecided, and so the conclusion.
    references.add_reference("survey", title="Carer survey", root=project)
    add_evidence("Patients want it", "description", "survey", contradicts=True, root=project)
    lab = _labels(project)
    assert lab["Patients want it"] == "undecided" and lab["Fund the drug"] == "undecided"
    am.set_claim("Patients want it", assessment="accepted", rationale="Board accepted the patient panel.",
                 root=project)
    assert _labels(project)["Fund the drug"] == "in"


def test_mutual_attack_is_undecided(project):
    _build(project)
    edge_ops.add_edge("We can afford it", "The budget is overspent", root=project)
    am.set_link("We can afford it -> The budget is overspent", relation="attacks", root=project)
    lab = _labels(project)
    assert lab["We can afford it"] == "undecided" and lab["The budget is overspent"] == "undecided"
    assert lab["Fund the drug"] == "in"


def test_refusals(project):
    _build(project)
    with pytest.raises(ValueError, match="argued for, not offered"):
        edge_ops.add_edge("Fund the drug", "Patients want it", root=project)
        am.set_link("Fund the drug -> Patients want it", root=project)
    with pytest.raises(ValueError, match="isn't a relation"):
        am.set_link("Patients want it -> Fund the drug", relation="undermines", root=project)
    with pytest.raises(ValueError, match="isn't a qualifier"):
        am.set_link("Patients want it -> Fund the drug", qualifier="definitely", root=project)


def test_surfaces(project):
    from fastapi.testclient import TestClient
    from typer.testing import CliRunner

    from latris.cli.app import app
    from latris.exporters.markdown import render
    from latris.operations.analysis_results import is_stale, report_results
    from latris.operations.build import build_from_spec
    from latris.operations.interpret import extract_claims
    from latris.operations.share_link import export_spec
    from latris.repo.layout import ProjectPaths
    from latris.server.app import create_app

    runner = CliRunner()
    for c, kind in [("Fund the drug", "conclusion"), *[(c, "claim") for c in CLAIMS[1:]]]:
        assert runner.invoke(app, ["argument", "element", c, kind]).exit_code == 0
    for a, b, rel, reason in LINKS:
        args = ["argument", "link", f"{a} -> {b}", "--relation", rel] + (["--reason", reason] if reason else [])
        r = runner.invoke(app, args)
        assert r.exit_code == 0, r.output
    r = runner.invoke(app, ["argument", "link", "Patients want it -> Fund the drug", "--warrant",
                            "Patient preference is a funding criterion", "--qualifier", "probably"])
    assert r.exit_code == 0, r.output
    assert runner.invoke(app, ["argument", "check"]).exit_code == 0
    r = runner.invoke(app, ["argument", "show"])
    assert r.exit_code == 0 and "Fund the drug" in r.output
    r = runner.invoke(app, ["argument", "analyse"])
    assert r.exit_code == 0 and "Linchpin" in r.output and "unanswered" in r.output

    md = render(ProjectPaths(project), model_type="argument_map", ai=False)
    assert "Argument map: does the conclusion stand?" in md and "Linchpins" in md
    assert "Argument mapping evaluated by grounded labelling" in md  # foundations
    assert "flowchart BT" in md
    assert any(c.startswith("Fund the drug stands") for c in extract_claims("answer_to_question", "argument_map",
                                                                            root=project))
    assert any("Answer the open objection" in c for c in extract_claims("implications", "argument_map",
                                                                        root=project))

    (run,) = [x.run for x in report_results(root=project) if x.run.result_kind == "argument-analysis"]
    r = runner.invoke(app, ["argument", "claim", "Patients want it", "rejected", "--rationale", "carers only"])
    assert r.exit_code == 0 and is_stale(run, ProjectPaths(project))
    assert runner.invoke(app, ["argument", "claim", "Patients want it", "none"]).exit_code == 0

    _, spec = export_spec(model_type="argument_map", root=project)
    assert {(x.link, x.relation, x.reason) for x in spec.argument_map.links} >= {
        ("We can afford it -> Fund the drug", "supports", "value"),
        ("The budget is overspent -> We can afford it", "attacks", None)}
    other = project.parent / "rebuilt"
    init_project(other, statement="Q?")
    built = build_from_spec(spec, root=other)
    assert not built.notes
    assert am.analyse(root=other)["status"] == "in"

    client = TestClient(create_app(project_root=project))
    assert client.get("/api/argument/map").json()["elements"]
    r = client.post("/api/argument/element", json={"node": "Patients want it", "element": "claim"})
    assert r.status_code == 200
    r = client.post("/api/argument/link", json={"link": "Patients want it -> Fund the drug", "qualifier": "possibly"})
    assert r.status_code == 200 and r.json()["result"]["warrant"] == "Patient preference is a funding criterion"
    r = client.post("/api/argument/claim", json={"node": "We can afford it", "assessment": "accepted"})
    assert r.status_code == 200
    assert client.get("/api/argument/check").json()["ready"]
    res = client.post("/api/argument/analyse", json={"record": False}).json()
    assert res["result"]["status"] == "in"


def test_an_answer_that_keeps_the_conclusion_standing_is_a_linchpin(tmp_path, git_identity):
    # P supports C; O objects to C; R answers O. Take R away and O stands, so C falls: C rests on R.
    root = tmp_path / "defended"
    init_project(root, statement="Does it hold?")
    for c in ("C", "P", "O", "R"):
        node_ops.add_node(c, root=root)
    am.set_element("C", "conclusion", root=root)
    for claim in ("P", "O", "R"):
        am.set_element(claim, "claim", root=root)
    for a, b, rel in (("P", "C", "supports"), ("O", "C", "attacks"), ("R", "O", "attacks")):
        edge_ops.add_edge(a, b, root=root)
        am.set_link(f"{a} -> {b}", relation=rel, root=root)
    p = am.analyse(root=root)
    assert p["status"] == "in"
    assert sorted(x["claim"] for x in p["linchpins"]) == ["P", "R"]
    assert sorted(p["rests_on"]["none"]) == ["P", "R"]  # the unsourced rebuttal is listed with the premise
    assert "2 premise(s) it rests on have no checked source" in am.describe(p)


def test_problem_payload_and_more_structure_problems(project):
    """A map with problems reports only them; the conclusion offered for a claim, and two questions."""
    _build(project)
    node_ops.add_node("Is it worth it?", root=project)
    node_ops.add_node("Is it safe?", root=project)
    am.set_element("Is it worth it?", "question", root=project)
    am.set_element("Is it safe?", "question", root=project)
    kinds = [p.gap_type for p in am.structure_problems(root=project)]
    assert kinds == ["am_many_questions"]
    p = am.analyse(root=project)
    assert list(p) == ["problems"] and p["problems"][0]["label"] == "Is it worth it?"
    am.set_element("Is it safe?", "claim", root=project)
    edge_ops.add_edge("Fund the drug", "Is it safe?", root=project)
    kinds = [p.gap_type for p in am.structure_problems(root=project)]
    assert kinds == ["am_conclusion_not_top"]


def test_analysis_rows(project):
    """The full shape of an analysis: claims, reasons, both sides' objections, what it rests on."""
    _build(project)
    node_ops.add_node("Doctors recommend it", root=project)
    am.set_element("Doctors recommend it", "claim", root=project)
    edge_ops.add_edge("Doctors recommend it", "Fund the drug", root=project)
    am.set_link("Doctors recommend it -> Fund the drug", relation="supports", warrant="Clinical judgement",
                qualifier="probably", root=project)
    node_ops.add_node("Unrelated aside", root=project)
    am.set_element("Unrelated aside", "claim", root=project)
    p = am.analyse(root=project)
    assert p["conclusion"] == "Fund the drug" and p["question"] is None and p["status"] == "in"
    assert p["linchpins"] == []  # two independent reasons hold: neither alone is a linchpin
    assert sorted(p["rests_on"]["none"]) == ["Doctors recommend it", "Patients want it"]
    assert p["outside"] == ["Unrelated aside"]
    by_claim = {c["claim"]: c for c in p["claims"]}
    assert by_claim["Fund the drug"] == {"claim": "Fund the drug", "role": "conclusion", "status": "in",
                                         "given": False, "basis": "none"}
    assert by_claim["The budget is overspent"]["given"] is True
    doctors = next(r for r in p["reasons"] if r["premises"] == ["Doctors recommend it"])
    assert doctors == {"claim": "Fund the drug", "reason": None, "premises": ["Doctors recommend it"],
                       "status": "holds", "warrant": "Clinical judgement", "qualifier": "probably"}
    assert {o["objection"]: (o["against"], o["status"], o["answered"]) for o in p["objections"]} == {
        "The trial was small": ("The drug works", "out", True),
        "The budget is overspent": ("We can afford it", "in", False)}
    assert [(a["objection"], a["against"]) for a in p["answers"]] == [
        ("A second trial confirmed it", "The trial was small")]
    assert p["unverified_links"] == 7 and p["ai_links"] == 0 and p["challenged"] == []
