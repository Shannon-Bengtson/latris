"""Equation parsing/evaluation (simpleeval) and unit handling (pint) for SD."""

from __future__ import annotations

import pytest

from latris.operations._sd_eval import EquationError, Evaluator, interpolate, parse, slugify
from latris.operations._units import UnitError, describe, parse_unit, quantity
from latris.schema.sd import SDTableEntry, TablePoint


def _names(**kw):
    out = {"TIME": quantity(3, "year")}
    for k, (v, u) in kw.items():
        out[k] = quantity(v, u)
    return out


def _eval(expr, names=None, table=None):
    return Evaluator().evaluate(parse(expr), names or _names(), table=table)


TABLE = SDTableEntry(
    target_id="x", points=[TablePoint(x=0, y=1), TablePoint(x=1, y=3)],
    x_units="dimensionless", y_units="1/year",
)


class TestUnits:
    def test_parse_and_describe(self):
        assert describe(parse_unit("person/year")) == "person / year"
        assert describe(parse_unit("dimensionless")) == "dimensionless"

    def test_custom_units_and_plurals(self):
        assert parse_unit("people") == parse_unit("person")
        assert parse_unit("dollars") == parse_unit("dollar")
        assert quantity(1, "items").to("item").magnitude == 1

    @pytest.mark.parametrize("bad", ["", "  ", "bananas", "liter/(year"])
    def test_bad_units(self, bad):
        with pytest.raises(UnitError):
            parse_unit(bad)


class TestSlugify:
    @pytest.mark.parametrize(
        ("label", "slug"),
        [("Birth Rate", "birth_rate"), ("  Water ", "water"), ("2nd Stock!", "_2nd_stock"), ("%%", "var")],
    )
    def test_slugs(self, label, slug):
        assert slugify(label) == slug


class TestParse:
    def test_names_exclude_functions_and_time(self):
        p = parse("MIN(water * k, cap) + STEP(boost, 5) * TIME / TIME")
        assert p.names == {"water", "k", "cap", "boost"}
        assert not p.uses_table
        assert parse("TABLE(water / cap)").uses_table

    @pytest.mark.parametrize(
        ("expr", "match"),
        [
            ("water +", "cannot parse"),
            ("min(a, b)", "did you mean MIN"),
            ("foo(a)", "unknown function"),
            ("a.__class__", "Attribute is not allowed"),
            ("'text'", "numeric literals"),
            ("[a, b]", "List is not allowed"),
            ("a if b else c", "IfExp is not allowed"),
            ("", "empty"),
        ],
    )
    def test_rejected(self, expr, match):
        with pytest.raises(EquationError, match=match):
            parse(expr)


class TestEvaluate:
    def test_units_propagate(self):
        out = _eval("water * k", _names(water=(100, "liter"), k=(0.1, "1/year")))
        assert out.units == parse_unit("liter/year")
        assert out.magnitude == pytest.approx(10)

    def test_incompatible_addition_is_a_unit_error(self):
        with pytest.raises(EquationError, match="cannot combine liter with 1 / year") as exc:
            _eval("water + k", _names(water=(100, "liter"), k=(0.1, "1/year")))
        assert "[" not in str(exc.value)  # no pint dimension brackets for rich to swallow

    def test_compatible_units_convert(self):
        out = _eval("a + b", _names(a=(1, "liter"), b=(500, "milliliter")))
        assert out.to("liter").magnitude == pytest.approx(1.5)

    def test_bare_number_comparison_explains_itself(self):
        with pytest.raises(EquationError, match="bare number"):
            _eval("water > 5", _names(water=(1, "liter")))

    def test_min_max_keep_units_with_literal_zero(self):
        names = _names(water=(100, "liter"), cap=(200, "liter"))
        assert _eval("MAX(0, water - cap)", names).units == parse_unit("liter")
        assert _eval("MIN(water, 0)", names).magnitude == 0
        assert _eval("MIN(water, cap)", names).magnitude == 100

    def test_min_rejects_nonzero_bare_number(self):
        with pytest.raises(EquationError, match="bare number"):
            _eval("MIN(water, 5)", _names(water=(1, "liter")))

    def test_if_then_else(self):
        names = _names(water=(100, "liter"), cap=(50, "liter"), k=(0.1, "1/year"))
        assert _eval("IF_THEN_ELSE(water > cap, water * k, 0)", names).magnitude == pytest.approx(10)
        assert _eval("IF_THEN_ELSE(water < cap, water * k, 0)", names).magnitude == 0

    def test_if_then_else_branches_must_agree(self):
        with pytest.raises(EquationError, match="units don't match"):
            _eval("IF_THEN_ELSE(water > cap, water, k)",
                  _names(water=(1, "liter"), cap=(0, "liter"), k=(1, "1/year")))

    def test_step_switches_on_time(self):
        names = _names(boost=(2, "liter/year"))  # TIME = 3 year
        assert _eval("STEP(boost, 2)", names).magnitude == 2
        assert _eval("STEP(boost, 5)", names).magnitude == 0

    def test_dimensionless_functions(self):
        names = _names(a=(1, "liter"), b=(2, "liter"))
        assert _eval("EXP(a / b)", names).magnitude == pytest.approx(1.6487212707)
        assert _eval("LN(b / a)", names).magnitude == pytest.approx(0.6931471806)
        with pytest.raises(EquationError, match="dimensionless"):
            _eval("EXP(a)", names)
        assert _eval("SQRT(a * b)", names).to("liter").magnitude == pytest.approx(2**0.5)

    def test_division_by_zero(self):
        with pytest.raises(EquationError, match="division by zero"):
            _eval("a / b", _names(a=(1, "liter"), b=(0, "liter")))

    def test_exponent_bound(self):
        with pytest.raises(EquationError, match="too large"):
            _eval("a ** 1000", _names(a=(1, "dimensionless")))

    def test_table_lookup(self):
        names = _names(r=(0.25, "dimensionless"))
        out = _eval("TABLE(r)", names, table=TABLE)
        assert out.units == parse_unit("1/year")
        assert out.magnitude == pytest.approx(1.5)

    def test_table_missing(self):
        with pytest.raises(EquationError, match="no table"):
            _eval("TABLE(r)", _names(r=(0.5, "dimensionless")))

    def test_table_input_units_checked(self):
        with pytest.raises(EquationError, match="units don't match"):
            _eval("TABLE(r)", _names(r=(0.5, "liter")), table=TABLE)


class TestInterpolate:
    def test_clamp_and_linear(self):
        assert interpolate(TABLE, -1) == 1
        assert interpolate(TABLE, 2) == 3
        linear = TABLE.model_copy(update={"extrapolate": "linear"})
        assert interpolate(linear, -1) == pytest.approx(-1)
        assert interpolate(linear, 2) == pytest.approx(5)
        assert interpolate(TABLE, 0.5) == pytest.approx(2)
