"""Markov cohort model schema — transition probabilities, per-cycle costs and utilities, the starting cohort.

A Markov model lives on the ordinary substrate: health (or other) states are
entities with the view role ``state``, the strategies being compared have the
role ``strategy``, and a transition is an ordinary edge between two states.
Stored, each value with provenance (``_EntryBase``):

- ``views/parameters/markov-transition.yaml`` — :class:`MarkovTransitionSet`:
  the per-cycle probability of moving along an edge, for every strategy or
  overriding it for one (``strategy``). Whatever doesn't leave a state stays.
- ``views/parameters/markov-reward.yaml``     — :class:`MarkovRewardSet`: a
  state's cost per cycle and utility (per year), for every strategy or one.
- ``views/parameters/markov-start.yaml``      — :class:`MarkovStartSet`: the
  share of the cohort that starts in each state.
- ``views/parameters/markov-settings.yaml``   — :class:`~latris.schema.settings.MarkovSettings`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from latris.schema.attributes import _Base, _EntryBase

MarkovElement = Literal["state", "strategy"]
MARKOV_ELEMENTS: tuple[str, ...] = ("state", "strategy")


class MarkovTransitionEntry(_EntryBase):
    """The probability of moving along an edge (``target_id``) in one cycle."""

    attribute: str = "transition"
    strategy: str | None = None  # a strategy entity id; None: every strategy without its own value
    probability: float = Field(ge=0.0, le=1.0)
    notes: str | None = None


class MarkovTransitionSet(_Base):
    entries: list[MarkovTransitionEntry] = Field(default_factory=list)


class MarkovRewardEntry(_EntryBase):
    """A state's (``target_id``) cost per cycle and utility weight per year."""

    attribute: str = "reward"
    strategy: str | None = None
    cost: float | None = None
    utility: float | None = None
    notes: str | None = None


class MarkovRewardSet(_Base):
    entries: list[MarkovRewardEntry] = Field(default_factory=list)


class MarkovStartEntry(_EntryBase):
    attribute: str = "start"
    proportion: float = Field(ge=0.0, le=1.0)


class MarkovStartSet(_Base):
    entries: list[MarkovStartEntry] = Field(default_factory=list)
