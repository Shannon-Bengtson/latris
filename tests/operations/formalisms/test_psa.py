"""The shared PSA plugin pieces: report sections and claims for decision trees and Markov models, rerun, spec."""

from __future__ import annotations

import pytest

from latris.operations import edges as edge_ops
from latris.operations import formalisms, markov, psa
from latris.operations import nodes as node_ops
from latris.operations.analysis_results import get_result
from latris.operations.formalisms import _psa
from latris.operations.init import init_project
from latris.repo.layout import ProjectPaths
from tests.operations import test_decision_tree as DT
from tests.operations import test_markov as MK

SECTIONS = ("sensitivity", "open_questions", "confidence_assessment", "implications", "assumptions_limitations")


@pytest.fixture
def dt_project(tmp_path, git_identity, monkeypatch):
    root = tmp_path / "launch"
    init_project(root, statement="Should we launch the product ourselves, license it, or do nothing?")
    for n in DT.NODES:
        node_ops.add_node(n, root=root)
    for a, b, _, _ in DT.BRANCHES:
        edge_ops.add_edge(a, b, kind="conditional", root=root)
    DT._build(root)
    monkeypatch.chdir(root)
    return root


@pytest.fixture
def mk_project(tmp_path, git_identity, monkeypatch):
    root = tmp_path / "cohort"
    init_project(root, statement="Is the new drug worth its cost?")
    for n in ("Healthy", "Sick", "Dead", "Standard care", "New drug"):
        node_ops.add_node(n, root=root)
    for a, b in (("Healthy", "Sick"), ("Healthy", "Dead"), ("Sick", "Dead")):
        edge_ops.add_edge(a, b, root=root)
    MK._full(root)
    monkeypatch.chdir(root)
    return root


def _kind(analysis):
    return formalisms.for_analysis(analysis)


def _claims(p):
    out = {k: [] for k in SECTIONS}
    _kind("markov_psa" if p["model_type"] == "markov" else "dt_psa").claims(p, out)
    return out


def test_decision_tree_section_and_claims(dt_project):
    psa.set_range("decision_tree", "Launched, high", "normal", {"mean": 500, "sd": 100}, reason="sales | survey",
                  root=dt_project)
    psa.set_range("decision_tree", "Launched, low", "normal", {"mean": -200, "sd": 60}, root=dt_project)
    p = psa.dt_psa(runs=2000, root=dt_project)
    text = "\n".join(_kind("dt_psa").render(p))
    assert text.startswith(psa.describe(p).replace("|", "\\|") + ".")
    assert "— option | Point estimate | Mean | 5th pct | 95th pct | Best in |" in text
    assert "Expected value of perfect information on the parameters: " in text
    # No "per person" for a one-off choice.
    assert "What knowing each input exactly before choosing would be worth, the rest still uncertain (partial " \
        "EVPI; all of them together: " in text
    assert "What drives the advantage of License over Launch: each uncertain input's range" in text
    # The table escapes the cell once: a pipe in a reason must not end the cell.
    assert "| Launched, high (payoff) | normal (5th–95th: " in text and "| sales \\| survey | unverified |" in text
    assert "Held at their point value (no range given): " in text
    assert "2000 runs, Latin hypercube sampling, seed 1234. Inputs are sampled independently, each once per run." \
        in text
    assert _kind("dt_psa").charts(p) == [("mc-strip", {})]

    out = _claims(p)
    assert out["sensitivity"] == [psa.describe(p) + "."]
    launch = next(o["p_best"] for o in p["outputs"] if o["output"] == "Launch")
    assert out["confidence_assessment"] == [
        f"The best choice is not settled by the evidence: Launch comes out best in {launch:.0%} of the runs."]
    assert out["implications"][0].startswith("Research that removes the parameter uncertainty is worth at most ")
    assert out["implications"][1].startswith("Of the uncertain inputs, learning ")
    assert "; next " in out["implications"][1]
    assert out["open_questions"][0].startswith("The ranges driving most of the uncertainty in the advantage of "
                                               "License over Launch haven't been checked: ")
    assert "lower bound on the real uncertainty" in out["assumptions_limitations"][0]


