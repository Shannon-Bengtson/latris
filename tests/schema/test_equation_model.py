"""Equation model schema: values with a valid range, formulas, scenarios."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from latris.repo.yaml_io import dump_model, load_model
from latris.schema.equation_model import (
    EquationFormulaEntry,
    EquationFormulaSet,
    EquationOverride,
    EquationScenario,
    EquationScenarioSet,
    EquationValueEntry,
    EquationValueSet,
)


def test_value_rules():
    v = EquationValueEntry(target_id="n", value=0.03, units="s/m**(1/3)", valid_min=0.01, valid_max=0.2)
    assert not v.outside(0.03) and v.outside(0.5) and v.outside(0.001)
    assert not EquationValueEntry(target_id="n", value=1, units="m").outside(1e9)  # no range stated
    assert EquationValueEntry(target_id="n", value=1, units="m", valid_min=0).outside(-1)
    with pytest.raises(ValidationError, match="units"):
        EquationValueEntry(target_id="n", value=1, units=" ")
    with pytest.raises(ValidationError, match="minimum below its maximum"):
        EquationValueEntry(target_id="n", value=1, units="m", valid_min=2, valid_max=1)


def test_formula_rules():
    f = EquationFormulaEntry(target_id="q", expression="  area * velocity ", units="m**3/s")
    assert f.expression == "area * velocity"
    with pytest.raises(ValidationError, match="formula"):
        EquationFormulaEntry(target_id="q", expression="", units="m")
    with pytest.raises(ValidationError, match="units"):
        EquationFormulaEntry(target_id="q", expression="a", units="")


def test_scenario_rules():
    o = EquationOverride(target_id="s", value=0.002, units="dimensionless")
    assert EquationScenario(name="Steep reach", overrides=[o]).extends is None
    with pytest.raises(ValidationError, match="another name"):
        EquationScenario(name="Reference", overrides=[o])
    with pytest.raises(ValidationError):
        EquationScenario(name="Empty", overrides=[])


def test_round_trip(tmp_path: Path):
    values = EquationValueSet(entries=[EquationValueEntry(
        target_id="n", value=0.03, units="s/m**(1/3)", valid_min=0.01, valid_max=0.2, source_id="chow-1959",
        notes="natural channel", verification="human-verified")])
    formulas = EquationFormulaSet(entries=[EquationFormulaEntry(
        target_id="v", expression="hydraulic_radius ** (2/3) * SQRT(slope) / roughness", units="m/s",
        source_id="manning-1891", notes="uniform flow")])
    scenarios = EquationScenarioSet(scenarios=[EquationScenario(
        name="Flood", description="bankfull", reason="design case",
        overrides=[EquationOverride(target_id="d", value=2.5, units="m")])])
    for model, cls, name in ((values, EquationValueSet, "v.yaml"), (formulas, EquationFormulaSet, "f.yaml"),
                             (scenarios, EquationScenarioSet, "s.yaml")):
        dump_model(model, tmp_path / name)
        assert load_model(cls, tmp_path / name) == model
