"""SMOOTH / DELAY against closed forms: exponential (first order) and Erlang-3 (third order) step responses."""

from __future__ import annotations

import math

import pytest

from latris.operations.sd_inference import analyse, build_model, simulate
from latris.operations.sd_loops import loop_dominance
from tests.operations.test_sd_inference import M

pytest.importorskip("scipy")

H, T_STEP = 10.0, 1.0


def step_model(fn: str, delay: str = "delay") -> M:
    """signal = STEP(10 person/year, 1); response = fn(signal, delay); response fills a stock."""
    m = M()
    pool = m.stock("Pool", 0.0, "person")
    height = m.const("Height", H, "person/year")
    d = m.const("Delay", 2.0, "year")
    signal = m.aux("Signal", "STEP(height, 1)", "person/year", inputs=[height])
    inputs = [signal, d] if delay == "delay" else [signal]
    response = m.aux("Response", f"{fn}(signal, {delay})", "person/year", inputs=inputs)
    m.flow("Arrivals", "response", "person/year", to=pool, inputs=[response])
    return m


def first_order(t: float, tau: float = 2.0) -> float:
    return 0.0 if t < T_STEP else H * (1 - math.exp(-(t - T_STEP) / tau))


def erlang3(t: float, tau: float = 2.0) -> float:
    if t < T_STEP:
        return 0.0
    a = 3 * (t - T_STEP) / tau
    return H * (1 - math.exp(-a) * (1 + a + a * a / 2))


@pytest.mark.parametrize(("fn", "exact"), [("SMOOTH", first_order), ("DELAY1", first_order),
                                           ("SMOOTH3", erlang3), ("DELAY3", erlang3)])
def test_step_responses_match_closed_forms(fn, exact):
    res = simulate(build_model(*step_model(fn).args(final_time=12, dt=0.01, integration_method="rk4")))
    for t, v in zip(res.times, res.series["response"], strict=True):
        if abs(t - T_STEP) > 0.05:  # the step itself is a discontinuity
            assert v == pytest.approx(exact(t), abs=2e-3), (fn, t)
    assert not any(k.startswith("sdhidden_") for k in res.series)  # hidden structure stays hidden


def test_bare_delay_time_is_in_clock_units_and_units_are_checked():
    a = simulate(build_model(*step_model("SMOOTH", delay="2").args(final_time=8, dt=0.05)))
    b = simulate(build_model(*step_model("SMOOTH").args(final_time=8, dt=0.05)))
    assert a.series["response"][-1] == pytest.approx(b.series["response"][-1], rel=1e-9)

    m = step_model("SMOOTH")
    m.consts[-1] = m.consts[-1].model_copy(update={"units": "person"})  # a delay in people
    _, problems = analyse(*m.args())
    assert any("must be a time" in p.message for p in problems)


def test_delay_in_months_on_a_years_clock_is_converted():
    m = step_model("DELAY1")
    m.consts[-1] = m.consts[-1].model_copy(update={"value": 24.0, "units": "month"})
    res = simulate(build_model(*m.args(final_time=8, dt=0.01, integration_method="rk4")))
    assert res.series["response"][-1] == pytest.approx(first_order(8.0), abs=2e-3)


def test_fast_path_matches_pint_with_delays():
    model = build_model(*step_model("DELAY3").args(final_time=6, dt=0.1))
    fast = simulate(model)
    ref = simulate(build_model(*step_model("DELAY3").args(final_time=6, dt=0.1)), fast=False)
    for k, series in ref.series.items():
        assert fast.series[k] == pytest.approx(series, rel=1e-9, abs=1e-12)


def test_smoothing_inside_a_feedback_loop_is_named_in_loop_paths():
    # Perceived crowding (a smoothed population) slows births: a balancing loop through the smooth.
    m = M()
    pop = m.stock("Population", 100.0, "person")
    cap = m.const("Capacity", 1000.0, "person")
    rate = m.const("Rate", 0.2, "1/year")
    lag = m.const("Perception Lag", 3.0, "year")
    perceived = m.aux("Perceived", "SMOOTH(population, perception_lag)", "person", inputs=[pop, lag])
    m.flow("Births", "rate * population * (1 - perceived / capacity)", "person/year", to=pop,
           inputs=[rate, pop, perceived, cap])
    out = loop_dominance(build_model(*m.args(final_time=40, dt=0.1, integration_method="euler")))
    paths = [" → ".join(lp["members"]) for lp in out["loops"]]
    assert any("Smooth of Perceived" in p for p in paths), paths