def test_no_single_input_worth_learning(dt_project):
    psa.set_range("decision_tree", "Launched, high", "normal", {"mean": 500, "sd": 100}, root=dt_project)
    p = psa.dt_psa(runs=500, root=dt_project)
    assert p["evpi"] > 0
    p["evppi"] = [{**r, "evppi": 0.0} for r in p["evppi"]]  # each within noise of zero
    assert "No single input is worth learning on its own" in _claims(p)["implications"][-1]
    p["evppi"] = []
    assert not any("worth learning" in c for c in _claims(p)["implications"])
    assert "partial EVPI" not in "\n".join(_kind("dt_psa").render(p))


def test_decision_tree_definition_reruns(dt_project):
    psa.set_range("decision_tree", "Launched, high", "normal", {"mean": 500, "sd": 100}, root=dt_project)
    p = psa.dt_psa(runs=300, seed=7, sampling="random", root=dt_project)
    assert "300 runs, random sampling, seed 7." in "\n".join(_kind("dt_psa").render(p))
    a = _kind("dt_psa").definition(p)
    assert (a.kind, a.runs, a.seed, a.sampling) == ("dt_psa", 300, 7, "random")
    run, payload = get_result(_kind("dt_psa").run(a, dt_project), root=dt_project)
    assert run.result_kind == "dt-psa" and payload["outputs"] == p["outputs"]


def test_markov_section_and_claims(mk_project):
    psa.set_range("markov", "Healthy -> Sick", "beta", {"mean": 0.10, "sd": 0.02}, root=mk_project)
    psa.set_range("markov", "Healthy -> Sick", "beta", {"mean": 0.06, "sd": 0.015}, strategy="New drug",
                  root=mk_project)
    psa.set_range("markov", "Sick", "gamma", {"mean": 3000, "sd": 600}, quantity="cost", root=mk_project)
    p = psa.markov_psa(runs=500, root=mk_project)
    text = "\n".join(_kind("markov_psa").render(p))
    assert "| Strategy | Mean cost | Cost, 90% of runs | Mean QALY | QALY, 90% of runs |" in text
    assert "Incremental analysis on the probabilistic means:" in text and " per QALY vs Standard care |" in text
    assert "Probability each strategy is the most cost-effective, by willingness to pay per QALY" in text
    assert "| Willingness to pay per QALY |" in text and "| £0 |" in text
    assert "What knowing each input exactly before choosing would be worth per person" in text
    assert "scaled down to 1" not in text
    assert _kind("markov_psa").charts(p) == [("markov-ceac", {})]
    out = _claims(p)
    assert out["sensitivity"] == [psa.describe(p) + "."]
    if p["p_cost_effective"] < 0.8:
        assert out["confidence_assessment"][0].startswith(f"{p['choice']} is the most cost-effective at the "
                                                          "willingness to pay in only ")
    assert any(c.startswith("Further research is worth at most £") and c.endswith(
        "per person affected by the decision (the EVPI at the willingness to pay).") for c in out["implications"])


def test_correlated_inputs_are_not_said_to_be_sampled_independently(mk_project):
    psa.set_range("markov", "Healthy -> Sick", "beta", {"mean": 0.10, "sd": 0.02}, root=mk_project)
    psa.set_range("markov", "Healthy -> Sick", "beta", {"mean": 0.06, "sd": 0.015}, strategy="New drug",
                  root=mk_project)
    psa.set_correlation("markov", "Healthy -> Sick", "Healthy -> Sick", 0.8, other_strategy="New drug",
                        reason="same registry cohort", root=mk_project)
    p = psa.markov_psa(runs=200, root=mk_project)
    text = "\n".join(_kind("markov_psa").render(p))
    assert ("Sampled together: P(Healthy → Sick) and P(Healthy → Sick) under New drug (rank correlation +0.8: "
            "same registry cohort).") in text
    assert "Inputs are sampled independently" not in text
    assert "The other inputs are sampled independently, each once per run." in text


