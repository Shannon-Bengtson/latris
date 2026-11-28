"""The Markov plugin: its report section, claims per section, charts, mermaid sketch, spec check and rerun."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from latris.operations import edges as edge_ops
from latris.operations import formalisms, markov
from latris.operations import nodes as node_ops
from latris.operations.analysis_results import get_result
from latris.operations.init import init_project
from latris.repo.layout import ProjectPaths
from tests.operations.test_markov import _full, _tiny

F = formalisms.get("markov")
KIND = F.results[0]


@pytest.fixture
def project(tmp_path, git_identity, monkeypatch):
    root = tmp_path / "cohort"
    init_project(root, statement="Is the new drug worth its cost?")
    for n in ("Healthy", "Sick", "Dead", "Standard care", "New drug"):
        node_ops.add_node(n, root=root)
    for a, b in (("Healthy", "Sick"), ("Healthy", "Dead"), ("Sick", "Dead")):
        edge_ops.add_edge(a, b, root=root)
    monkeypatch.chdir(root)
    return root


def _claims(root, section):
    return F.claims(ProjectPaths(root), section)


def test_incomplete_model_claims_only_its_structure_and_refuses_to_run(project):
    markov.set_element("Healthy", "state", root=project)
    (claim,) = _claims(project, "structure")
    assert claim.startswith("The Markov model is incomplete: ") and "structure problem(s) (e.g." in claim
    assert all(_claims(project, s) == [] for s in ("answer", "sensitivity", "implications", "gaps"))
    assert F.mermaid(ProjectPaths(project), [], []) == ""
    with pytest.raises(ValueError, match="The Markov model is incomplete"):
        KIND.run(SimpleNamespace(), project)


def test_one_strategy_reads_without_an_incremental_analysis(project):
    _tiny(project)
    p = markov.analyse(root=project)
    text = "\n".join(KIND.render(p))
    assert "2 cycles of 1 year; discounting 0.0% for costs, 0.0% for outcomes; half-cycle correction off." in text
    assert "| Strategy | Cost (discounted) | outcome units (discounted) | Cost (undiscounted) |" in text
    assert "| Base case | 150 | 1.500 | 150 | 1.500 |" in text
    assert "Incremental analysis" not in text
    assert "Expected time in each state (years, undiscounted):" in text and "| Healthy | 1.50 |" in text
    assert "Note: no cost for Dead (counted as 0); no utility for Dead (counted as 0)." in text
    assert KIND.charts(p) == [("markov-trace", {})]
    assert _claims(project, "structure") == [
        "A cohort model of 2 states (Dead, Healthy) over 2 cycles of 1 year, comparing Base case."]
    assert _claims(project, "implications") == []  # nothing to compare, so no willingness to pay is asked for
    gaps = _claims(project, "gaps")
    assert gaps == ["States counted as costing nothing or worth nothing because no value is recorded: Dead.",
                    "Transitions with no source: Healthy → Dead."]
    assert _claims(project, "sensitivity") == ["Transition probabilities not verified: Healthy → Dead."]


def test_two_strategies_report_and_claims(project):
    _full(project)
    p = markov.analyse(root=project)
    text = "\n".join(KIND.render(p))
    assert "30 cycles of 1 year; discounting 3.5% for costs, 3.5% for outcomes; half-cycle correction on." in text
    assert "| Strategy | Cost (discounted) | QALY (discounted) |" in text
    assert "Incremental analysis, cheapest first." in text
    new = next(r for r in p["incremental"] if r["strategy"] == "New drug")
    assert f"| {markov._money(new['icer'], '£')} per QALY vs Standard care |" in text
    assert f"At a willingness to pay of £20,000 per QALY, {p['choice']} has the highest net monetary benefit." in text
    assert "Note:" not in text
    assert KIND.charts(p) == [("markov-trace", {}), ("markov-ce", {})]
    assert _claims(project, "answer") == [markov.describe(p) + "."]
    sens = _claims(project, "sensitivity")
    assert sens[0] == (f"New drug is worth choosing over Standard care only if a unit of QALY is worth more than "
                       f"{markov._money(new['icer'], '£')} — its ICER is the threshold.")
    assert sens[1] == "Transition probabilities not verified: Healthy → Dead, Healthy → Sick, Sick → Dead."
    assert _claims(project, "implications") == [f"At £20,000 per QALY, choose {p['choice']}."]
    assert _claims(project, "gaps") == ["Transitions with no source: Healthy → Dead, Sick → Dead."]


def test_no_willingness_to_pay_and_a_dominated_strategy(project):
    _full(project)
    markov.set_settings(wtp=None, root=project)
    # The drug now makes people sicker: dearer and worse, so dominated whatever a QALY is worth.
    markov.set_transition("Healthy -> Sick", 0.2, strategy="New drug", root=project)
    p = markov.analyse(root=project)
    assert "choice" not in p
    text = "\n".join(KIND.render(p))
    assert "| New drug |" in text and "| dominated | by Standard care |" in text
    assert "willingness to pay of" not in text
    impl = _claims(project, "implications")
    assert impl == ["Never cost-effective, whatever the willingness to pay: New drug (dominated).",
                    "Set a willingness to pay (`latris markov settings --wtp`) to name the strategy to choose."]
    assert not any("ICER is the threshold" in c for c in _claims(project, "sensitivity"))


def test_mermaid(project):
    _full(project)
    src = F.mermaid(ProjectPaths(project), [], [])
    assert src.startswith("flowchart LR\n")
    assert 's0[["Dead"]]' in src and 's1(["Healthy"])' in src  # nobody leaves the absorbing state
    assert 's1 -->|"0.1"| s2' in src and 's2 -->|"0.2"| s0' in src
    # A transition given only for one strategy has no base value to show.
    edge_ops.add_edge("Sick", "Healthy", root=project)
    markov.set_transition("Sick -> Healthy", 0.3, strategy="New drug", root=project)
    assert not markov.structure_problems(root=project)
    assert 's2 -->|"by strategy"| s1' in F.mermaid(ProjectPaths(project), [], [])


def test_spec_check():
    block = SimpleNamespace(
        elements=[SimpleNamespace(node="Ghost")],
        transitions=[SimpleNamespace(link="Well -> Ill", strategy=None), SimpleNamespace(link="Well to Ill", strategy=None),
                     SimpleNamespace(link="Well -> Nowhere", strategy="Plan Z")],
        rewards=[SimpleNamespace(state="Limbo", strategy=None)], start=[SimpleNamespace(state="Well")],
        ranges=[SimpleNamespace(target="Well -> Ill", strategy="Plan Y")],
        correlations=[SimpleNamespace(target="Well -> Ill", other="Fog", strategy=None, other_strategy="Plan X")])
    known = {"Well", "Ill"}.__contains__
    assert F.spec_check(block, known, None) == [
        "markov element: no factor named 'Ghost'",
        "markov transition 'Well to Ill': write it as 'From state -> To state'",
        "markov transition: no factor named 'Nowhere'",
        "markov: no factor named 'Limbo'", "markov: no factor named 'Plan Z'",
        "markov range: no factor named 'Plan Y'",
        "markov correlation: no factor named 'Fog'", "markov correlation: no factor named 'Plan X'"]


def test_run_records_and_definition_reruns(project):
    _full(project)
    a = KIND.definition(markov.analyse(root=project))
    assert a.kind == "markov_analyse"
    run, payload = get_result(KIND.run(a, project), root=project)
    assert run.result_kind == "markov-analysis" and payload["choice"] == markov.analyse(root=project)["choice"]
    assert F.spec_export(ProjectPaths(project), {}) is None  # nothing labelled: nothing to export
