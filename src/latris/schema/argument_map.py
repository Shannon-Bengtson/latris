"""Argument map schema — how each premise bears on the claim it is offered for, and a person's assessment.

An argument map lives on the ordinary substrate: claims are entities with a
view role (``views/roles/argument_map-roles.yaml``: ``conclusion``, ``claim``
or ``question``); a link from a premise to the claim it bears on is an
ordinary edge. Stored, each with provenance (design:
``docs/engineering/ARGUMENT_MAP.md``):

- ``views/parameters/argument_map-link.yaml``  — :class:`ArgumentLinkSet`:
  whether a link supports or attacks, which reason it belongs to (premises in
  one reason work only together), its warrant and qualifier;
- ``views/parameters/argument_map-claim.yaml`` — :class:`ArgumentClaimSet`: a
  person's assessment of a claim the map doesn't argue further.

A claim's grounds are its ordinary citations, and an open challenge on a link
is an objection to the inference itself — both reused, not stored here.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from latris.schema.attributes import EntryBase, _Base

ArgumentElement = Literal["conclusion", "claim", "question"]
ARGUMENT_ELEMENTS: tuple[str, ...] = ("conclusion", "claim", "question")
Relation = Literal["supports", "attacks"]
RELATIONS: tuple[str, ...] = ("supports", "attacks")
Qualifier = Literal["certainly", "probably", "possibly"]
QUALIFIERS: tuple[str, ...] = ("certainly", "probably", "possibly")
Assessment = Literal["accepted", "rejected"]


class ArgumentLinkEntry(EntryBase):
    """How a premise (the edge ``target_id``'s source) bears on a claim (its target)."""

    attribute: str = "link"
    relation: Relation = "supports"
    reason: str | None = None  # premises sharing a reason name form one linked reason; None: a reason alone
    warrant: str | None = None  # why the premise bears on the claim (Toulmin)
    qualifier: Qualifier | None = None  # how strongly the arguer says it does
    notes: str | None = None


class ArgumentLinkSet(_Base):
    entries: list[ArgumentLinkEntry] = Field(default_factory=list)


class ArgumentClaimEntry(EntryBase):
    """A person's assessment of a claim (``target_id``) — for a premise the map takes as given or not."""

    attribute: str = "claim"
    assessment: Assessment | None = None
    rationale: str | None = None


class ArgumentClaimSet(_Base):
    entries: list[ArgumentClaimEntry] = Field(default_factory=list)
