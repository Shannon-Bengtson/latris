"""Equation model schema — values, formulas and named scenarios.

A model of sourced formulas with no clock (``docs/engineering/EQUATION_MODEL.md``). Quantities are
ordinary substrate factors with a view role (``views/roles/equation_model-roles.yaml``): an ``input``
or ``parameter`` carries a value, a ``computed`` quantity or ``output`` a formula.

Stored, one entry per quantity, each with its own provenance (``EntryBase``):

- ``views/parameters/equation_model-value.yaml``     — :class:`EquationValueSet`
- ``views/parameters/equation_model-formula.yaml``   — :class:`EquationFormulaSet`
- ``views/parameters/equation_model-scenarios.yaml`` — :class:`EquationScenarioSet`

Only intrinsic shape is enforced here. Whether a unit string parses, a formula references real
quantities and the model is dimensionally consistent are operations concerns
(``operations/equation_model.py``).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from latris.schema.attributes import EntryBase, _Base
from latris.schema.common import ProvenanceOrigin, ProvenanceVerification

EquationRole = Literal["input", "parameter", "computed", "output"]
EQUATION_ROLES: tuple[str, ...] = ("input", "parameter", "computed", "output")
VALUE_ROLES: tuple[str, ...] = ("input", "parameter")  # roles that carry a value
FORMULA_ROLES: tuple[str, ...] = ("computed", "output")  # roles that carry a formula


def _non_blank(value: str, what: str) -> str:
    if not value or not value.strip():
        raise ValueError(f"{what} must not be empty")
    return value.strip()


class EquationValueEntry(EntryBase):
    """The value of an input or a parameter, in its units.

    ``valid_min``/``valid_max`` state the range the value is good for — usually the range the cited
    study covered. A run with a value outside it is reported as an extrapolation, never clamped.
    """

    attribute: str = "value"
    value: float
    units: str
    valid_min: float | None = None
    valid_max: float | None = None
    notes: str | None = None

    @field_validator("units")
    @classmethod
    def _units_present(cls, v: str) -> str:
        return _non_blank(v, "units (use 'dimensionless' for a pure number)")

    @model_validator(mode="after")
    def _range(self) -> EquationValueEntry:
        if self.valid_min is not None and self.valid_max is not None and not self.valid_min < self.valid_max:
            raise ValueError("the valid range needs its minimum below its maximum")
        return self

    def outside(self, value: float) -> bool:
        """Is ``value`` (in this entry's units) outside the stated valid range?"""
        return ((self.valid_min is not None and value < self.valid_min)
                or (self.valid_max is not None and value > self.valid_max))


class EquationValueSet(_Base):
    entries: list[EquationValueEntry] = Field(default_factory=list)


class EquationFormulaEntry(EntryBase):
    """The formula for a computed quantity or an output.

    ``expression`` references other quantities by their slugified labels (``Hydraulic radius`` →
    ``hydraulic_radius``). ``units`` declares the result's units; evaluation checks the expression
    produces them. ``notes`` is where the formula's conditions of validity go.
    """

    attribute: str = "formula"
    expression: str
    units: str
    notes: str | None = None

    @field_validator("expression")
    @classmethod
    def _expression_present(cls, v: str) -> str:
        return _non_blank(v, "a formula")

    @field_validator("units")
    @classmethod
    def _units_present(cls, v: str) -> str:
        return _non_blank(v, "units (use 'dimensionless' for a pure number)")


class EquationFormulaSet(_Base):
    entries: list[EquationFormulaEntry] = Field(default_factory=list)


class EquationOverride(_Base):
    """One value a scenario changes. ``units`` may differ from the declared units if compatible."""

    target_id: str
    value: float
    units: str

    @field_validator("units")
    @classmethod
    def _units_present(cls, v: str) -> str:
        return _non_blank(v, "units (use 'dimensionless' for a pure number)")


class EquationScenario(_Base):
    """A named set of input (or parameter) values: a design storm, a dry year, a high-dose case."""

    name: str
    description: str = ""
    overrides: list[EquationOverride] = Field(min_length=1)
    reason: str = ""
    origin: ProvenanceOrigin = "human-direct"
    verification: ProvenanceVerification = "unverified"
    source_id: str | None = None

    @field_validator("name")
    @classmethod
    def _name_present(cls, v: str) -> str:
        name = _non_blank(v, "a scenario name")
        if name.lower() == "reference":
            raise ValueError("'reference' is the model's own values; give the scenario another name")
        return name

    @property
    def extends(self) -> None:
        """Equation-model scenarios don't build on one another (the shape result staleness reads)."""
        return None


class EquationScenarioSet(_Base):
    scenarios: list[EquationScenario] = Field(default_factory=list)
