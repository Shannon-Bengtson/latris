"""The float fast path must reproduce the pint reference path exactly.

Each model exercises one place where pint gives a bare number an implicit unit,
or converts between units; the fast path is compared to the pint path at
1e-9 relative on every reported value.
"""

from __future__ import annotations

import pytest

from latris.operations._sd_eval import EquationError
from latris.operations._units import Quantity
from latris.operations.sd_inference import build_model, fast_model, simulate, with_values
from latris.schema.sd import SDTableEntry, TablePoint
from tests.operations.test_sd_inference import M, bathtub

pytest.importorskip("scipy")


def _assert_same(m: M, **settings) -> None:
    ref = simulate(build_model(*m.args(**settings)), fast=False)
    model = build_model(*m.args(**settings))
    assert fast_model(model) is not None, "model unexpectedly fell back to the pint path"
    got = simulate(model)
    assert got.times == ref.times
    for k, series in ref.series.items():
        for a, b in zip(series, got.series[k], strict=True):
            assert b == pytest.approx(a, rel=1e-9, abs=1e-12), k


def _growth(expr: str, units: str = "person/year", extra=()) -> M:
    m = M()
    p = m.stock("Population", 100.0, "person")
    inputs = [p]
    for label, value, u in extra:
        inputs.append(m.const(label, value, u))
    m.flow("Births", expr, units, to=p, inputs=inputs)
    return m


@pytest.mark.parametrize("method", ["euler", "rk2", "rk4", "adaptive"])
def test_bathtub_every_method(method):
    _assert_same(bathtub(), final_time=50, dt=0.5, integration_method=method)


def test_mixed_units_are_converted():
    m = M()
    w = m.stock("Water", 2.0, "liter")
    r = m.const("Tap", 500.0, "milliliter/day")
    m.flow("Fill", "tap", "liter/year", to=w, inputs=[r])
    _assert_same(m, final_time=3, dt=0.25)


def test_bare_number_result_takes_declared_units():
    _assert_same(_growth("3", "person/year"), final_time=5, dt=0.5)


def test_step_ramp_pulse_with_bare_times():
    m = _growth(
        "STEP(boost, 2) + RAMP(slope, 1, 4) + PULSE(3, 1) * boost",
        extra=[("Boost", 4.0, "person/year"), ("Slope", 2.0, "person/year**2")],
    )
    _assert_same(m, final_time=6, dt=0.25)


def test_step_time_in_other_units():
    m = _growth("STEP(boost, half)", extra=[("Boost", 4.0, "person/year"), ("Half", 6.0, "month")])
    _assert_same(m, final_time=2, dt=0.125)


def test_min_max_if_then_else_align_bare_numbers():
    m = _growth(
        "MAX(0, MIN(cap, population * rate)) + IF_THEN_ELSE(population > threshold, 0, cap)",
        extra=[("Cap", 30.0, "person/year"), ("Rate", 0.2, "1/year"), ("Threshold", 150.0, "person")],
    )
    _assert_same(m, final_time=10, dt=0.25)


def test_dimensionless_percent_mixes_with_numbers():
    m = M()
    p = m.stock("Population", 100.0, "person")
    g = m.const("Growth", 5.0, "percent")
    k = m.const("Per Year", 1.0, "1/year")
    share = m.aux("Share", "growth + 1", "dimensionless", inputs=[g])
    m.flow("Births", "population * (share - 1) * per_year", "person/year", to=p, inputs=[p, share, k])
    _assert_same(m, final_time=10, dt=0.5)


def test_exp_ln_sqrt_and_power():
    m = _growth(
        "population * rate * EXP(-LN(2) * SQRT(population / scale) ** 2)",
        extra=[("Rate", 0.1, "1/year"), ("Scale", 400.0, "person")],
    )
    _assert_same(m, final_time=10, dt=0.25)


def test_table_lookup_converts_units():
    m = M()
    p = m.stock("Population", 100.0, "person")
    c = m.const("Capacity", 1.0, "kiloperson")
    r = m.aux("Crowding", "population / capacity", "dimensionless", inputs=[p, c])
    eff = m.aux("Effect", "TABLE(crowding)", "person/year", inputs=[r])
    m.tables.append(
        SDTableEntry(
            target_id=eff,
            points=[TablePoint(x=0, y=20), TablePoint(x=0.5, y=10), TablePoint(x=1, y=0)],
            x_units="dimensionless",
            y_units="person/month",
        )
    )
    m.flow("Births", "effect", "person/year", to=p, inputs=[eff])
    _assert_same(m, final_time=20, dt=0.25)


def test_runtime_error_names_the_equation():
    m = _growth("population / (zero * population)", extra=[("Zero", 0.0, "1/year")])
    with pytest.raises(EquationError):
        build_model(*m.args())  # caught at the trial evaluation, as before


def test_runtime_error_mid_run_is_reported_by_the_reference_path():
    m = _growth(
        "SQRT(drop - TIME * per_time) * unit_rate",
        extra=[("Drop", 2.0, "dimensionless"), ("Per Time", 1.0, "1/year"), ("Unit Rate", 1.0, "person/year")],
    )
    model = build_model(*m.args(final_time=5, dt=0.5, integration_method="euler"))
    assert fast_model(model) is not None
    with pytest.raises(EquationError, match="SQRT of a negative"):
        simulate(model)


def test_offset_units_fall_back_to_pint():
    m = M()
    t = m.stock("Temperature", 20.0, "degC")
    m.flow("Warming", "rate", "delta_degC/year", to=t, inputs=[m.const("Rate", 1.0, "delta_degC/year")])
    model = build_model(*m.args(final_time=2, dt=0.5, integration_method="euler"))
    assert fast_model(model) is None
    assert simulate(model).success


def test_with_values_shares_the_compiled_model():
    model = build_model(*bathtub().args(final_time=50, dt=0.5))
    fast_model(model)
    other = with_values(model, constants={"drain_rate": Quantity(0.2, "1/year")}, initial={"water": 10.0})
    assert other.fast is model.fast
    ref = with_values(build_model(*bathtub(k=0.2, initial=10.0).args(final_time=50, dt=0.5)))
    a, b = simulate(other).series["water"], simulate(ref, fast=False).series["water"]
    assert b[-1] == pytest.approx(a[-1], rel=1e-9)
