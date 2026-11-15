"""Fault tree schema — gates on events, and probabilities on basic events.

A fault tree lives on the ordinary substrate. Its events are substrate
entities; what each one *is* in the tree is a view role
(``views/roles/fault_tree-roles.yaml``): ``top_event``, ``intermediate_event``,
``basic_event`` or ``undeveloped_event``. A link from an input event to the
event it contributes to is an ordinary ``causal`` (or ``logical``) edge.

Every top or intermediate event has exactly one gate saying how its inputs
combine — so the gate is stored on the event, not drawn as a node of its own,
and the shared substrate stays a model of real events:

- ``views/parameters/fault_tree-gate.yaml``        — :class:`FTGateSet`
- ``views/parameters/fault_tree-probability.yaml`` — :class:`FTProbabilitySet`

Each probability carries its own provenance (``_EntryBase``): who gave it,
from what source, and whether a person has verified it.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from latris.schema.attributes import _Base, _EntryBase

FTEventType = Literal["top_event", "intermediate_event", "basic_event", "undeveloped_event"]
FT_EVENT_TYPES: tuple[str, ...] = ("top_event", "intermediate_event", "basic_event", "undeveloped_event")
GateType = Literal["and", "or", "vote"]


class FTGateEntry(_EntryBase):
    """How a top or intermediate event's inputs combine.

    ``and``: all inputs occur. ``or``: any input occurs. ``vote``: at least
    ``k`` of the inputs occur (a k-out-of-n gate).
    """

    attribute: str = "gate"
    gate: GateType
    k: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _k_only_for_vote(self) -> FTGateEntry:
        if self.gate == "vote" and self.k is None:
            raise ValueError("a vote gate needs k (at least k of its inputs must occur)")
        if self.gate != "vote" and self.k is not None:
            raise ValueError("only a vote gate takes k")
        return self


class FTGateSet(_Base):
    entries: list[FTGateEntry] = Field(default_factory=list)


class FTProbabilityEntry(_EntryBase):
    """A basic or undeveloped event's probability over the period the tree is about."""

    attribute: str = "probability"
    probability: float = Field(ge=0.0, le=1.0)
    notes: str | None = None


class FTProbabilitySet(_Base):
    entries: list[FTProbabilityEntry] = Field(default_factory=list)
