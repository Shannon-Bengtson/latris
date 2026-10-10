from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from latris.schema.common import HumanActor, now_utc


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Assumption(_Base):
    id: str
    statement: str
    rationale: str | None = None
    target_id: str | None = None
    authored_by: HumanActor


class AssumptionLog(_Base):
    entries: list[Assumption] = Field(default_factory=list)


class Decision(_Base):
    """An unforced choice taken during modelling — e.g. 'chose not to include X'."""

    id: str
    statement: str
    rationale: str
    target_id: str | None = None
    authored_by: HumanActor


class DecisionLog(_Base):
    entries: list[Decision] = Field(default_factory=list)


class ModelChoice(_Base):
    """A model-type selection captured as an auditable, append-only decision.

    The live set of active formalisms is ``ProjectFoundation.selected_model_types``;
    this log is the *narrative* of how that set came to be. ``added`` / ``removed``
    track selection, ``revised`` records a rationale edit — so the latest entry for
    a given ``model_type_id`` is its current rationale, and the full history shows
    how the justification evolved.
    """

    id: str
    model_type_id: str
    action: Literal["added", "revised", "removed"]
    rationale: str = ""
    origin: Literal["human-direct", "ai-proposed"] = "human-direct"
    authored_by: HumanActor


class ModelChoiceLog(_Base):
    entries: list[ModelChoice] = Field(default_factory=list)


class Signoff(_Base):
    """Formal review approval — project-level or per-element."""

    id: str
    reviewer: HumanActor
    role: str = "Reviewer"
    scope: str = "Model"
    target_id: str | None = None  # entity/edge id, or None for project-level
    signed_at: datetime = Field(default_factory=now_utc)
    notes: str | None = None


class SignoffLog(_Base):
    entries: list[Signoff] = Field(default_factory=list)


class Session(_Base):
    """Workshop / working session record. Attached changes live in git history; this is the anchor.

    Either ``notes`` (short inline summary) or ``notes_file`` (path to a
    Markdown transcript), but not both — pick whichever fits the session.
    """

    id: str
    held_at: date
    attendees: list[HumanActor]
    notes: str | None = None
    notes_file: str | None = None  # path to a Markdown transcript, relative to project root

    @model_validator(mode="after")
    def _notes_xor_notes_file(self) -> Session:
        if self.notes is not None and self.notes_file is not None:
            raise ValueError(
                "Session: set either 'notes' (inline) or 'notes_file' (path), not both."
            )
        return self


class SessionLog(_Base):
    entries: list[Session] = Field(default_factory=list)


QuestionDisposition = Literal["open", "resolved", "abandoned"]


class Question(_Base):
    """Unresolved structural issue, parked for later.

    Uses ``disposition`` rather than ``status`` so the word ``status``
    stays reserved for the unified Maturity ladder
    (``proposed | reviewed | approved``). See
    docs/design/MATURITY_LADDER.md.
    """

    id: str
    question: str
    target_id: str | None = None
    raised_by: HumanActor
    disposition: QuestionDisposition = "open"
    resolution: str | None = None


class QuestionLog(_Base):
    entries: list[Question] = Field(default_factory=list)


class Exclusion(_Base):
    """Scope boundary / negative claim / validity-limit statement."""

    id: str
    statement: str
    rationale: str
    authored_by: HumanActor


class ExclusionLog(_Base):
    entries: list[Exclusion] = Field(default_factory=list)


class Prediction(_Base):
    """A prediction register entry — supports outcome-tracking over time."""

    id: str
    statement: str
    horizon: str  # e.g. "6 months", "by 2027-Q1"; free-form to keep the schema loose
    authored_by: HumanActor
    resolution: Literal["pending", "confirmed", "refuted", "superseded"] = "pending"
    resolution_notes: str | None = None


class PredictionLog(_Base):
    entries: list[Prediction] = Field(default_factory=list)
