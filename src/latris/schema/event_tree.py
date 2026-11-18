"""Event tree schema — heading order, sequences, branch probabilities, initiator frequency.

An event tree lives on the ordinary substrate. Its elements are substrate
entities with a view role (``views/roles/event_tree-roles.yaml``):
``initiating_event``, ``functional_event`` (a heading: a question answered
yes or no along the way, e.g. *Gas detected?*) or ``end_state``.

The tree itself is not a set of substrate links: a heading can be asked on
many branches and an end state reached by many sequences. It is stored as
data:

- ``views/parameters/event_tree-structure.yaml``   — :class:`ETStructure`:
  the headings in order, and each sequence as its yes/no answers plus the
  end state it reaches;
- ``views/parameters/event_tree-probability.yaml`` — :class:`ETProbabilitySet`:
  P(yes) for each heading, optionally conditional on earlier answers;
- ``views/parameters/event_tree-frequency.yaml``   — :class:`ETFrequencySet`:
  how often the initiating event occurs.

Each probability and frequency carries its own provenance (``EntryBase``).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from latris.schema.attributes import EntryBase, _Base

ETElement = Literal["initiating_event", "functional_event", "end_state"]
ET_ELEMENTS: tuple[str, ...] = ("initiating_event", "functional_event", "end_state")
Answer = Literal["yes", "no"]


class ETStep(_Base):
    """One heading's answer on a sequence."""

    heading: str  # entity id of a functional event
    answer: Answer


class ETSequence(_Base):
    """A path through the tree — the answers given, in heading order — and where it ends."""

    path: list[ETStep] = Field(default_factory=list)
    end_state: str  # entity id


class ETStructure(_Base):
    headings: list[str] = Field(default_factory=list)  # functional-event ids, left to right
    sequences: list[ETSequence] = Field(default_factory=list)


class ETProbabilityEntry(EntryBase):
    """P(yes) for a heading — in general, or given earlier headings' answers.

    The most specific entry whose ``given`` matches a branch applies there.
    """

    attribute: str = "probability"
    p_yes: float = Field(ge=0.0, le=1.0)
    given: list[ETStep] = Field(default_factory=list)
    notes: str | None = None


class ETProbabilitySet(_Base):
    entries: list[ETProbabilityEntry] = Field(default_factory=list)


class ETFrequencyEntry(EntryBase):
    """How often the initiating event occurs, per year."""

    attribute: str = "frequency"
    frequency: float = Field(ge=0.0)
    notes: str | None = None


class ETFrequencySet(_Base):
    entries: list[ETFrequencyEntry] = Field(default_factory=list)
