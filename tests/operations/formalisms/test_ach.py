"""The ACH plugin: its report section, claims per section, mermaid sketch, spec check and rerun."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from latris.operations import ach, formalisms
from latris.operations import nodes as node_ops
from latris.operations.analysis_results import get_result
from latris.operations.init import init_project
from latris.repo.layout import ProjectPaths
from tests.operations.test_ach import HYPS, ITEMS, _build


@pytest.fixture
def project(tmp_path, git_identity, monkeypatch):
    root = tmp_path / "outage"
    init_project(root, statement="Why did the service go down on Tuesday?")
    for label in [*HYPS, *ITEMS]:
        node_ops.add_node(label, root=root)
    monkeypatch.chdir(root)
    return root


F = formalisms.get("ach")
(KIND,) = F.results


def _claims(root, section):
    return F.claims(ProjectPaths(root), section)


def test_incomplete_matrix_claims_only_its_structure_and_refuses_to_run(project):
    ach.set_element(HYPS[0], "hypothesis", root=project)
    (claim,) = _claims(project, "structure")
    assert claim.startswith("The ACH matrix is incomplete:") and "structure problem(s) (e.g." in claim
    assert all(_claims(project, s) == [] for s in ("answer", "sensitivity", "implications", "gaps"))
    assert F.mermaid(ProjectPaths(project), [], []) == ""
    with pytest.raises(ValueError, match="The ACH matrix is incomplete"):
        KIND.run(SimpleNamespace(), project)


def test_report_section(project):
    _build(project)
    p = ach.analyse(root=project)
    text = "\n".join(KIND.render(p))
    assert text.startswith("Software bug has the least evidence against it (0.00); then")
    assert "| Hypothesis | Weighted inconsistency | Evidence against it | Consistent items |" in text
    assert "| Software bug | 0.00 | — | 3 |" in text
    assert "| Cyber attack | 2.00 | No unusual network traffic | 2 |" in text
    assert f"| Evidence | {' | '.join(sorted(HYPS))} | Credibility/relevance | Source |" in text
    assert "| Outage began right after a deploy | C | I | CC | high/high | no source |" in text
    assert "CC very consistent" in text
    assert "Linchpins — without any one of these the lead would change or be tied: " in text
    assert "Rated the same against every hypothesis, so they don't help choose: Restart fixed it." in text
    assert KIND.charts(p) == [("ach-matrix", {})]


def test_claims_by_section(project):
    _build(project)
    assert _claims(project, "structure") == ["3 hypotheses weighed against 4 evidence items."]
    answer = _claims(project, "answer")
    assert answer[0].startswith("Software bug has the least evidence against it")
    assert "Cyber attack is contradicted by: No unusual network traffic." in answer
    assert "Hardware failure is contradicted by: Outage began right after a deploy." in answer
    sens = _claims(project, "sensitivity")
    assert "The conclusion turns on No unusual network traffic (no source, credibility high)." in sens
    impl = _claims(project, "implications")
    assert impl[0] == ("Look next for evidence that would be inconsistent with Software bug but not "
                       "Hardware failure, or the reverse.")
    assert any(c.startswith("Check the sources behind these linchpins first: ") for c in impl)
    assert "These items don't discriminate and can be set aside: Restart fixed it." in impl
    gaps = _claims(project, "gaps")
    assert gaps[0] == f"Evidence items with no source: {', '.join(sorted(ITEMS))}."
    # Ratings entered through the operations are a person's, so no AI share is named.
    assert gaps[1] == "12 rating(s) not reviewed by a person."
    assert _claims(project, "no such section") == []


def test_no_linchpin_and_ai_ratings(project):
    _build(project)
    # A second item against the cyber attack and the hardware failure: no single item now decides the lead.
    ach.set_rating("Disk errors in logs", "Cyber attack", "II", root=project)
    ach.set_rating("Disk errors in logs", "Hardware failure", "C", root=project)
    ach.set_rating("Restart fixed it", "Hardware failure", "I", origin="ai-proposed", root=project)
    p = ach.analyse(root=project)
    assert p["linchpins"] == [] and p["leading"] == ["Software bug"]
    assert _claims(project, "sensitivity") == ["No single evidence item changes the leading hypothesis."]
    assert not any("linchpins first" in c for c in _claims(project, "implications"))
    assert _claims(project, "gaps")[1] == "12 rating(s) not reviewed by a person (1 proposed by AI)."
    assert "Linchpins" not in "\n".join(KIND.render(p))


def test_mermaid_draws_only_the_evidence_against(project):
    _build(project)
    src = F.mermaid(ProjectPaths(project), [], [])
    assert src.startswith("flowchart LR\n")
    assert 'h2(["Software bug<br/>against: 0.00"])' in src  # hypotheses numbered in name order
    assert 'e1["No unusual network traffic"]\n    e1 -.->|II| h0' in src
    assert 'e2["Outage began right after a deploy"]\n    e2 -.->|I| h1' in src
    assert "Restart fixed it" not in src and "Disk errors in logs" not in src  # nothing against anything


def test_spec_check_names_unknown_factors():
    block = SimpleNamespace(elements=[SimpleNamespace(node="H1")], items=[SimpleNamespace(node="E9")],
                            ratings=[SimpleNamespace(item="E1", hypothesis="H9")])
    known = {"H1", "E1"}.__contains__
    assert F.spec_check(block, known, None) == ["ach item: no factor named 'E9'",
                                                 "ach rating: no factor named 'H9'"]


def test_run_records_and_definition_reruns(project):
    _build(project)
    a = KIND.definition(ach.analyse(root=project))
    assert a.kind == "ach_analyse"
    run, payload = get_result(KIND.run(a, project), root=project)
    assert run.result_kind == "ach-analysis" and payload["leading"] == ["Software bug"]