def test_markov_one_strategy_and_rescaled_runs(tmp_path, git_identity, monkeypatch):
    root = tmp_path / "tiny"
    init_project(root, statement="How long do they stay well?")
    for n in ("Healthy", "Sick", "Dead"):
        node_ops.add_node(n, root=root)
    for a, b in (("Healthy", "Sick"), ("Healthy", "Dead")):
        edge_ops.add_edge(a, b, root=root)
    for s in ("Healthy", "Sick", "Dead"):
        markov.set_element(s, "state", root=root)
    markov.set_transition("Healthy -> Sick", 0.5, root=root)
    markov.set_transition("Healthy -> Dead", 0.45, root=root)
    markov.set_start("Healthy", 1, root=root)
    psa.set_range("markov", "Healthy -> Sick", "uniform", {"min": 0.3, "max": 0.7}, root=root)
    psa.set_range("markov", "Healthy -> Dead", "uniform", {"min": 0.25, "max": 0.65}, root=root)
    p = psa.markov_psa(runs=200, root=root)
    assert p["rescaled_runs"] > 0
    text = "\n".join(_kind("markov_psa").render(p))
    assert f"In {p['rescaled_runs']} run(s) the sampled probabilities of leaving a state summed to more than 1" \
        in text
    assert "| Mean outcome |" in text  # no outcome units: named generically
    assert "acceptability curve" not in text and "Incremental analysis" not in text
    assert _kind("markov_psa").charts(p) == []
    out = _claims(p)  # nothing to choose between: no cost-effectiveness claims
    assert out["confidence_assessment"] == [] and not any("Further research" in c for c in out["implications"])


def test_spec_export_leaves_out_what_the_labels_dont_name(mk_project):
    psa.set_range("markov", "Healthy -> Sick", "beta", {"mean": 0.06, "sd": 0.015}, strategy="New drug",
                  root=mk_project)
    psa.set_range("markov", "Sick", "gamma", {"mean": 3000, "sd": 600}, quantity="cost", root=mk_project)
    psa.set_range("markov", "Healthy -> Sick", "beta", {"mean": 0.10, "sd": 0.02}, root=mk_project)
    psa.set_correlation("markov", "Healthy -> Sick", "Sick", 0.3, other_quantity="cost", root=mk_project)
    psa.set_correlation("markov", "Healthy -> Sick", "Healthy -> Sick", 0.5, other_strategy="New drug",
                        root=mk_project)
    paths = ProjectPaths(mk_project)
    from latris.repo.yaml_io import load_model
    from latris.schema import Substrate

    every = {e.id: e.label for e in load_model(Substrate, paths.conceptual_yaml).entities}
    assert [(r.target, r.quantity, r.strategy) for r in _psa.spec_export("markov", paths, every)] == [
        ("Healthy -> Sick", "transition", None), ("Healthy -> Sick", "transition", "New drug"),
        ("Sick", "cost", None)]
    assert len(_psa.spec_export_correlations("markov", paths, every)) == 2
    assert _psa.spec_export_correlations("decision_tree", paths, every) == []  # each type its own
    no_sick = {k: v for k, v in every.items() if v != "Sick"}  # the link and the state both go
    assert _psa.spec_export("markov", paths, no_sick) == []
    assert _psa.spec_export_correlations("markov", paths, no_sick) == []
    no_drug = {k: v for k, v in every.items() if v != "New drug"}  # the strategy's own values go
    assert [(r.target, r.strategy) for r in _psa.spec_export("markov", paths, no_drug)] == [
        ("Healthy -> Sick", None), ("Sick", None)]
    assert [(c.target, c.other) for c in _psa.spec_export_correlations("markov", paths, no_drug)] == [
        ("Healthy -> Sick", "Sick")]
    no_healthy = {k: v for k, v in every.items() if v != "Healthy"}
    assert [r.target for r in _psa.spec_export("markov", paths, no_healthy)] == ["Sick"]
    assert _psa.spec_export_correlations("markov", paths, no_healthy) == []
