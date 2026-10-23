"""Lock the numbers the worked example's System Dynamics sections print.

The worked-example runner only checks exit codes, so this rebuilds the same
PM2.5 models in memory and pins them to hand-derived values.
"""

from __future__ import annotations

import math

import pytest

from latris.schema.sd import SDTableEntry, TablePoint
from tests.operations.test_sd_inference import M

pytest.importorskip("scipy")

SETTINGS = {"final_time": 3, "dt": 0.05, "saveper": 0.5}


def pm25() -> tuple[M, str]:
    m = M()
    load = m.stock("PM2.5 Load", 20, "tonne", non_negative=True)
    er = m.const("Emission Rate", 120, "tonne/year")
    dr = m.const("Dispersal Rate", 2, "1/year")
    m.flow("Emission", "emission_rate", "tonne/year", to=load, inputs=[er])
    m.flow("Dispersal", "pm2_5_load * dispersal_rate", "tonne/year", frm=load, inputs=[dr])
    return m, load


def with_stagnation(m: M, load: str) -> M:
    m.eqs[1] = m.eqs[1].model_copy(update={"expression": "pm2_5_load * dispersal_rate * stagnation_effect"})
    ref = m.const("Reference Load", 50, "tonne")
    stag = m.aux("Stagnation Effect", "TABLE(pm2_5_load / reference_load)", "dimensionless", inputs=[load, ref])
    m.edge(stag, "dispersal", "causal")
    m.tables.append(SDTableEntry(
        target_id=stag, points=[TablePoint(x=0, y=1), TablePoint(x=1, y=0.8), TablePoint(x=2, y=0.5)],
        x_units="dimensionless", y_units="dimensionless",
    ))
    return m


def test_section_7_9_matches_closed_form():
    m, load = pm25()
    r = m.run(**SETTINGS)
    assert r.success and not r.warnings
    assert r.times == pytest.approx([0, 0.5, 1, 1.5, 2, 2.5, 3])
    # L(t) = 60 + (20 − 60)·e^(−2t): equilibrium = emission rate / dispersal rate.
    for t, value in zip(r.times, r.series[load], strict=True):
        assert value == pytest.approx(60 - 40 * math.exp(-2 * t), rel=1e-5)
    assert r.series["dispersal"][0] == pytest.approx(40)  # 20 t × 2/yr


def test_section_7_10_stagnation_tipping_point():
    m, load = pm25()
    m = with_stagnation(m, load)
    assert m.problems() == set()

    r = m.run(**SETTINGS)
    # t=0: load ratio 0.4 → effect 1 − 0.2·0.4 = 0.92, so dispersal = 20 × 2 × 0.92.
    assert r.series["stagnation_effect"][0] == pytest.approx(0.92)
    assert r.series["dispersal"][0] == pytest.approx(36.8)
    # On the stagnant segment (50–100 t) dispersal = 2L(1.1 − 0.006L), which peaks at
    # ≈100.8 t/yr — below the 120 t/yr emitted — so the load cannot settle at 60 t.
    peak = max(2 * x * (1.1 - 0.006 * x) for x in range(50, 101))
    assert peak == pytest.approx(100.83, abs=0.01)
    assert max(r.series["dispersal"]) < 120
    assert r.series[load] == sorted(r.series[load])  # still climbing at t=3
    assert r.series[load][-1] > 100

    # Past 100 t the curve clamps at 0.5, dispersal = L, and the load settles at 120 t.
    long_run = m.run(final_time=40, dt=0.05, saveper=10)
    assert long_run.series[load][-1] == pytest.approx(120, abs=1e-3)
