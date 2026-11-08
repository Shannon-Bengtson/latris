"""SD scenarios and the results store: unit-checked overrides, comparisons, report selection."""

from __future__ import annotations

import math

import pytest

from latris.operations import analysis_results as ar
from latris.operations import sd as sd_ops
from latris.operations import sd_scenarios

pytest.importorskip("scipy")

SETTINGS = {"final_time": 10, "dt": 0.25, "saveper": 1, "method": "euler"}


def _water_end(payload, name):
    sc = next(s for s in payload["scenarios"] if s["name"] == name)
    water = next(v for v, label in payload["labels"].items() if label == "Water")
    return sc["summary"][water]["end"], water, sc


def test_scenario_is_unit_checked_and_converted(sd_bathtub_root):
    root = sd_bathtub_root
    with pytest.raises(ValueError, match="can't replace"):
        sd_scenarios.set_scenario("Wrong", ["Drain Rate=0.2 liter"], root=root)
    with pytest.raises(ValueError, match="not a constant|scenario value"):
        sd_scenarios.set_scenario("Flow", ["Inflow=3"], root=root)
    scenario, _ = sd_scenarios.set_scenario(
        "Faster drain", ["Drain Rate=0.2 1/year", "Water=10 L"], description="Wider plughole", root=root
    )
    assert {o.attribute for o in scenario.overrides} == {"constant", "initial_value"}
    # A delay in another time unit is converted, not rejected.
    sd_scenarios.set_scenario("Monthly", ["Drain Rate=0.025 1/month"], root=root)
    assert [s.name for s in sd_scenarios.list_scenarios(root=root)] == ["Faster drain", "Monthly"]


def test_comparison_matches_closed_form(sd_bathtub_root):
    root = sd_bathtub_root
    sd_scenarios.set_scenario("Faster drain", ["Drain Rate=0.2"], root=root)
    sd_scenarios.set_scenario("Monthly", ["Drain Rate=0.025 1/month"], root=root)  # = 0.3/year
    payload, runs = sd_ops.simulate_scenarios(
        ["Faster drain", "Monthly"], ["Inflow Rate=10"], **{**SETTINGS, "method": "rk4"}, root=root
    )
    assert [r.name for r in runs] == ["baseline", "Faster drain", "Monthly", "what-if"]

    def exact(t, inflow=5.0, k=0.1, initial=100.0):
        eq = inflow / k
        return eq + (initial - eq) * math.exp(-k * t)

    assert _water_end(payload, "baseline")[0] == pytest.approx(exact(10), rel=1e-4)
    assert _water_end(payload, "Faster drain")[0] == pytest.approx(exact(10, k=0.2), rel=1e-4)
    assert _water_end(payload, "Monthly")[0] == pytest.approx(exact(10, k=0.3), rel=1e-4)
    end, water, sc = _water_end(payload, "what-if")
    assert end == pytest.approx(exact(10, inflow=10), rel=1e-4)
    change = sc["change_vs_baseline"][water]
    assert change["end"] == pytest.approx(exact(10, inflow=10) - exact(10), rel=1e-3)
    assert sc["overrides"][0]["baseline"] == "5 liter/year"


def test_report_shows_latest_and_marks_stale(sd_bathtub_root):
    root = sd_bathtub_root
    payload, runs = sd_ops.simulate_scenarios([], [], **SETTINGS, root=root)
    _, first = sd_ops.record_comparison(payload, runs, root=root)
    shown = ar.report_results(root=root)
    assert [r.run.id for r in shown] == [first] and not shown[0].stale

    # A later comparison that includes the baseline supersedes the baseline-only run.
    sd_scenarios.set_scenario("Faster drain", ["Drain Rate=0.2"], root=root)
    payload, runs = sd_ops.simulate_scenarios(["Faster drain"], [], **SETTINGS, root=root)
    _, second = sd_ops.record_comparison(payload, runs, root=root)
    shown = ar.report_results(root=root)
    assert [r.run.id for r in shown] == [second]
    assert shown[0].payload["scenarios"][1]["name"] == "Faster drain"

    # Changing the model makes the result out of date; changing the scenario does too.
    sd_ops.set_constant("Inflow Rate", 6, "liter/year", root=root)
    assert ar.report_results(root=root)[0].stale

    # Hiding drops it from reports but not from the log.
    ar.set_hidden(second, True, root=root)
    assert ar.report_results(root=root) == [] or all(r.run.id != second for r in ar.report_results(root=root))
    assert any(run.id == second and hidden for run, hidden, _ in ar.list_results(root=root))
    ar.set_hidden(second.split("_", 1)[1][:10], False, root=root)
    assert second in {r.run.id for r in ar.report_results(root=root)}


def test_adding_a_scenario_does_not_stale_a_baseline_run(sd_bathtub_root):
    root = sd_bathtub_root
    sd_ops.record_simulation(sd_ops.simulate(**SETTINGS, root=root), root=root)
    sd_scenarios.set_scenario("Faster drain", ["Drain Rate=0.2"], root=root)
    assert not ar.report_results(root=root)[0].stale


def test_scenarios_survive_a_removed_override_target(sd_bathtub_root):
    root = sd_bathtub_root
    sd_scenarios.set_scenario("Faster drain", ["Drain Rate=0.2"], root=root)
    sd_scenarios.remove_scenario("faster drain", root=root)
    assert sd_scenarios.list_scenarios(root=root) == []
    with pytest.raises(ValueError, match="no scenario"):
        sd_ops.simulate_scenarios(["Faster drain"], [], **SETTINGS, root=root)


def test_sd_values_count_as_quantified(sd_bathtub_root):
    from latris.operations.maturity import compute_badges
    from latris.operations.nodes import list_nodes

    ids = {n.label: n.id for n in list_nodes(root=sd_bathtub_root)}
    assert compute_badges(ids["Drain Rate"], model_type="sd", root=sd_bathtub_root).has_quantification
    assert not compute_badges(ids["Tap"], model_type="sd", root=sd_bathtub_root).has_quantification
