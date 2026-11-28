"""The argument-map plugin: its report section, claims per section, mermaid sketch, spec check, outcome, rerun."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from latris.operations import argument_map as am
from latris.operations import edges as edge_ops
from latris.operations import formalisms
from latris.operations import nodes as node_ops
from latris.operations.analysis_results import get_result
from latris.operations.init import init_project
from latris.repo.layout import ProjectPaths
from tests.operations.test_argument_map import CLAIMS, LINKS, _build


@pytest.fixture
def project(tmp_path, git_identity, monkeypatch):
    root = tmp_path / "case"
    init_project(root, statement="Should we fund the new drug?")
    for c in CLAIMS:
        node_ops.add_node(c, root=root)
    for a, b, _, _ in LINKS:
        edge_ops.add_edge(a, b, root=root)
    monkeypatch.chdir(root)
    return root


F = formalisms.get("argument_map")
(KIND,) = F.results


def _claims(root, section):
    return F.claims(ProjectPaths(root), section)


def test_incomplete_map_claims_only_its_structure_and_refuses_to_run(project):
    am.set_element("Fund the drug", "conclusion", root=project)
    am.set_element("Patients want it", "conclusion", root=project)
    (claim,) = _claims(project, "structure")
    assert claim.startswith("The argument map is incomplete: ") and "structure problem(s) (e.g." in claim
    assert all(_claims(project, s) == [] for s in ("answer", "sensitivity", "implications", "gaps"))
    assert F.mermaid(ProjectPaths(project), [], []) == ""
    with pytest.raises(ValueError, match="The argument map is incomplete"):
        KIND.run(SimpleNamespace(), project)


def test_report_section(project):
    _build(project)
    node_ops.add_node("Should we fund it?", root=project)
    am.set_element("Should we fund it?", "question", root=project)
    node_ops.add_node("Unrelated aside", root=project)
    am.set_element("Unrelated aside", "claim", root=project)
    am.set_link("Patients want it -> Fund the drug", warrant="Preference | need", qualifier="probably", root=project)
    p = am.analyse(root=project)
    text = "\n".join(KIND.render(p))
    assert text.startswith("Fund the drug stands on 1 reason(s)")
    assert "The question: Should we fund it?" in text
    assert "| For | Because | Holds? | Qualifier | Warrant |" in text
    assert "| Fund the drug | The drug works + We can afford it | fails | — | — |" in text
    # The table escapes a cell once: a pipe in the warrant must not end the cell.
    assert "| Fund the drug | Patients want it | holds | probably | Preference \\| need |" in text
    assert "| The trial was small | The drug works | defeated | answered |" in text
    assert "| The budget is overspent | We can afford it | stands | **unanswered** |" in text
    assert "Answers to objections:" in text and "| A second trial confirmed it | The trial was small | stands |" in text
    assert "The conclusion rests on premises taken as given: 1 with no source." in text
    assert "Without a checked source: Patients want it." in text
    assert "Linchpins — if any one were rejected, the conclusion would no longer stand: Patients want it (no source)." \
        in text
    assert "Claims that don't bear on the conclusion: Unrelated aside." in text
    assert "Inferences under an open challenge" not in text
    assert "grounded labelling, Dung 1995" in text


def test_a_challenged_inference_and_a_defeated_conclusion(project):
    from latris.operations.challenges import open_challenge

    _build(project)
    open_challenge("The trial was small -> The drug works", "Small but well powered.", root=project)
    open_challenge("Patients want it -> Fund the drug", "Wanting it isn't a reason to fund it.", root=project)
    p = am.analyse(root=project)
    assert p["status"] == "out"
    text = "\n".join(KIND.render(p))
    assert "| The trial was small | The drug works | defeated | inference challenged |" in text
    assert "Inferences under an open challenge (counted for nothing until resolved): " in text
    assert "The conclusion rests on" not in text and "Linchpins" not in text
    impl = _claims(project, "implications")
    assert any(c.startswith("Resolve the challenges to these inferences: ") for c in impl)


def test_claims_by_section(project):
    _build(project)
    assert _claims(project, "structure") == [
        "An argument for Fund the drug: 2 reason(s) and 2 objection(s) over 7 claims."]
    assert _claims(project, "answer")[0].startswith("Fund the drug stands on 1 reason(s)")
    sens = _claims(project, "sensitivity")
    assert sens[0] == "The conclusion turns on Patients want it (no source)."
    impl = _claims(project, "implications")
    assert impl[0] == "Find or check sources for the linchpins first: Patients want it."
    assert "Answer the open objection(s) before relying on the conclusion: The budget is overspent." in impl
    gaps = _claims(project, "gaps")
    assert gaps[0] == ("2 reason(s) don't say why the premise bears on the claim (no warrant): "
                       "Fund the drug ← Patients want it, Fund the drug ← The drug works + We can afford it.")
    assert "Premises asserted with no source: Patients want it." in gaps
    assert "6 link(s) not reviewed by a person." in gaps
    assert _claims(project, "no such section") == []


def test_an_unanswered_objection_the_conclusion_stands_without_is_not_said_to_change_it(project):
    # The budget objection defeats one reason, but the conclusion stands on another: answering it changes nothing.
    _build(project)
    p = am.analyse(root=project)
    assert p["status"] == "in" and [o["objection"] for o in p["unanswered"]] == ["The budget is overspent"]
    assert not any("would change the outcome" in c for c in _claims(project, "sensitivity"))
    # Take the other reason away and the conclusion now falls with the objection: answering it would change that.
    am.set_claim("Patients want it", assessment="rejected", rationale="Carers, not patients.", root=project)
    assert am.analyse(root=project)["status"] == "out"
    assert ("Answering the objection 'The budget is overspent' (against We can afford it) would change the outcome."
            in _claims(project, "sensitivity"))


def test_no_linchpin_when_two_reasons_hold(project):
    _build(project)
    node_ops.add_node("Doctors recommend it", root=project)
    am.set_element("Doctors recommend it", "claim", root=project)
    edge_ops.add_edge("Doctors recommend it", "Fund the drug", root=project)
    am.set_link("Doctors recommend it -> Fund the drug", relation="supports", warrant="Clinical judgement",
                origin="ai-proposed", root=project)
    assert "No single premise, rejected, would stop the conclusion standing." in _claims(project, "sensitivity")
    assert not any("linchpins first" in c for c in _claims(project, "implications"))
    assert "7 link(s) not reviewed by a person (1 proposed by AI)." in _claims(project, "gaps")


def test_mermaid(project):
    _build(project)
    src = F.mermaid(ProjectPaths(project), [], [])
    assert src.startswith("flowchart BT\n")
    assert 'a1(["Fund the drug"]):::in' in src  # the conclusion is the rounded one
    assert 'a5["The trial was small"]:::out' in src
    assert 'a4 -->|"value"| a1' in src and 'a6 -->|"value"| a1' in src  # one reason, two premises
    assert "a2 --> a1" in src  # a reason of its own carries no tag
    assert 'a3 -.->|"attacks"| a6' in src
    assert "classDef out stroke-dasharray:4 3,opacity:0.6" in src


def test_spec_check():
    block = SimpleNamespace(elements=[SimpleNamespace(node="C"), SimpleNamespace(node="Ghost")],
                            claims=[SimpleNamespace(node="Phantom")],
                            links=[SimpleNamespace(link="P -> C"), SimpleNamespace(link="P supports C"),
                                   SimpleNamespace(link="P -> Nowhere")])
    known = {"C", "P"}.__contains__
    assert F.spec_check(block, known, None) == [
        "argument element: no factor named 'Ghost'", "argument claim: no factor named 'Phantom'",
        "argument link 'P supports C': write it as 'Premise -> Claim'", "argument link: no factor named 'Nowhere'"]


def test_outcome_is_the_conclusion(project):
    paths = ProjectPaths(project)
    assert F.outcome_ids(paths) == set()
    F.set_outcome("Fund the drug", project)
    (cid,) = F.outcome_ids(paths)
    assert am.get_elements(root=project)[cid] == "conclusion"
    assert F.spec_export(paths, {}) is None  # nothing labelled: nothing to export


def test_run_records_and_definition_reruns(project):
    _build(project)
    a = KIND.definition(am.analyse(root=project))
    assert a.kind == "argument_analyse"
    run, payload = get_result(KIND.run(a, project), root=project)
    assert run.result_kind == "argument-analysis" and payload["status"] == "in"
