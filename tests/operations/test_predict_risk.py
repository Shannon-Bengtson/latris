"""Predict on the risk model types (fault tree, bow-tie, event tree), and the contract machinery they need:
a cell naming one of a factor's parameters, opaque units, and impossible values refused."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import bow_tie as bt
from latris.operations import contract, predict
from latris.operations import edges as edge_ops
from latris.operations import event_tree as et
from latris.operations import fault_tree as ft
from latris.operations import nodes as node_ops
from latris.operations.init import init_project
from tests.operations import test_bow_tie as BT
from tests.operations import test_event_tree as ET
from tests.operations import test_fault_tree as FT


def _value(result, name):
    return result["outputs"][name]["value"]


# ── fault tree ──────────────────────────────────────────────────────


@pytest.fixture
def cooling(tmp_path: Path, git_identity, monkeypatch):
    root = tmp_path / "cooling"
    init_project(root, statement="How likely is a loss of cooling?")
    for label in FT.EVENTS:
        node_ops.add_node(label, kind="event", root=root)
    for a, b in FT.LINKS:
        edge_ops.add_edge(a, b, kind="logical", root=root)
    FT._classify(root)
    monkeypatch.chdir(root)
    return root


def test_fault_tree_contract_and_predict(cooling):
    root = cooling
    c, _ = contract.init("fault_tree", root=root)
    assert {i.name for i in c.inputs} == {"pump_a_fails", "pump_b_fails", "supply_1_fails", "supply_2_fails",
                                          "supply_3_fails"}
    assert all(i.cell == "fault_tree:probability" and i.units == "dimensionless" for i in c.inputs)
    assert [(o.name, o.units) for o in c.outputs] == [("loss_of_cooling", "dimensionless")]
    assert contract.check(root=root) == []

    point = ft.analyse(root=root)["probability"]["exact"]
    assert _value(predict.predict(root=root), "loss_of_cooling") == pytest.approx(point)
    # Both pumps certain to fail: the top event is certain.
    sure = predict.predict({"pump_a_fails": 1, "pump_b_fails": 1}, root=root)
    assert _value(sure, "loss_of_cooling") == pytest.approx(1.0)
    # An intermediate gate is an output too.
    contract.set_output("fault_tree", "Both pumps fail", root=root)
    r = predict.predict({"pump_a_fails": 0.5}, root=root)
    assert _value(r, "both_pumps_fail") == pytest.approx(0.5 * 0.02)
    # A probability outside 0–1 is impossible, not an extrapolation.
    with pytest.raises(ValueError, match="impossible"):
        predict.predict({"pump_a_fails": 1.5}, root=root)


def test_fault_tree_without_probabilities_says_so(tmp_path, git_identity, monkeypatch):
    root = tmp_path / "bare"
    init_project(root, statement="?")
    for label in FT.EVENTS:
        node_ops.add_node(label, kind="event", root=root)
    for a, b in FT.LINKS:
        edge_ops.add_edge(a, b, kind="logical", root=root)
    FT._classify(root, probs=False)
    d = contract.candidates("fault_tree", root=root)
    assert any("no probability yet" in p for p in d["problems"])


# ── bow-tie ─────────────────────────────────────────────────────────


@pytest.fixture
def gas(tmp_path: Path, git_identity, monkeypatch):
    root = tmp_path / "gas"
    init_project(root, statement="How well protected are we?")
    for label in BT.ELEMENTS:
        node_ops.add_node(label, kind="event", root=root)
    for a, b in BT.LINKS:
        edge_ops.add_edge(a, b, root=root)
    BT._classify(root)
    BT._quantify(root)
    monkeypatch.chdir(root)
    return root


def test_bow_tie_contract_predict_and_barrier_status(gas):
    root = gas
    c, _ = contract.init("bow_tie", root=root)
    names = {i.name: i for i in c.inputs}
    assert names["overpressure_frequency"].units == "1/year"
    assert names["pressure_relief_valve_pfd"].cell == "bow_tie:pfd"
    assert {o.name for o in c.outputs} == {"loss_of_containment", "fire", "toxic_exposure"}

    point = bt.analyse(root=root)["frequency"]
    r = predict.predict(root=root)
    assert _value(r, "loss_of_containment") == pytest.approx(point["top"])
    assert _value(r, "fire") == pytest.approx(point["consequences"]["Fire"])
    # A value with its own units is read in them.
    r = predict.predict({"overpressure_frequency": "1 1/month"}, root=root)
    assert _value(r, "loss_of_containment") == pytest.approx(point["top"] + 11.5 * 0.01)

    # A barrier holds two parameters (its PFD and its status): name one with its cell.
    with pytest.raises(ValueError, match="say which with its cell"):
        contract.set_input("bow_tie", "Pressure relief valve", root=root)
    entry, _ = contract.set_input("bow_tie", "Pressure relief valve", cell="bow_tie:status", name="relief_valve",
                                  root=root)
    assert (entry.kind, entry.cell) == ("state", "bow_tie:status")
    out = predict.predict({"relief_valve": "not_in_place"}, root=root)
    assert _value(out, "loss_of_containment") == pytest.approx(point["top"] + 0.5 * 0.99)
    with pytest.raises(ValueError, match="not a barrier status"):
        predict.predict({"relief_valve": "gone"}, root=root)
    assert contract.check(root=root) == []


# ── event tree ──────────────────────────────────────────────────────


@pytest.fixture
def release(tmp_path: Path, git_identity, monkeypatch):
    root = tmp_path / "release"
    init_project(root, statement="How often does a gas release end in a fire?")
    for label in ET.ELEMENTS:
        node_ops.add_node(label, kind="event", root=root)
    ET._build(root)
    ET._quantify(root)
    monkeypatch.chdir(root)
    return root


def test_event_tree_conditional_probabilities_are_inputs_of_their_own(release):
    root = release
    c, _ = contract.init("event_tree", root=root)
    ignition = [i for i in c.inputs if i.name.startswith("p_ignition")]
    assert len(ignition) == 2 and len({i.cell for i in ignition}) == 2  # one per branch it is asked on
    d = contract.describe(root=root)
    labels = {i["label"] for i in d["inputs"]}
    assert {"P(Ignition=yes)", "P(Ignition=yes | Gas detected=no)", "Gas release (frequency)"} <= labels
    # The suggested output is the rarest end state.
    assert [o.name for o in c.outputs] == ["fire"]

    point = {e["end_state"]: e["frequency"] for e in et.analyse(root=root)["end_states"]}
    assert _value(predict.predict(root=root), "fire") == pytest.approx(point["Fire"])
    assert {i.name for i in ignition} == {"p_ignition_yes", "p_ignition_yes_gas_detected_no"}
    r = predict.predict({"p_ignition_yes_gas_detected_no": 1.0, "gas_release_frequency": 0.04}, root=root)
    assert _value(r, "fire") == pytest.approx(0.04 * (0.9 * 0.05 * 0.1 + 0.1 * 1.0))
    # Adding every end state partitions the initiating frequency.
    for end in ("Contained release", "Gas cloud dispersed"):
        contract.set_output("event_tree", end, root=root)
    r = predict.predict(root=root)
    assert sum(o["value"] for o in r["outputs"].values()) == pytest.approx(0.02)


# ── the contract machinery ──────────────────────────────────────────


def test_a_cell_is_part_of_an_entrys_identity_and_hash():
    from latris.schema.contract import Contract, ContractInput, ContractOutput

    a = ContractInput(name="a", target_id="x", cell="m:p:s1", units="dimensionless")
    b = ContractInput(name="b", target_id="x", cell="m:p:s2", units="dimensionless")
    Contract(model_type="markov", inputs=[a, b], outputs=[])  # two parameters of one factor: fine
    with pytest.raises(ValueError, match="one input only"):
        Contract(model_type="markov", inputs=[a, b.model_copy(update={"cell": "m:p:s1"})], outputs=[])
    out = ContractOutput(name="o", target_id="y", units="m")
    plain = Contract(model_type="equation_model", inputs=[a.model_copy(update={"cell": None})], outputs=[out])
    # Without a cell, the hash is what it always was.
    import hashlib
    import json

    old = {"inputs": [["a", "x", "value", "dimensionless", "observe", False]],
           "outputs": [["o", "y", "value", "m", None]]}
    assert contract.contract_hash(plain) == hashlib.sha256(json.dumps(old, sort_keys=True).encode()).hexdigest()[:12]
    with_cell = plain.model_copy(update={"inputs": [a]})
    assert contract.contract_hash(with_cell) != contract.contract_hash(plain)


def test_a_choice_output_has_no_units():
    from latris.schema.contract import ContractOutput

    ContractOutput(name="best", target_id="d", kind="choice")
    with pytest.raises(ValueError, match="choice"):
        ContractOutput(name="best", target_id="d", kind="choice", units="GBP")


def test_units_pint_does_not_know_are_opaque():
    assert contract.units_compatible("GBP", "GBP")
    assert not contract.units_compatible("GBP", "USD")
    assert not contract.units_compatible("GBP", "m")
    assert contract.units_compatible("m", "cm")
    assert contract.convert(5.0, "QALY", "QALY") == 5.0
    assert contract.convert(250.0, "cm", "m") == pytest.approx(2.5)
    with pytest.raises(ValueError, match="can't be given"):
        contract.convert(5.0, "GBP", "USD")


def test_routes_take_a_cell(gas):
    from fastapi.testclient import TestClient

    from latris.server.app import create_app

    c = TestClient(create_app(project_root=gas))
    assert c.post("/api/contract/init", json={"model_type": "bow_tie"}).status_code == 200
    cands = c.get("/api/contract/candidates", params={"model_type": "bow_tie"}).json()
    assert {"bow_tie:pfd", "bow_tie:status", "bow_tie:frequency"} <= {x["cell"] for x in cands["inputs"]}
    assert c.post("/api/contract/input", json={"model_type": "bow_tie", "node": "Gas detection"}).status_code == 422
    r = c.post("/api/contract/input", json={"model_type": "bow_tie", "node": "Gas detection", "cell": "bow_tie:status",
                                            "name": "detection"})
    assert r.status_code == 200 and r.json()["result"]["cell"] == "bow_tie:status"
    shown = c.get("/api/contract").json()
    assert next(i for i in shown["inputs"] if i["name"] == "detection")["cell"] == "bow_tie:status"
    out = c.post("/api/predict", json={"inputs": {"detection": "not_in_place"}}).json()
    assert out["outputs"]["toxic_exposure"]["value"] == pytest.approx(out["outputs"]["loss_of_containment"]["value"])
