"""System Dynamics schema — equations, initial values, constants, table functions.

An SD model lives on the ordinary substrate. Stocks, flows, auxiliaries,
constants and source/sink clouds are all substrate ``variable`` entities; their
SD meaning is a *view role* (``views/roles/sd-roles.yaml``, see ``schema/roles.py``),
not a substrate kind. Material movement uses ``flow`` edges
(``stock → flow → stock``); "X appears in Y's equation" uses ``causal`` edges.

Stored (one file each, via the generic view-attribute path convention):

- ``views/parameters/sd-equations.yaml``     — :class:`SDEquationSet` (flows + auxiliaries)
- ``views/parameters/sd-initial_value.yaml`` — :class:`SDStockSet`
- ``views/parameters/sd-constant.yaml``      — :class:`SDConstantSet`
- ``views/parameters/sd-table.yaml``         — :class:`SDTableSet`

Every entry carries its own provenance (``_EntryBase``), so one equation or one
initial value is independently attributable — and a one-number edit is a
one-line, sourced git diff.

Only intrinsic shape is enforced here. Whether a unit string actually parses,
whether an equation references real variables, and whether the model is
dimensionally consistent are operations/readiness concerns
(``operations/_units.py``, ``operations/_sd_eval.py``, ``operations/readiness.py``).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from latris.schema.attributes import _Base, _EntryBase


def _non_blank(value: str, what: str) -> str:
    if not value or not value.strip():
        raise ValueError(f"{what} must not be empty")
    return value.strip()


class SDEquationEntry(_EntryBase):
    """The equation for a flow or auxiliary.

    ``expression`` references other SD variables by their slugified labels
    (``Birth Rate`` → ``birth_rate``). ``units`` declares the result's units;
    the evaluator checks the expression actually produces them.
    """

    attribute: str = "equations"
    expression: str
    units: str

    @field_validator("expression")
    @classmethod
    def _expression_present(cls, v: str) -> str:
        return _non_blank(v, "an equation expression")

    @field_validator("units")
    @classmethod
    def _units_present(cls, v: str) -> str:
        return _non_blank(v, "units (use 'dimensionless' for a pure number)")


class SDEquationSet(_Base):
    entries: list[SDEquationEntry] = Field(default_factory=list)


class SDStockEntry(_EntryBase):
    """A stock's value at the simulation's initial time."""

    attribute: str = "initial_value"
    initial_value: float
    units: str
    non_negative: bool = False  # warning-only in v1: flagged if the run goes negative

    @field_validator("units")
    @classmethod
    def _units_present(cls, v: str) -> str:
        return _non_blank(v, "units")


class SDStockSet(_Base):
    entries: list[SDStockEntry] = Field(default_factory=list)


class SDConstantEntry(_EntryBase):
    """A parameter held fixed for the duration of a run."""

    attribute: str = "constant"
    value: float
    units: str

    @field_validator("units")
    @classmethod
    def _units_present(cls, v: str) -> str:
        return _non_blank(v, "units (use 'dimensionless' for a pure number)")


class SDConstantSet(_Base):
    entries: list[SDConstantEntry] = Field(default_factory=list)


class TablePoint(_Base):
    x: float
    y: float


class SDTableEntry(_EntryBase):
    """A piecewise-linear lookup ("graphical function") owned by one flow/auxiliary.

    The owner's equation calls it as ``TABLE(<input expression>)``. Outside the
    point range the output is clamped to the end values (``clamp``) or the end
    segments are extended (``linear``).
    """

    attribute: str = "table"
    points: list[TablePoint]
    x_units: str
    y_units: str
    extrapolate: Literal["clamp", "linear"] = "clamp"

    @field_validator("x_units", "y_units")
    @classmethod
    def _units_present(cls, v: str) -> str:
        return _non_blank(v, "table units (use 'dimensionless' for a pure number)")

    @model_validator(mode="after")
    def _check_points(self) -> SDTableEntry:
        if len(self.points) < 2:
            raise ValueError("a table function needs at least two points")
        xs = [p.x for p in self.points]
        if any(b <= a for a, b in zip(xs, xs[1:], strict=False)):
            raise ValueError(f"table x-values must be strictly increasing, got {xs}")
        return self


class SDTableSet(_Base):
    entries: list[SDTableEntry] = Field(default_factory=list)
