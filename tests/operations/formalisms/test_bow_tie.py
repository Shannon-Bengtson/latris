"""The bow-tie plugin: its report section, claims per section, mermaid sketch, spec check, outcome and rerun."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from latris.operations import bow_tie as bt
from latris.operations import edges as edge_ops
from latris.operations import formalisms
from latris.operations import nodes as node_ops
from latris.operations.analysis_results import get_result
from latris.operations.init import init_project
from latris.repo.layout import ProjectPaths
from tests.operations.test_bow_tie import ELEMENTS, LINKS, _classify, _quantify

F = formalisms.get("bow_tie")
KIND = F.results[0]


@pytest.fixture
def project(tmp_path, git_identity, monkeypatch):
    root = tmp_path / "gas"
    init_project(root, statement="How well protected are we against a loss of containment?")
    for label in ELEMENTS:
        node_ops.add_node(label, kind="event", root=root)
    for a, b in LINKS:
        edge_ops.add_edge(a, b, root=root)
    monkeypatch.chdir(root)
    return root


@pytest.fixture
def layered(tmp_path, git_identity, monkeypatch):
    """One threat and one consequence, each line behind two barriers in place, owned and sourced."""
    root = tmp_path / "layered"
    init_project(root, statement="Is the tank protected?")
    chain = [("Overfill", "threat"), ("Level alarm", "barrier"), ("High-level trip", "barrier"),
             ("Tank overflow", "top_event"), ("Bund", "barrier"), ("Drain valve closed", "barrier"),
             ("Spill to river", "consequence")]
    for label, _ in chain:
        node_ops.add_node(label, root=root)
    for (a, _), (b, _) in zip(chain, chain[1:], strict=False):
        edge_ops.add_edge(a, b, root=root)
    for label, el in chain:
        bt.set_element(label, el, root=root)
    for b in ("Level alarm", "High-level trip", "Bund", "Drain valve closed"):
        bt.set_barrier(b, owner="Site", root=root)
    monkeypatch.chdir(root)
    return root


def _claims(root, section):
    return F.claims(ProjectPaths(root), section)


def test_incomplete_bow_tie_claims_only_its_structure_and_refuses_to_run(project):
    (claim,) = _claims(project, "structure")
    assert claim.startswith("The bow-tie is incomplete: ") and "structure problem(s) (e.g." in claim
    assert all(_claims(project, s) == [] for s in ("answer", "sensitivity", "implications", "gaps"))
    with pytest.raises(ValueError, match="The bow-tie is incomplete"):
        KIND.run(SimpleNamespace(), project)


def test_unquantified_report_and_claims(project):
    _classify(project)
    node_ops.add_node("Weather", root=project)  # not a bow-tie element: an input from outside
    edge_ops.add_edge("Weather", "Corrosion", root=project)
    p = bt.analyse(root=project)
    text = "\n".join(KIND.render(p))
    assert text.startswith(bt.describe(p) + ".")
    assert "Top-event frequency" not in text and "*RAW*" not in text
    assert "| Side | Line | Barriers | Effective |" in text
    assert "| prevention | Impact damage → Loss of containment | — | 0 |" in text
    assert "| prevention | Corrosion → Loss of containment | Inspection programme → Corrosion inhibitor | 2 |" in text
    assert "- **No effective barrier:** Impact damage → Loss of containment" in text
    assert "- **Barriers on more than one line (one failure takes them all):** Gas detection" in text
    assert "- **Escalation factors with no control:** Relief valve not tested → Pressure relief valve" in text
    assert "- **Barriers with no owner:** " in text
    assert KIND.charts(p) == [("bt-lines", {})]

    structure = _claims(project, "structure")
    assert structure == [bt.describe(p) + ".",
                         "Hazard: Flammable gas under pressure; top event: Loss of containment.",
                         "Left out of the bow-tie (no bow-tie role): Weather → Corrosion."]
    answer = _claims(project, "answer")
    assert answer[0] == "Lines with no effective barrier: Impact damage → Loss of containment."
    assert answer[1].startswith("Lines resting on a single effective barrier: ")
    assert not any("per year" in c for c in answer)
    assert _claims(project, "sensitivity") == []  # nothing to rank until it is quantified
    impl = _claims(project, "implications")
    assert impl[0].startswith("Where another independent barrier would help most: Impact damage → Loss of "
                              "containment, ")
    assert "Barriers on more than one line — one failure defeats every line they guard: Gas detection." in impl
    assert "Escalation factors with no control: Relief valve not tested → Pressure relief valve." in impl
    assert any(c.startswith("Barriers nobody owns: ") for c in impl)
    gaps = _claims(project, "gaps")
    assert gaps == ["Not quantified — missing: Corrosion (frequency), Overpressure (frequency), Impact damage "
                    f"(frequency), {', '.join(p['missing'][3:6])} (+{len(p['missing']) - 6} more)."]


def test_quantified_report_and_claims(project):
    _classify(project)
    _quantify(project)
    bt.set_barrier("Corrosion inhibitor", status="degraded", source_id="vendor-sheet", root=project)
    p = bt.analyse(root=project)
    text = "\n".join(KIND.render(p))
    assert f"Top-event frequency: **{p['frequency']['top']:.4g} per year** (layer of protection" in text
    assert "consequences per year: Fire " in text
    assert "*RAW*: how many times more often the top event (prevention)" in text
    assert "| Barrier | Side | Failure probability | RAW | Where it came from |" in text
    assert "| Corrosion inhibitor | prevention | 0.1 |" in text and "(vendor-sheet); not verified |" in text
    assert "| Bypass permit |" not in text  # an escalation control has no line of its own to weigh
    assert "- **Barriers degraded or not in place:** Corrosion inhibitor" in text

    answer = _claims(project, "answer")
    assert f"Estimated frequency of Loss of containment: {p['frequency']['top']:.3g} per year (layer of " \
           "protection; barriers assumed independent)." in answer
    assert answer[-1].startswith("Consequences per year: Fire ")
    sens = _claims(project, "sensitivity")
    assert sens[0].startswith("Barriers by how much they buy (RAW:")
    ranked = [b for b in p["barriers"] if b["raw"] is not None][:5]
    assert sens[1:1 + len(ranked)] == [f"  - {b['barrier']} ({b['side']}): {b['raw']:.3g} (value not verified)"
                                       for b in ranked]
    assert sens[-1].startswith("The barriers that matter most whose failure probability nobody has verified: ")
    assert "Barriers degraded or not in place: Corrosion inhibitor." in _claims(project, "implications")
    gaps = _claims(project, "gaps")
    assert not any(c.startswith("Not quantified") for c in gaps)
    (unsourced,) = [c for c in gaps if c.startswith("Failure probabilities with no stated source: ")]
    assert "Corrosion inhibitor" not in unsourced


def test_zero_frequencies_leave_nothing_to_rank(project):
    _classify(project)
    _quantify(project)
    for t in ("Corrosion", "Overpressure", "Impact damage"):
        bt.set_frequency(t, 0.0, root=project)
    assert bt.analyse(root=project)["quantified"]
    # No barrier changes anything when nothing reaches the top event: no ranking heading with nothing under it.
    assert _claims(project, "sensitivity") == [
        "At the threat frequencies given nothing reaches Loss of containment, so no barrier can be ranked by how "
        "much it buys."]


def test_every_line_behind_two_barriers(layered):
    assert _claims(layered, "answer") == ["Every line has at least two effective barriers."]
    assert _claims(layered, "implications") == []
    assert _claims(layered, "gaps") == ["Not quantified — missing: Overfill (frequency), Level alarm (failure "
                                        "probability), High-level trip (failure probability), Bund (failure "
                                        "probability), Drain valve closed (failure probability)."]
    p = bt.analyse(root=layered)
    text = "\n".join(KIND.render(p))
    assert "- **" not in text  # nothing to flag


def test_mermaid(project):
    _classify(project)
    bt.set_barrier("Gas detection", status="not_in_place", pfd=0.1, root=project)
    from latris.repo.yaml_io import load_model
    from latris.schema import Substrate

    sub = load_model(Substrate, ProjectPaths(project).conceptual_yaml)
    node_ops.add_node("Bystander", root=project)  # no bow-tie role: not drawn
    sub = load_model(Substrate, ProjectPaths(project).conceptual_yaml)
    src = F.mermaid(ProjectPaths(project), sub.entities, sub.edges)
    assert src.startswith("flowchart LR\n") and "Bystander" not in src
    alias = {e.label: f"n{i}" for i, e in enumerate(x for x in sub.entities if x.label in ELEMENTS)}
    assert f'{alias["Flammable gas under pressure"]}[/"Flammable gas under pressure"/]' in src
    assert f'{alias["Loss of containment"]}(("Loss of containment"))' in src
    assert f'{alias["Gas detection"]}["Gas detection<br/>not in place<br/>pfd 0.1"]' in src
    assert f'{alias["Detector bypassed for maintenance"]}>"Detector bypassed for maintenance"]' in src
    assert f'{alias["Flammable gas under pressure"]} -.-> {alias["Loss of containment"]}' in src
    assert f'{alias["Corrosion"]} --> {alias["Inspection programme"]}' in src
    assert f'style {alias["Gas detection"]} stroke:#c0392b,stroke-dasharray:4 3' in src
    assert F.mermaid(ProjectPaths(project), [], []) == ""


def test_spec_check():
    block = SimpleNamespace(elements=[SimpleNamespace(node="Leak", type="threat"), SimpleNamespace(node="Ghost",
                                                                                                    type="barrier")],
                            barriers=[SimpleNamespace(node="Phantom")], frequencies=[SimpleNamespace(node="Nowhere")],
                            uncertainty=[])
    known = {"Leak"}.__contains__
    assert F.spec_check(block, known, "leak") == [
        "bowtie element: no factor named 'Ghost'", "bowtie barrier: no factor named 'Phantom'",
        "bowtie frequency: no factor named 'Nowhere'",
        "bowtie element: 'Leak' is the outcome, so it is the top event, not threat"]


def test_outcome_export_and_rerun(project):
    paths = ProjectPaths(project)
    assert F.outcome_ids(paths) == set() and F.spec_export(paths, {}) is None
    F.set_outcome("Loss of containment", project)
    (top,) = F.outcome_ids(paths)
    assert bt.get_elements(root=project)[top] == "top_event"
    _classify(project)
    a = KIND.definition(bt.analyse(root=project))
    assert a.kind == "bowtie_analyse"
    run, payload = get_result(KIND.run(a, project), root=project)
    assert run.result_kind == "bt-analysis" and payload["top"] == "Loss of containment"
