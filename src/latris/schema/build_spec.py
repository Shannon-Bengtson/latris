"""A whole model in one file, for ``latris build --spec``.

Agents otherwise build a model one command (and one commit) at a time —
about a hundred calls for a dozen factors. A spec carries the same content
in one YAML or JSON document; the field names match the remote MCP
server's ``apply_changes`` operations so one vocabulary serves both.

    outcome: Volunteer departures
    factors:
      - label: Volunteer burnout
        description: Emotional and physical exhaustion from volunteering.
    links:
      - from: Workload per volunteer
        to: Volunteer burnout
        polarity: "+"
        reason: More hours per person, more exhaustion.
        confidence: high
        sources: [smith2024]
        contradicts: [tuohy2015]   # sources that argue against this link
    sources:
      - key: smith2024
        title: Burnout among community volunteers
        authors: ["Smith, Jane"]
        year: 2024
      - key: tuohy2015
        title: Workload and volunteer retention revisited
        year: 2015
    assumptions:
      - Volunteers' hours are roughly comparable across programs.
    questions:
      - Does recognition reduce departures independently of workload?
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from latris.schema.substrate import EdgeKind, EntityKind


class _Spec(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class SpecCitation(_Spec):
    """A source cited on a factor or link, by its reference key."""

    key: str
    notes: str | None = None


class SpecFactor(_Spec):
    label: str
    kind: EntityKind = "variable"
    description: str | None = None
    sources: list[str | SpecCitation] = Field(default_factory=list)
    contradicts: list[str | SpecCitation] = Field(default_factory=list)


class SpecLink(_Spec):
    from_: str = Field(alias="from")
    to: str
    kind: EdgeKind = "causal"
    polarity: Literal["+", "-"] | None = None
    reason: str | None = None  # why the polarity holds (the causal story)
    weight: float | None = Field(default=None, ge=-1, le=1)  # FCM edge weight
    description: str | None = None
    confidence: str | None = None
    sources: list[str | SpecCitation] = Field(default_factory=list)
    contradicts: list[str | SpecCitation] = Field(default_factory=list)  # sources against the link


class SpecSource(_Spec):
    key: str
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    container: str | None = None
    doi: str | None = None
    url: str | None = None


class BuildSpec(_Spec):
    """Everything ``latris build`` adds, applied as one commit."""

    model_type: str | None = None  # view for polarity and roles; default: the project's first selected type
    outcome: str | None = None  # factor the model explains (gets the outcome role)
    factors: list[SpecFactor] = Field(default_factory=list)
    links: list[SpecLink] = Field(default_factory=list)
    sources: list[SpecSource] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
