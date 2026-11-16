"""Bow-tie schema — barriers and threat frequencies.

A bow-tie lives on the ordinary substrate. What each element *is* is a view
role (``views/roles/bow_tie-roles.yaml``): ``hazard``, ``top_event``,
``threat``, ``consequence``, ``barrier`` or ``escalation_factor``. Its lines
are ordinary ``causal`` (or ``logical``) edges::

    threat → barrier → … → top event → barrier → … → consequence
    escalation factor → barrier → … → the barrier it degrades

What a barrier is, who owns it, whether it is in place and how often it fails
when called on is stored per barrier; a threat may carry how often it occurs:

- ``views/parameters/bow_tie-barrier.yaml``   — :class:`BTBarrierSet`
- ``views/parameters/bow_tie-frequency.yaml`` — :class:`BTFrequencySet`

Each entry carries its own provenance (``_EntryBase``).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from latris.schema.attributes import _Base, _EntryBase

BTElement = Literal["hazard", "top_event", "threat", "consequence", "barrier", "escalation_factor"]
BT_ELEMENTS: tuple[str, ...] = ("hazard", "top_event", "threat", "consequence", "barrier", "escalation_factor")

# The barrier types of the CCPS / Energy Institute bow-tie concept book (2018).
BarrierType = Literal["passive_hardware", "active_hardware", "active_hardware_human", "human"]
BARRIER_TYPES: tuple[str, ...] = ("passive_hardware", "active_hardware", "active_hardware_human", "human")
BarrierStatus = Literal["in_place", "degraded", "not_in_place"]


class BTBarrierEntry(_EntryBase):
    """One barrier's type, owner, condition and probability of failure on demand.

    ``pfd`` is the probability the barrier fails when called on (LOPA's PFD).
    A barrier that is ``not_in_place`` counts as always failing.
    """

    attribute: str = "barrier"
    barrier_type: BarrierType | None = None
    status: BarrierStatus = "in_place"
    owner: str | None = None
    pfd: float | None = Field(default=None, ge=0.0, le=1.0)
    notes: str | None = None


class BTBarrierSet(_Base):
    entries: list[BTBarrierEntry] = Field(default_factory=list)


class BTFrequencyEntry(_EntryBase):
    """How often a threat occurs, per year."""

    attribute: str = "frequency"
    frequency: float = Field(ge=0.0)
    notes: str | None = None


class BTFrequencySet(_Base):
    entries: list[BTFrequencyEntry] = Field(default_factory=list)
