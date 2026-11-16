"""Process-tracing schema — prior confidence in each theory-of-change link, and the evidence tests on it.

Process tracing tests the causal claims of a theory of change one link at a
time. For a link (``target_id`` is the edge), a test is a piece of evidence
you would expect to see — or not — if the link holds, characterised by two
probabilities: how likely you'd be to find it if the link holds (its
*certainty*, P(E | H)) and if it doesn't (1 minus its *uniqueness*,
P(E | not H)). Stored with provenance:

- ``views/parameters/theory_of_change-pt_prior.yaml`` — :class:`PTPriorSet`
- ``views/parameters/theory_of_change-pt_test.yaml``  — :class:`PTTestSet`
"""

from __future__ import annotations

from pydantic import Field

from latris.schema.attributes import _Base, _EntryBase


class PTPriorEntry(_EntryBase):
    """How confident you are that a link holds before the tests (``target_id`` is the edge)."""

    attribute: str = "pt_prior"
    prior: float = Field(gt=0.0, lt=1.0)
    notes: str | None = None


class PTPriorSet(_Base):
    entries: list[PTPriorEntry] = Field(default_factory=list)


class PTTestEntry(_EntryBase):
    """One evidence test on a link: what you'd expect to find, how telling it is, and whether it was found.

    Probabilities are open-interval: no evidence is certain, and a value of 0 or 1 would let one test settle
    the question outright.
    """

    attribute: str = "pt_test"
    name: str  # unique per link
    p_if_true: float = Field(gt=0.0, lt=1.0)  # P(E | the link holds): certainty
    p_if_false: float = Field(gt=0.0, lt=1.0)  # P(E | it doesn't): 1 - uniqueness
    found: bool | None = None  # None: not looked for yet
    description: str | None = None
    notes: str | None = None


class PTTestSet(_Base):
    entries: list[PTTestEntry] = Field(default_factory=list)
