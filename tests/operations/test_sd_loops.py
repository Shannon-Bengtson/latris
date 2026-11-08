"""Loops That Matter against textbook cases.

Logistic growth with separate births (r·P) and deaths (r·P²/K): the
reinforcing loop's relative share is 1 / (1 + 2P/K), so dominance passes from
the reinforcing to the balancing loop exactly when P = K/2 — the inflection.
"""

from __future__ import annotations

import math

import pytest

from latris.operations import sd as sd_ops
from latris.operations.sd_inference import build_model
from latris.operations.sd_loops import describe, loop_dominance, loop_links
from tests.operations.test_sd_inference import M, bathtub

pytest.importorskip("scipy")


def logistic(p0=10.0, r=0.5, k=1000.0) -> M:
    m = M()
    p = m.stock("Population", p0, "person")
    rate = m.const("Rate", r, "1/year")
    cap = m.const("Capacity", k, "person")
    m.flow("Births", "rate * population", "person/year", to=p, inputs=[rate, p])
    m.flow("Deaths", "rate * population * population / capacity", "person/year", frm=p, inputs=[rate, cap])
    return m


def test_logistic_switches_at_the_inflection():
    model = build_model(*logistic().args(final_time=30, dt=0.01, integration_method="euler"))
    out = loop_dominance(model)
    loops = {lp["id"]: lp for lp in out["loops"]}
    assert set(loops) == {"R1", "B1"}
    assert loops["R1"]["members"] == ["Population", "Births"]
    assert loops["B1"]["members"] == ["Population", "Deaths"]

    periods = out["sets"][0]["dominant_periods"]
    assert [p["loops"] for p in periods] == [["R1"], ["B1"]]
    switch = periods[0]["end"]
    # Analytic inflection of P' = rP(1 − P/K) from P0: t* = ln((K − P0)/P0) / r.
    t_star = math.log((1000 - 10) / 10) / 0.5
    assert switch == pytest.approx(t_star, abs=0.05)

    # The relative score itself matches 1 / (1 + 2P/K) along the run.
    res = sd_ops.sd_inference.simulate(model)
    for t_idx in (10, 50, 100, 150):
        t = out["times"][t_idx]
        p_at = res.series["population"][round(t / 0.01)]
        expected = 1 / (1 + 2 * p_at / 1000)
        assert loops["R1"]["relative_score"][t_idx] == pytest.approx(expected, abs=0.01)


def test_bathtub_has_one_balancing_loop_at_full_strength():
    model = build_model(*bathtub().args(final_time=20, dt=0.1, integration_method="euler"))
    out = loop_dominance(model)
    (loop,) = out["loops"]
    assert loop["id"] == "B1" and loop["polarity"] == "B" and loop["average_share"] == pytest.approx(1.0)
    assert out["sets"][0]["dominant_periods"] == [
        {"start": 0.0, "end": 20.0, "loops": ["B1"], "share": 1.0}
    ]
    assert describe(out) == "B1 (Water → Outflow) dominates 0–20 years (100%)"


def test_feedback_through_a_stock_is_found_from_the_equations():
    model = build_model(*bathtub().args())
    kinds = {(lk.from_id, lk.to_id): lk.kind for lk in loop_links(model)}
    assert kinds[("water", "outflow")] == "info" and kinds[("outflow", "water")] == "flow"


def test_no_loops_and_too_many_loops():
    m = M()
    s = m.stock("Tank", 0.0, "liter")
    m.flow("Fill", "rate", "liter/year", to=s, inputs=[m.const("Rate", 1.0, "liter/year")])
    out = loop_dominance(build_model(*m.args(final_time=5)))
    assert out["loops"] == [] and describe(out) == "No feedback loops."
    with pytest.raises(ValueError, match="too many"):
        loop_dominance(build_model(*logistic().args(final_time=5)), max_loops=1)


def test_window_and_scenario_on_a_project(sd_bathtub_root):
    from latris.operations import sd_scenarios

    root = sd_bathtub_root
    sd_scenarios.set_scenario("Faster drain", ["Drain Rate=0.2"], root=root)
    out = sd_ops.run_loops(scenario="Faster drain", start=2, end=8,
                           settings={"final_time": 10, "dt": 0.1, "method": "euler"}, root=root)
    assert out["window"] == [2, 8] and out["scenario"] == "Faster drain"
    loop = out["loops"][0]
    assert loop["weak_links"] and loop["weak_links"][0]["why"] == "no source"  # fixture has no evidence
    _, run_id = sd_ops.record_loops(out, root=root)
    from latris.operations import analysis_results as ar

    assert run_id in {r.run.id for r in ar.report_results(root=root)}
