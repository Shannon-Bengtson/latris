"""The FCM steady-state analysis plugin: its report section, claims, and rerun from a build spec."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import edges as edge_ops
from latris.operations import formalisms
from latris.operations import nodes as node_ops
from latris.operations import view_attributes as va
from latris.operations.analysis import fcm_steady_state
from latris.operations.analysis_results import get_result
from latris.operations.init import init_project


@pytest.fixture
def town(tmp_path: Path, git_identity, monkeypatch):
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


def _kind():
    mt, r = formalisms.result_kind("fcm-inference")
    assert mt == "fcm"
    return r


def _claims(p):
    out = {k: [] for k in ("answer_to_question", "confidence_assessment", "assumptions_limitations")}
    _kind().claims(p, out)
    return out


def test_render_and_claims_for_a_settled_scenario(town):
    p = fcm_steady_state(clamp={"Fuel price": 0.9}, root=town)
    assert p["converged"]
    text = "\n".join(_kind().render(p))
    assert text.startswith("Fuzzy cognitive map with Fuel price held at 0.9: most active")
    assert "| Factor | Activation (0–1) | Scenario |" in text
    assert "| Fuel price | 0.9 | held |" in text
    assert "hadn't settled" not in text
    out = _claims(p)
    assert out["answer_to_question"] == [text.splitlines()[0]]
    assert out["confidence_assessment"] == []
    assert "relative (0–1)" in out["assumptions_limitations"][0]


def test_a_map_that_does_not_settle_says_so(town):
    # A step transfer with one iteration can't be called settled.
    p = fcm_steady_state(clamp={"Fuel price": 1.0}, settings={"transfer_function": "step", "max_iterations": 1},
                         root=town)
    assert not p["converged"]
    text = "\n".join(_kind().render(p))
    assert "not settled after 1 steps" in text
    assert "It hadn't settled when the run stopped" in text
    out = _claims(p)
    assert "didn't settle to a steady state" in out["confidence_assessment"][0]


def test_definition_reruns_the_same_scenario(town):
    p = fcm_steady_state(clamp={"Fuel price": 0.2}, initial={"Driving": 0.5},
                         settings={"transfer_function": "tanh", "lambda_steepness": 2.0, "max_iterations": 50},
                         root=town)
    a = _kind().definition(p)
    assert a.kind == "fcm_infer" and a.clamp == {"Fuel price": 0.2} and a.initial == {"Driving": 0.5}
    assert (a.transfer_function, a.lambda_steepness, a.max_iterations) == ("tanh", 2.0, 50)
    run_id = _kind().run(a, town)
    run, payload = get_result(run_id, root=town)
    assert run.result_kind == "fcm-inference"
    assert payload["activations"] == p["activations"] and payload["clamp"] == {"Fuel price": 0.2}


def test_activations_outside_zero_to_one_are_refused(town):
    with pytest.raises(ValueError, match="activations run from 0 to 1"):
        fcm_steady_state(clamp={"Fuel price": 1.5}, root=town)
