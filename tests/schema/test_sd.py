"""Pydantic-level validation for the System Dynamics schema.

Only intrinsic shape is checked here. Unit parseability, name resolution and
dimensional consistency belong to operations/readiness (see test_sd_eval.py and
test_sd_readiness.py).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from latris.repo.yaml_io import dump_model, load_model
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


def _table(points, **kw) -> SDTableEntry:
    return SDTableEntry(
        target_id="aux_1", points=[TablePoint(x=x, y=y) for x, y in points],
        x_units="dimensionless", y_units="dimensionless", **kw,
    )


class TestEquation:
    def test_valid(self):
        e = SDEquationEntry(target_id="flow_1", expression=" water * k ", units=" liter/year ")
        assert e.attribute == "equations"
        assert e.expression == "water * k"
        assert e.units == "liter/year"

    def test_blank_expression_rejected(self):
        with pytest.raises(ValidationError, match="expression"):
            SDEquationEntry(target_id="flow_1", expression="  ", units="liter/year")

    def test_blank_units_rejected(self):
        with pytest.raises(ValidationError, match="dimensionless"):
            SDEquationEntry(target_id="flow_1", expression="k", units="")


class TestStockAndConstant:
    def test_stock(self):
        s = SDStockEntry(target_id="stock_1", initial_value=100, units="liter", non_negative=True)
        assert s.initial_value == 100.0 and s.non_negative

    def test_stock_blank_units_rejected(self):
        with pytest.raises(ValidationError):
            SDStockEntry(target_id="stock_1", initial_value=1, units=" ")

    def test_constant(self):
        c = SDConstantEntry(target_id="c_1", value=0.1, units="1/year")
        assert c.attribute == "constant"


class TestTable:
    def test_valid(self):
        t = _table([(0, 1), (0.5, 0.8), (1, 0)], extrapolate="linear")
        assert len(t.points) == 3 and t.extrapolate == "linear"

    def test_needs_two_points(self):
        with pytest.raises(ValidationError, match="at least two"):
            _table([(0, 1)])

    def test_x_must_increase(self):
        with pytest.raises(ValidationError, match="strictly increasing"):
            _table([(0, 1), (1, 2), (0.5, 3)])

    def test_duplicate_x_rejected(self):
        with pytest.raises(ValidationError, match="strictly increasing"):
            _table([(0, 1), (0, 2)])

    def test_bad_extrapolation_rejected(self):
        with pytest.raises(ValidationError):
            _table([(0, 1), (1, 2)], extrapolate="wrap")


def test_round_trip(tmp_path: Path):
    sets = [
        SDEquationSet(entries=[SDEquationEntry(target_id="f", expression="a*b", units="liter/year",
                                               origin="human-elicited", source_id="src_1")]),
        SDStockSet(entries=[SDStockEntry(target_id="s", initial_value=3.5, units="person")]),
        SDConstantSet(entries=[SDConstantEntry(target_id="c", value=2, units="dimensionless")]),
        SDTableSet(entries=[_table([(0, 0), (1, 2)])]),
    ]
    for i, model in enumerate(sets):
        path = tmp_path / f"m{i}.yaml"
        dump_model(model, path)
        assert load_model(type(model), path) == model
