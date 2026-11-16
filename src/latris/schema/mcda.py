"""MCDA schema — criterion weights and scales, and each option's score on each criterion.

Multi-criteria decision analysis lives on the ordinary substrate: options and
criteria are entities with a view role (``views/roles/mcda-roles.yaml``:
``option`` or ``criterion``). The numbers are stored per value, each with its
own provenance (``_EntryBase``):

- ``views/parameters/mcda-criterion.yaml`` — :class:`MCDACriterionSet`: a
  criterion's swing weight, direction and scale;
- ``views/parameters/mcda-score.yaml``     — :class:`MCDAScoreSet`: an option's
  performance on a criterion, in the criterion's units.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from latris.schema.attributes import _Base, _EntryBase

MCDAElement = Literal["option", "criterion"]
MCDA_ELEMENTS: tuple[str, ...] = ("option", "criterion")
Direction = Literal["higher", "lower"]


class MCDACriterionEntry(_EntryBase):
    """How a criterion counts: its swing weight, which way is better, and the scale scores are read on.

    A swing weight says how much moving from ``worst`` to ``best`` on this criterion matters compared with
    the others' swings — so a weight means nothing without its scale. Without ``worst``/``best`` the scale
    is the range of the options' scores (a *local* scale), which changes when an option is added.
    """

    attribute: str = "criterion"
    weight: float | None = Field(default=None, gt=0)
    direction: Direction | None = None
    worst: float | None = None
    best: float | None = None
    units: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _scale(self) -> MCDACriterionEntry:
        if (self.worst is None) != (self.best is None):
            raise ValueError("give both worst and best, or neither (then the options' range is used)")
        if self.worst is not None and self.worst == self.best:
            raise ValueError("worst and best must differ")
        if (self.worst is not None and self.direction is not None
                and (self.direction == "higher") != (self.best > self.worst)):  # type: ignore[operator]
            raise ValueError(f"for '{self.direction} is better', best must be "
                             f"{'above' if self.direction == 'higher' else 'below'} worst")
        return self


class MCDACriterionSet(_Base):
    entries: list[MCDACriterionEntry] = Field(default_factory=list)


class MCDAScoreEntry(_EntryBase):
    """An option's performance on one criterion (``target_id`` is the option)."""

    attribute: str = "score"
    criterion: str  # criterion entity id
    value: float
    notes: str | None = None


class MCDAScoreSet(_Base):
    entries: list[MCDAScoreEntry] = Field(default_factory=list)
