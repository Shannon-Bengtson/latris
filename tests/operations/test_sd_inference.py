"""SD analysis + simulation against hand-derived closed forms.

Pure — models are built in memory, no project or git. Numerical tests compare
against analytic solutions, not against "it ran".
"""

from __future__ import annotations

import math

import pytest

from latris.operations._sd_eval import EquationError
from latris.operations.sd_inference import analyse, build_model, evaluate_step, simulate
from latris.schema import Edge, Entity, RoleEntry, RoleSet, Substrate
from latris.schema.sd import (
    SDConstantEntry,
    SDConstantSet,
    SDEquationEntry,
    SDEquationSet,
    SDStockEntry,
    SDStockSet,
    SDTableEntry,
    SDTableSet,
    TablePoint,
)
from latris.schema.settings import SDSettings

pytest.importorskip("scipy")


class M:
    """Tiny in-memory SD model builder. Entity ids are their slugs."""

    def __init__(self):
        self.entities: list[Entity] = []
        self.edges: list[Edge] = []
        self.roles: list[RoleEntry] = []
        self.eqs: list[SDEquationEntry] = []
        self.stocks: list[SDStockEntry] = []
        self.consts: list[SDConstantEntry] = []
        self.tables: list[SDTableEntry] = []

    def var(self, label: str, role: str | None) -> str:
        vid = label.lower().replace(" ", "_")
        self.entities.append(Entity(id=vid, kind="variable", label=label))
        if role:
            self.roles.append(RoleEntry(target_id=vid, value=role))
        return vid

    def edge(self, a: str, b: str, kind: str) -> str:
        eid = f"e{len(self.edges)}"
        self.edges.append(Edge(id=eid, from_id=a, to_id=b, kind=kind))
        return eid

    def stock(self, label, value, units, **kw):
        sid = self.var(label, "stock")
        self.stocks.append(SDStockEntry(target_id=sid, initial_value=value, units=units, **kw))
        return sid

    def const(self, label, value, units):
        cid = self.var(label, "constant")
        self.consts.append(SDConstantEntry(target_id=cid, value=value, units=units))
        return cid

    def flow(self, label, expr, units, *, frm=None, to=None, inputs=()):
        fid = self.var(label, "flow")
        self.eqs.append(SDEquationEntry(target_id=fid, expression=expr, units=units))
        if frm:
            self.edge(frm, fid, "flow")
        if to:
            self.edge(fid, to, "flow")
        for i in inputs:
            if (frm, to) != (i, None) and i not in (frm, to):
                self.edge(i, fid, "causal")
        return fid

    def aux(self, label, expr, units, inputs=()):
        aid = self.var(label, "auxiliary")
        self.eqs.append(SDEquationEntry(target_id=aid, expression=expr, units=units))
        for i in inputs:
            self.edge(i, aid, "causal")
        return aid

    def args(self, **settings):
        return (
            Substrate(entities=self.entities, edges=self.edges),
            RoleSet(entries=self.roles),
            SDEquationSet(entries=self.eqs),
            SDStockSet(entries=self.stocks),
            SDConstantSet(entries=self.consts),
            SDTableSet(entries=self.tables),
            SDSettings(**settings),
        )

    def problems(self, **settings) -> set[str]:
        return {p.gap_type for p in analyse(*self.args(**settings))[1]}

    def run(self, **settings):
        return simulate(build_model(*self.args(**settings)))


def bathtub(inflow=5.0, k=0.1, initial=100.0) -> M:
    m = M()
    w = m.stock("Water", initial, "liter")
    r = m.const("Inflow Rate", inflow, "liter/year")
    d = m.const("Drain Rate", k, "1/year")
    m.flow("Inflow", "inflow_rate", "liter/year", to=w, inputs=[r])
    m.flow("Outflow", "water * drain_rate", "liter/year", frm=w, inputs=[d])
    return m


# ── numerics ─────────────────────────────────────────────────────────


def _exact(t, inflow=5.0, k=0.1, initial=100.0):
    eq = inflow / k
    return eq + (initial - eq) * math.exp(-k * t)


@pytest.mark.parametrize("method", ["rk4", "rk2", "adaptive"])
def test_bathtub_matches_closed_form(method):
    r = bathtub().run(final_time=20, dt=0.25, saveper=5, integration_method=method)
    assert r.success
    assert r.times == pytest.approx([0, 5, 10, 15, 20])
    for t, w in zip(r.times, r.series["water"], strict=True):
        assert w == pytest.approx(_exact(t), rel=1e-5)


def test_euler_is_first_order_and_less_accurate_than_rk4():
    euler = bathtub().run(final_time=20, dt=0.25, integration_method="euler").series["water"][-1]
    rk4 = bathtub().run(final_time=20, dt=0.25, integration_method="rk4").series["water"][-1]
    exact = _exact(20)
    assert abs(euler - exact) > 10 * abs(rk4 - exact)
    # Euler's error roughly halves when dt halves (first order).
    euler_half = bathtub().run(final_time=20, dt=0.125, integration_method="euler").series["water"][-1]
    assert abs(euler_half - exact) == pytest.approx(abs(euler - exact) / 2, rel=0.05)


