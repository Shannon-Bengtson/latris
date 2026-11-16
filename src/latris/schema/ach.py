"""ACH schema — how each piece of evidence bears on each hypothesis, and how much the evidence counts.

Analysis of competing hypotheses lives on the ordinary substrate: hypotheses
and evidence items are entities with a view role
(``views/roles/ach-roles.yaml``: ``hypothesis`` or ``evidence_item``). An
evidence item can carry its own sources through the usual citations
(``latris evidence add <item> description <key>``). Stored, each with
provenance:

- ``views/parameters/ach-rating.yaml`` — :class:`ACHRatingSet`: one rating per
  (evidence item, hypothesis), with the reasoning;
- ``views/parameters/ach-item.yaml``   — :class:`ACHItemSet`: an item's
  credibility and relevance.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from latris.schema.attributes import _Base, _EntryBase

ACHElement = Literal["hypothesis", "evidence_item"]
ACH_ELEMENTS: tuple[str, ...] = ("hypothesis", "evidence_item")
# Very consistent, consistent, neutral / not applicable, inconsistent, very inconsistent (Heuer 1999).
Rating = Literal["CC", "C", "N", "I", "II"]
RATINGS: tuple[str, ...] = ("CC", "C", "N", "I", "II")
Level = Literal["high", "medium", "low"]


class ACHRatingEntry(_EntryBase):
    """How one evidence item (``target_id``) bears on one hypothesis."""

    attribute: str = "rating"
    hypothesis: str  # hypothesis entity id
    rating: Rating
    rationale: str | None = None


class ACHRatingSet(_Base):
    entries: list[ACHRatingEntry] = Field(default_factory=list)


class ACHItemEntry(_EntryBase):
    """How much an evidence item counts: is it credible, and does it bear on the question?"""

    attribute: str = "item"
    credibility: Level = "medium"
    relevance: Level = "medium"
    notes: str | None = None


class ACHItemSet(_Base):
    entries: list[ACHItemEntry] = Field(default_factory=list)
