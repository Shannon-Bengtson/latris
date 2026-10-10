"""Expert elicitation schemas.

First-class representation of structured expert elicitation sessions —
distinct from direct human authoring, AI proposal, or data-derived values.
See ``docs/design/ELICITATION.md`` for the full design rationale.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from latris.schema.common import ExpertActor, HumanActor, now_utc


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ElicitationProtocol(_Base):
    """Describes the elicitation method used in a session."""

    name: Literal[
        "delphi",
        "shelf",
        "idea",
        "cooke",
        "ahp",
        "direct",
        "workshop",
        "other",
    ]
    rounds_planned: int = 1
    anonymous: bool = False
    aggregation_method: Literal[
        "median",
        "mean",
        "weighted-mean",
        "consensus",
        "cooke-weights",
        "none",
    ] = "median"
    calibration_used: bool = False
    notes: str | None = None


class ExpertResponse(_Base):
    """One expert's contribution in one round."""

    expert: ExpertActor | None = None  # null while still anonymous
    anonymised_id: str | None = None  # tracks identity across anonymous rounds
    round: int
    raw_input: str  # text, distribution spec, ranking, etc.
    rationale: str | None = None
    submitted_at: datetime = Field(default_factory=now_utc)


class TargetAttribute(_Base):
    """An (entity/edge ID, attribute name) pair being elicited."""

    target_id: str
    attribute: str


ElicitationSessionPhase = Literal["active", "finalised"]


class ElicitationSession(_Base):
    """A complete elicitation session with protocol, experts, and responses.

    Uses ``phase`` rather than ``status`` so the word ``status`` stays
    reserved for the unified Maturity ladder. See
    docs/design/MATURITY_LADDER.md.
    """

    id: str
    held_at: date
    facilitator: HumanActor
    experts: list[ExpertActor] = Field(default_factory=list)
    protocol: ElicitationProtocol
    target_attributes: list[TargetAttribute] = Field(default_factory=list)
    raw_responses: list[ExpertResponse] = Field(default_factory=list)
    aggregated_result: dict | None = None
    confidence_summary: str | None = None
    notes: str | None = None
    notes_file: str | None = None
    phase: ElicitationSessionPhase = "active"


class ElicitationIndexEntry(_Base):
    """One entry in the elicitation index — maps session ID to file path."""

    id: str
    file_path: str


class ElicitationLog(_Base):
    """Index of all elicitation sessions in a project."""

    entries: list[ElicitationIndexEntry] = Field(default_factory=list)