def test_linear_drain_is_exact_under_euler():
    m = M()
    w = m.stock("Water", 100, "liter")
    q = m.const("Leak", 2, "liter/year")
    m.flow("Out", "leak", "liter/year", frm=w, inputs=[q])
    r = m.run(final_time=10, dt=1, integration_method="euler")
    assert r.series["water"] == pytest.approx([100 - 2 * t for t in range(11)])
    assert r.series["out"] == pytest.approx([2.0] * 11)
    assert r.units == {"water": "liter", "out": "liter/year"}  # as declared, not pint's canonical form


def test_units_convert_automatically_between_flow_and_stock():
    """A flow in mL/day fills a stock in litres on a yearly clock: pint does the conversion."""
    m = M()
    w = m.stock("Tank", 0, "liter")
    q = m.const("Drip", 1000, "milliliter/day")
    m.flow("Fill", "drip", "milliliter/day", to=w, inputs=[q])
    r = m.run(final_time=1, dt=0.25, integration_method="euler")
    assert r.series["tank"][-1] == pytest.approx(365.25)  # pint's year is the Julian year


def test_step_function_uses_model_time():
    m = M()
    w = m.stock("Water", 0, "liter")
    p = m.const("Pulse", 10, "liter/year")
    m.flow("In", "STEP(pulse, 5)", "liter/year", to=w, inputs=[p])
    r = m.run(final_time=10, dt=1, integration_method="euler")
    assert r.series["water"][5] == 0
    assert r.series["water"][-1] == pytest.approx(50)


def test_table_function_drives_flow():
    m = M()
    w = m.stock("Water", 50, "liter")
    cap = m.const("Capacity", 100, "liter")
    out = m.flow("Out", "water * TABLE(water / capacity)", "liter/year", frm=w, inputs=[cap])
    m.tables.append(SDTableEntry(
        target_id=out, points=[TablePoint(x=0, y=0), TablePoint(x=1, y=0.2)],
        x_units="dimensionless", y_units="1/year",
    ))
    r = m.run(final_time=1, dt=0.5, integration_method="euler")
    assert r.series["out"][0] == pytest.approx(50 * 0.1)  # TABLE(0.5) = 0.1/year


def test_auxiliary_chain_and_evaluate_step():
    m = bathtub()
    m.aux("Fill Ratio", "water / capacity", "dimensionless", inputs=["water"])
    m.const("Capacity", 200, "liter")
    m.edge("capacity", "fill_ratio", "causal")
    model = build_model(*m.args())
    values = evaluate_step(model, 0.0, [100.0])
    assert values["fill_ratio"].magnitude == pytest.approx(0.5)
    assert values["outflow"].magnitude == pytest.approx(10)


def test_non_negative_warning():
    m = M()
    w = m.stock("Water", 5, "liter", non_negative=True)
    q = m.const("Leak", 2, "liter/year")
    m.flow("Out", "leak", "liter/year", frm=w, inputs=[q])
    r = m.run(final_time=5, dt=1, integration_method="euler")
    assert r.success
    assert len(r.warnings) == 1 and "went negative" in r.warnings[0]


def test_runaway_growth_reports_failure():
    m = M()
    s = m.stock("Pop", 1, "person")
    g = m.const("Growth", 1e3, "1/year")
    m.flow("Births", "pop * growth", "person/year", to=s, inputs=[s, g])
    r = m.run(final_time=200, dt=1, integration_method="euler")
    assert not r.success
    assert "non-finite" in r.message


def test_runtime_error_names_time_and_variable():
    m = M()
    w = m.stock("Water", 1, "liter")
    c = m.const("Cap", 1, "liter")
    q = m.const("Rate", 1, "liter/year")
    m.flow("Out", "rate * cap / (cap - water)", "liter/year", frm=w, inputs=[c, q, w])
    with pytest.raises(EquationError):
        build_model(*m.args())  # division by zero already at t=0


# ── structural analysis ──────────────────────────────────────────────


def test_complete_bathtub_has_no_problems():
    assert bathtub().problems() == set()


def test_unclassified_and_missing_values():
    m = bathtub()
    m.roles = [r for r in m.roles if r.target_id != "drain_rate"]
    m.stocks = []
    probs = m.problems()
    assert "unclassified" in probs
    assert "missing_initial_value" in probs


