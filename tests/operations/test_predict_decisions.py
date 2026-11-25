"""Predict on the decision types: decision tree, Markov cohort model, MCDA, and the fuzzy cognitive map."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import contract, predict
from latris.operations import decision_tree as dt
from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations.init import init_project
from tests.operations import test_decision_tree as DT


def _out(result, name):
    o = result["outputs"][name]
    return o.get("value", o.get("choice"))


# ── decision tree ───────────────────────────────────────────────────


@pytest.fixture
def launch(tmp_path: Path, git_identity, monkeypatch):
    root = tmp_path / "launch"
    init_project(root, statement="Should we launch, license or do nothing?")
    for n in DT.NODES:
        node_ops.add_node(n, root=root)
    for a, b, _, _ in DT.BRANCHES:
        edge_ops.add_edge(a, b, kind="conditional", root=root)
    DT._build(root)
    monkeypatch.chdir(root)
    return root


def test_decision_tree_contract_matches_the_analysis(launch):
    root = launch
    c, _ = contract.init("decision_tree", root=root)
    names = {i.name for i in c.inputs}
    # Payoffs, and Demand once: it recurs under both options but is one uncertainty.
    assert {"launched_high_payoff", "do_nothing_payoff", "p_demand_high"} <= names
    assert "p_demand_low" not in names  # of two branches, one: the other takes the rest
    assert not any("licensed" in n and n.startswith("p_") for n in names)
    assert all(i.units == "$k" for i in c.inputs if i.cell == "decision_tree:payoff")
    outs = {o.name: o for o in c.outputs}
    assert outs["strategy_best_option"].kind == "choice"
    assert {"launch_expected_value", "license_expected_value", "do_nothing_expected_value"} <= set(outs)
    assert contract.check(root=root) == []

    p = dt.analyse(root=root)
    r = predict.predict(root=root)
    assert _out(r, "strategy_best_option") == p["best"] == "License"
    for o in p["options"]:
        assert _out(r, f"{o['option'].lower().replace(' ', '_')}_expected_value") == pytest.approx(o["ev"])
    assert r["outputs"]["strategy_best_option"]["units"] is None

    # High demand more likely: launching wins. Setting one branch of two gives the other the rest, and the
    # same uncertainty under licensing moves with it.
    r = predict.predict({"p_demand_high": 0.7}, root=root)
    assert _out(r, "launch_expected_value") == pytest.approx(0.7 * 500 + 0.3 * -200)
    assert _out(r, "license_expected_value") == pytest.approx(0.7 * 150 + 0.3 * 50)
    assert _out(r, "strategy_best_option") == "Launch"
    from latris.operations.predictors import decision_tree as dtp

    pred = dtp.build(contract.require_project(root))
    high = next(c for c in pred.inputs() if c.cell == dtp.PROBABILITY)
    edges = [e for e, _ in pred.t.children[pred.parent[high.target_id]]]
    with pytest.raises(ValueError, match="must sum to 1"):  # both branches given: they must still add up
        pred.apply({f"{e}|{dtp.PROBABILITY}": 0.7 for e in edges})
    with pytest.raises(ValueError, match="impossible"):
        predict.predict({"p_demand_high": 1.2}, root=root)
    # A payoff in the tree's own units; another currency is refused, never converted.
    r = predict.predict({"launched_low_payoff": 0}, root=root)
    assert _out(r, "launch_expected_value") == pytest.approx(200)
    with pytest.raises(ValueError, match="can't be used"):
        predict.predict({"launched_low_payoff": "0 EUR"}, root=root)


def test_decision_tree_evpi_and_a_value_along_a_branch(launch):
    root = launch
    contract.init("decision_tree", root=root)
    contract.set_output("decision_tree", "Strategy", cell="decision_tree:evpi", name="evpi", root=root)
    p = dt.analyse(root=root)
    assert _out(predict.predict(root=root), "evpi") == pytest.approx(p["evpi"]["per_uncertainty"][0]["evpi"])
    # A value along a branch: what launching costs up front.
    d = contract.candidates("decision_tree", root=root)
    launch_value = next(x for x in d["inputs"] if x["label"] == "Strategy → Launch (value)")
    contract.set_input("decision_tree", launch_value["target_id"], cell="decision_tree:value", name="launch_cost",
                       root=root)
    r = predict.predict({"launch_cost": -50}, root=root)
    assert _out(r, "launch_expected_value") == pytest.approx(80 - 50)


# ── Markov ──────────────────────────────────────────────────────────


@pytest.fixture
def cohort(tmp_path: Path, git_identity, monkeypatch):
    from tests.operations import test_markov as MK

    root = tmp_path / "cohort"
    init_project(root, statement="Is the new drug worth its cost?")
    for n in ("Healthy", "Sick", "Dead", "Standard care", "New drug"):
        node_ops.add_node(n, root=root)
    for a, b in (("Healthy", "Sick"), ("Healthy", "Dead"), ("Sick", "Dead")):
        edge_ops.add_edge(a, b, root=root)
    MK._full(root)
    monkeypatch.chdir(root)
    return root


def test_markov_contract_matches_the_analysis(cohort):
    from latris.operations import markov

    root = cohort
    c, _ = contract.init("markov", root=root)
    outs = {o.name: o for o in c.outputs}
    assert {"standard_care_cost", "new_drug_outcome", "new_drug_icer", "best_strategy"} <= set(outs)
    assert outs["new_drug_cost"].units == "£" and outs["new_drug_outcome"].units == "QALY"
    assert outs["new_drug_icer"].units == "£/QALY" and outs["best_strategy"].kind == "choice"
    assert {"healthy_cost", "healthy_cost_under_new_drug", "sick_utility"} <= {i.name for i in c.inputs}
    assert contract.check(root=root) == []

    p = markov.analyse(root=root)
    r = predict.predict(root=root)
    by = {x["strategy"]: x for x in p["results"]}
    assert _out(r, "new_drug_cost") == pytest.approx(by["New drug"]["cost"])
    assert _out(r, "standard_care_outcome") == pytest.approx(by["Standard care"]["outcome"])
    icer = next(x["icer"] for x in p["incremental"] if x["strategy"] == "New drug")
    assert _out(r, "new_drug_icer") == pytest.approx(icer)
    assert _out(r, "best_strategy") == p["choice"]
    # The reference strategy has no ICER, and says why.
    assert _out(r, "standard_care_icer") is None
    assert any("standard_care_icer: no ICER" in w for w in r["warnings"])

    # A cheaper drug: its ICER falls. Costs are in £; another currency is refused.
    cheaper = predict.predict({"healthy_cost_under_new_drug": 600}, root=root)
    assert _out(cheaper, "new_drug_icer") < icer
    with pytest.raises(ValueError, match="can't be used"):
        predict.predict({"healthy_cost_under_new_drug": "600 USD"}, root=root)


def test_markov_settings_transitions_time_and_trace(cohort):
    from latris.operations import markov

    root = cohort
    contract.init("markov", root=root)
    for cell, name in (("markov:discount_rate", "discount"), ("markov:num_cycles", "horizon")):
        contract.set_input("markov", "model", cell=cell, name=name, root=root)
    d = contract.candidates("markov", root=root)
    drug = next(x for x in d["inputs"] if x["label"] == "P(Healthy → Sick) under New drug")
    contract.set_input("markov", drug["target_id"], cell=drug["cell"], name="p_sick_on_drug", root=root)
    with pytest.raises(ValueError, match="several things"):  # base case and the drug's own: say which
        contract.set_input("markov", drug["target_id"], root=root)
    contract.set_output("markov", "New drug", cell="markov:time_in:" + markov.load(root=root).states[1],
                        name="healthy_years", root=root)
    contract.set_output("markov", "New drug", cell="markov:trace:" + markov.load(root=root).states[0],
                        name="dead_share", root=root)

    r = predict.predict({"discount": 0, "horizon": 10}, root=root)
    markov.set_settings(discount_rate=0, num_cycles=10, root=root)
    p = markov.analyse(root=root)
    by = {x["strategy"]: x for x in p["results"]}
    assert _out(r, "new_drug_cost") == pytest.approx(by["New drug"]["cost"])
    assert _out(r, "healthy_years") == pytest.approx(by["New drug"]["time_in_state"]["Healthy"])
    trace = r["outputs"]["dead_share"]["series"]
    assert len(trace["values"]) == 11 and trace["values"][0] == 0 and trace["time_units"] == "year"
    assert trace["values"][-1] == pytest.approx(by["New drug"]["final"]["Dead"])
    with pytest.raises(ValueError, match="whole number"):
        predict.predict({"horizon": 2.5}, root=root)
    # The drug as good as nothing: its outcome falls back to standard care's.
    same = predict.predict({"p_sick_on_drug": 0.10}, root=root)
    assert _out(same, "new_drug_outcome") == pytest.approx(_out(same, "standard_care_outcome"))


# ── MCDA ────────────────────────────────────────────────────────────


@pytest.fixture
def site(tmp_path: Path, git_identity, monkeypatch):
    from tests.operations import test_mcda as MC

    root = tmp_path / "site"
    init_project(root, statement="Which site should the new hospital go on?")
    for label in [*MC.SCORES, "Cost", "Travel time", "Capacity"]:
        node_ops.add_node(label, root=root)
    MC._build(root)
    monkeypatch.chdir(root)
    return root


def test_mcda_contract_matches_the_analysis(site):
    from latris.operations import mcda

    root = site
    c, _ = contract.init("mcda", root=root)
    assert {i.name for i in c.inputs} == {"cost_weight", "travel_time_weight", "capacity_weight"}
    assert {o.name for o in c.outputs} == {"site_a_overall_value", "site_b_overall_value", "site_c_overall_value",
                                           "top_option"}
    p = mcda.analyse(root=root)
    r = predict.predict(root=root)
    for row in p["ranking"]:
        assert _out(r, row["option"].lower().replace(" ", "_") + "_overall_value") == pytest.approx(row["total"])
    assert _out(r, "top_option") == p["ranking"][0]["option"] == "Site A"
    # Capacity is all that matters: the biggest site wins.
    r = predict.predict({"cost_weight": 0.001, "travel_time_weight": 0.001, "capacity_weight": 100}, root=root)
    assert _out(r, "top_option") == "Site B"
    with pytest.raises(ValueError, match="impossible"):
        predict.predict({"cost_weight": -1}, root=root)

    # A new score on a locally scaled criterion moves every option's value, and the run says so.
    d = contract.candidates("mcda", root=root)
    a_cost = next(x for x in d["inputs"] if x["label"] == "Site A on Cost")
    contract.set_input("mcda", "Site A", cell=a_cost["cell"], name="site_a_cost", root=root)
    r = predict.predict({"site_a_cost": 70}, root=root)
    assert any("no fixed scale" in w for w in r["warnings"])
    assert _out(r, "top_option") == "Site B"
    # On a fixed scale, a score beyond its end counts as the end, and the run says so too.
    mcda.set_criterion("Cost", worst=80, best=20, root=root)
    r = predict.predict({"site_a_cost": 10}, root=root)
    assert any("outside the criterion's scale" in w for w in r["warnings"])
    assert not any("no fixed scale" in w for w in r["warnings"])


# ── fuzzy cognitive map ─────────────────────────────────────────────


@pytest.fixture
def town(tmp_path: Path, git_identity, monkeypatch):
    from latris.operations import view_attributes as va

    root = tmp_path / "town"
    init_project(root, statement="What drives congestion?")
    for n in ("Fuel price", "Driving", "Congestion", "Bus use"):
        node_ops.add_node(n, root=root)
    for a, b, w in (("Fuel price", "Driving", -0.7), ("Driving", "Congestion", 0.9), ("Fuel price", "Bus use", 0.5),
                    ("Bus use", "Driving", -0.4)):
        edge, _ = edge_ops.add_edge(a, b, root=root)
        va.set_view_attribute(edge.id, "fcm", "weight", str(w), root=root)
    monkeypatch.chdir(root)
    return root


def test_fcm_contract_matches_the_steady_state_analysis(town):
    from latris.operations.analysis import fcm_steady_state

    root = town
    c, _ = contract.init("fcm", root=root)
    assert [i.name for i in c.inputs] == ["fuel_price_held_at"]  # what nothing drives is the scenario's lever
    assert [o.name for o in c.outputs] == ["congestion"]  # what drives nothing is what the map is for
    for price in (0.2, 0.9):
        p = fcm_steady_state(clamp={"Fuel price": price}, root=root)
        act = next(a["activation"] for a in p["activations"] if a["label"] == "Congestion")
        r = predict.predict({"fuel_price_held_at": price}, root=root)
        assert _out(r, "congestion") == pytest.approx(act, abs=1e-4)
    assert _out(predict.predict({"fuel_price_held_at": 0.9}, root=root), "congestion") < \
        _out(predict.predict({"fuel_price_held_at": 0.2}, root=root), "congestion")
    with pytest.raises(ValueError, match="impossible"):
        predict.predict({"fuel_price_held_at": 1.5}, root=root)
