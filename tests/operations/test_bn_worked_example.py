"""Lock the BN inference numbers shown in the worked example transcript.

The worked example (`worked_example/worked_example.py`) only checks that
commands exit 0 — it does *not* assert the posteriors are correct, so an
engine regression would silently rewrite `worked_example_output.md` rather
than fail. This test reconstructs the same five-node air-quality BN and
asserts the exact marginals/posteriors the transcript displays, so any
change to the computed numbers fails here with a clear diff.

If the worked-example CPTs change, update both the script and these
expected values together.
"""

from __future__ import annotations

import pytest

from latris.operations.bn_inference import bn_infer
from latris.schema.bn import CPTEntry, CPTRow

pytest.importorskip("pgmpy")


def _air_quality_bn():
    """The worked example's clean five-node causal core (node IDs stand in for
    the labels Transport Policy, Green Infrastructure, etc.). Parent order and
    probability layout mirror the `bn set-cpt` calls in the worked example."""
    ss = {
        "transport_policy": ["lax", "strict"],
        "green_infra": ["low", "high"],
        "vehicle_emissions": ["low", "high"],
        "air_quality": ["good", "moderate", "poor"],
        "respiratory_health": ["good", "poor"],
    }
    cpts = {
        "transport_policy": CPTEntry(
            target_id="transport_policy", parents=[], states=ss["transport_policy"],
            rows=[CPTRow(p=[0.6, 0.4])],
        ),
        "green_infra": CPTEntry(
            target_id="green_infra", parents=[], states=ss["green_infra"],
            rows=[CPTRow(p=[0.5, 0.5])],
        ),
        "vehicle_emissions": CPTEntry(
            target_id="vehicle_emissions", parents=["transport_policy"],
            states=ss["vehicle_emissions"], rows=[
                CPTRow(parent_states={"transport_policy": "lax"}, p=[0.3, 0.7]),
                CPTRow(parent_states={"transport_policy": "strict"}, p=[0.8, 0.2]),
            ],
        ),
        "air_quality": CPTEntry(
            target_id="air_quality", parents=["vehicle_emissions", "green_infra"],
            states=ss["air_quality"], rows=[
                CPTRow(parent_states={"vehicle_emissions": "low", "green_infra": "low"}, p=[0.5, 0.35, 0.15]),
                CPTRow(parent_states={"vehicle_emissions": "low", "green_infra": "high"}, p=[0.7, 0.25, 0.05]),
                CPTRow(parent_states={"vehicle_emissions": "high", "green_infra": "low"}, p=[0.1, 0.3, 0.6]),
                CPTRow(parent_states={"vehicle_emissions": "high", "green_infra": "high"}, p=[0.25, 0.4, 0.35]),
            ],
        ),
        "respiratory_health": CPTEntry(
            target_id="respiratory_health", parents=["air_quality", "green_infra"],
            states=ss["respiratory_health"], rows=[
                CPTRow(parent_states={"air_quality": "good", "green_infra": "low"}, p=[0.9, 0.1]),
                CPTRow(parent_states={"air_quality": "good", "green_infra": "high"}, p=[0.93, 0.07]),
                CPTRow(parent_states={"air_quality": "moderate", "green_infra": "low"}, p=[0.75, 0.25]),
                CPTRow(parent_states={"air_quality": "moderate", "green_infra": "high"}, p=[0.8, 0.2]),
                CPTRow(parent_states={"air_quality": "poor", "green_infra": "low"}, p=[0.45, 0.55]),
                CPTRow(parent_states={"air_quality": "poor", "green_infra": "high"}, p=[0.55, 0.45]),
            ],
        ),
    }
    return ss, cpts


def test_prior_marginals_match_transcript():
    ss, cpts = _air_quality_bn()
    m = bn_infer(ss, cpts).marginals
    # Transcript: Vehicle Emissions low 0.500
    assert m["vehicle_emissions"]["low"] == pytest.approx(0.5, abs=1e-9)
    # Transcript: Air Quality Index good 0.388 moderate 0.325 poor 0.288
    assert m["air_quality"]["good"] == pytest.approx(0.3875, abs=1e-6)
    assert m["air_quality"]["moderate"] == pytest.approx(0.325, abs=1e-6)
    assert m["air_quality"]["poor"] == pytest.approx(0.2875, abs=1e-6)
    # Transcript: Respiratory Health good 0.747
    assert m["respiratory_health"]["good"] == pytest.approx(0.747125, abs=1e-6)


def test_predictive_query_strict_policy():
    """Transcript: given Transport Policy=strict."""
    ss, cpts = _air_quality_bn()
    m = bn_infer(
        ss, cpts,
        query=["air_quality", "respiratory_health"],
        evidence={"transport_policy": "strict"},
    ).marginals
    # AQI good 0.515 moderate 0.310 poor 0.175
    assert m["air_quality"]["good"] == pytest.approx(0.515, abs=1e-6)
    assert m["air_quality"]["moderate"] == pytest.approx(0.310, abs=1e-6)
    assert m["air_quality"]["poor"] == pytest.approx(0.175, abs=1e-6)
    # Respiratory Health good 0.796
    assert m["respiratory_health"]["good"] == pytest.approx(0.7964, abs=1e-3)


def test_diagnostic_query_poor_health():
    """Transcript: given Respiratory Health=poor — beliefs flow backwards."""
    ss, cpts = _air_quality_bn()
    m = bn_infer(
        ss, cpts,
        query=["transport_policy", "vehicle_emissions"],
        evidence={"respiratory_health": "poor"},
    ).marginals
    # Transport Policy lax 0.678 strict 0.322 (both above/below their priors)
    assert m["transport_policy"]["lax"] == pytest.approx(0.678, abs=1e-3)
    assert m["transport_policy"]["strict"] == pytest.approx(0.322, abs=1e-3)
    # Vehicle Emissions low 0.338 high 0.662
    assert m["vehicle_emissions"]["high"] == pytest.approx(0.662, abs=1e-3)
    assert m["vehicle_emissions"]["low"] == pytest.approx(0.338, abs=1e-3)