def test_flow_plumbing_errors():
    m = M()
    a = m.stock("A", 1, "liter")
    b = m.stock("B", 1, "liter")
    m.edge(a, b, "flow")  # stock → stock: invalid
    f = m.flow("Loose", "1", "liter/year")  # not connected to any stock
    c = m.const("C", 1, "liter")
    m.edge(c, a, "causal")  # information link into a stock
    probs = m.problems()
    assert {"flow_edge_invalid", "flow_not_connected", "stock_causal_input"} <= probs
    assert f


def test_flow_with_two_sources_is_ambiguous():
    m = M()
    a = m.stock("A", 1, "liter")
    b = m.stock("B", 1, "liter")
    c = m.stock("C", 1, "liter")
    f = m.flow("F", "1", "liter/year", to=c)
    m.edge(a, f, "flow")
    m.edge(b, f, "flow")
    assert "flow_ambiguous" in m.problems()


def test_equation_reference_problems():
    m = bathtub()
    m.eqs[1] = SDEquationEntry(target_id="outflow", expression="water * drain_rate * ghost", units="liter/year")
    assert "unknown_reference" in m.problems()

    m = bathtub()
    m.edges = [e for e in m.edges if not (e.from_id == "drain_rate" and e.to_id == "outflow")]
    assert "missing_information_link" in m.problems()

    m = bathtub()
    m.const("Unused", 1, "dimensionless")
    m.edge("unused", "outflow", "causal")
    assert "unused_information_link" in m.problems()

    m = bathtub()
    m.eqs = m.eqs[:1]
    assert "missing_equation" in m.problems()


def test_name_collision():
    m = bathtub()
    m.const("Drain-Rate", 1, "1/year")
    assert "name_collision" in m.problems()


def test_algebraic_loop_detected():
    m = bathtub()
    m.aux("A", "b * 2", "liter", inputs=[])
    m.aux("B", "a * 2", "liter", inputs=["a"])
    m.edge("b", "a", "causal")
    probs = analyse(*m.args())[1]
    loops = [p for p in probs if p.gap_type == "algebraic_loop"]
    assert loops and "A" in loops[0].message and "B" in loops[0].message


def test_loop_through_a_stock_is_fine():
    m = M()
    s = m.stock("Pop", 10, "person")
    g = m.const("Growth", 0.1, "1/year")
    m.flow("Births", "pop * growth", "person/year", to=s, inputs=[s, g])
    assert m.problems() == set()


def test_table_presence_checks():
    m = bathtub()
    m.eqs[1] = SDEquationEntry(target_id="outflow", expression="water * TABLE(water / water)", units="liter/year")
    assert "missing_table" in m.problems()

    m = bathtub()
    m.tables.append(SDTableEntry(target_id="outflow", points=[TablePoint(x=0, y=0), TablePoint(x=1, y=1)],
                                 x_units="dimensionless", y_units="dimensionless"))
    assert "unused_table" in m.problems()


def test_unit_problems():
    m = bathtub()
    m.eqs[0] = SDEquationEntry(target_id="inflow", expression="inflow_rate", units="liter")
    assert "flow_units_incompatible" in m.problems()

    m = bathtub()
    m.eqs[1] = SDEquationEntry(target_id="outflow", expression="water + drain_rate", units="liter/year")
    assert "evaluation_error" in m.problems()

    m = bathtub()
    # yields liter/year**2 — still uses every linked input, so only the units are wrong
    m.eqs[1] = SDEquationEntry(target_id="outflow", expression="water * drain_rate * drain_rate", units="liter/year")
    assert m.problems() == {"units_mismatch"}

    m = bathtub()
    m.consts[0] = SDConstantEntry(target_id="inflow_rate", value=1, units="bananas")
    assert "units_invalid" in m.problems()


def test_bare_number_equation_takes_declared_units():
    m = M()
    w = m.stock("Water", 0, "liter")
    m.flow("In", "3", "liter/year", to=w)
    r = m.run(final_time=2, dt=1, integration_method="euler")
    assert r.series["water"][-1] == pytest.approx(6)


def test_settings_problems():
    assert "settings_invalid" in bathtub().problems(final_time=0)
    assert "settings_invalid" in bathtub().problems(time_units="liter")
    assert "settings_invalid" in bathtub().problems(dt=0)


def test_build_model_summarises_problems():
    m = bathtub()
    m.stocks = []
    with pytest.raises(EquationError, match="not ready to simulate"):
        build_model(*m.args())


def test_empty_model_is_not_ready():
    assert M().problems() == {"no_stocks"}


def test_model_boundary_ignores_unrelated_causal_edges():
    """SD shares the substrate with other views: a CLD elsewhere on it is outside the SD model."""
    m = bathtub()
    m.var("Air Quality", None)
    m.var("Health", None)
    m.edge("air_quality", "health", "causal")  # unrelated CLD edge
    m.edge("water", "health", "causal")  # leaves the SD model: outside its boundary
    assert m.problems() == set()

    m.edge("health", "outflow", "causal")  # points into the model: must be classified + used
    assert m.problems() == {"unclassified"}
