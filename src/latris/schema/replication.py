"""A replication: a textbook model rebuilt in Latris, with the numbers it must reproduce.

Each replication is a folder in ``latris/replications/``: ``spec.json`` (a build spec, as ``latris build
--spec`` reads it) and ``replication.yaml`` (this model). ``latris replicate check`` builds the model,
runs its analyses and compares what Latris computes with each check's expected value.

A check says where its expected value comes from (``basis``) and whether a person has compared it with the
original (``checked``): Latris's own rule that evidence stays unverified until someone reads the source.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from latris.schema._base import SchemaModel

# Where an expected value comes from:
#   published   — a number printed in the original (``where`` names the table, figure or page)
#   closed_form — a formula the model satisfies exactly (``where`` gives it)
#   exact       — an exact calculation from the published inputs, done independently of Latris
#                 (``where`` says how; the test suite repeats it)
ReplicationBasis = Literal["published", "closed_form", "exact"]


class ReplicationSource(SchemaModel):
    """The work the model comes from."""

    citation: str
    doi: str | None = None
    url: str | None = None


class _Measure(SchemaModel):
    pass


class _OnAnalysis(_Measure):
    # Index into the spec's ``analyses``: the recorded result the value is read from.
    analysis: int = Field(ge=0)


class BnProbability(_OnAnalysis):
    """P(node = state) in a ``bn_query`` result."""

    kind: Literal["bn_probability"]
    node: str
    state: str


class SdValue(_OnAnalysis):
    """A variable's value at ``time`` in a ``simulate`` result (a parabola through the nearest saved points)."""

    kind: Literal["sd_value"]
    variable: str
    time: float
    scenario: str = "baseline"


class SdPeak(_OnAnalysis):
    """The time a variable peaks, or its value there, in a ``simulate`` result (the vertex of the parabola
    through the highest saved point and its neighbours)."""

    kind: Literal["sd_peak_time", "sd_peak_value"]
    variable: str
    scenario: str = "baseline"


class DagAdjustmentValid(_Measure):
    """Whether ``adjust_for`` satisfies the back-door criterion for exposure → outcome (true / false)."""

    kind: Literal["dag_adjustment_valid"]
    exposure: str
    outcome: str
    adjust_for: list[str]


class DagAdjustmentSets(_Measure):
    """The minimal back-door adjustment sets Latris finds for exposure → outcome (a list of label lists)."""

    kind: Literal["dag_adjustment_sets"]
    exposure: str
    outcome: str


class LoopCount(_Measure):
    """How many feedback loops the map has of one polarity (``R`` reinforcing, ``B`` balancing)."""

    kind: Literal["loop_count"]
    polarity: Literal["R", "B"]


ReplicationMeasure = Annotated[
    BnProbability | SdValue | SdPeak | DagAdjustmentValid | DagAdjustmentSets | LoopCount,
    Field(discriminator="kind"),
]


class ReplicationCheck(SchemaModel):
    """One number (or answer) the model must reproduce."""

    id: str
    claim: str  # what is being checked, in words: "P(tuberculosis) with no evidence"
    measure: ReplicationMeasure
    expected: float | bool | list[list[str]]
    # For a number: passes when |actual − expected| ≤ max(abs_tol, rel_tol × |expected|).
    abs_tol: float = 0.0
    rel_tol: float = 0.0
    basis: ReplicationBasis
    where: str  # the table, figure or page; the formula; or how the exact value was calculated
    checked: bool = False  # a person compared ``expected`` with the original


class Replication(SchemaModel):
    """A textbook model and the results it must reproduce."""

    id: str
    title: str
    model_type: str
    question: str
    summary: str  # what the model is and why it is a standard test, for the listing and the website
    source: ReplicationSource
    checks: list[ReplicationCheck] = Field(min_length=1)
    notes: list[str] = Field(default_factory=list)  # deviations from the original, and what isn't checked
