"""Review pack schema — structured external review round-trip.

A ReviewManifest is embedded in the exported HTML file. At export time
reviewer and items are empty; the reviewer's browser fills them in.
On import, feedback items are mapped to existing provenance types
(challenges, questions, signoffs). The ReviewSession is the on-disk
lifecycle record.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from latris.schema.common import HumanActor, now_utc


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


FeedbackType = Literal["challenge", "question", "signoff"]


class ReviewerInfo(_Base):
    """Reviewer identity — collected in the HTML form."""

    name: str
    email: str | None = None
    role: str = "Reviewer"


class ReviewFeedbackItem(_Base):
    """A single piece of structured reviewer feedback."""

    target_id: str | None = None  # entity/edge ID, or None for project-level
    feedback_type: FeedbackType
    text: str


class ReviewManifest(_Base):
    """Metadata envelope embedded in the HTML file's JSON block."""

    review_session_id: str
    project_name: str
    export_commit_sha: str
    exported_at: datetime = Field(default_factory=now_utc)
    exported_by: HumanActor
    pack: str
    # Formalism this review was scoped to ("" = whole project / legacy export).
    model_type: str = ""
    sections: list[str]
    element_ids: dict[str, str] = Field(default_factory=dict)  # id → label
    reviewer: ReviewerInfo | None = None
    items: list[ReviewFeedbackItem] = Field(default_factory=list)
    completed_at: datetime | None = None


ReviewSessionPhase = Literal["exported", "imported"]


class ReviewSession(_Base):
    """On-disk record of a review round-trip — stored in provenance/.

    Uses ``phase`` rather than ``status`` so the word ``status`` stays
    reserved for the unified Maturity ladder. See
    docs/design/MATURITY_LADDER.md.
    """

    id: str
    export_commit_sha: str
    import_commit_sha: str | None = None
    exported_at: datetime = Field(default_factory=now_utc)
    imported_at: datetime | None = None
    exported_by: HumanActor
    reviewer: ReviewerInfo | None = None
    pack: str
    # Formalism this review was scoped to ("" = whole project / legacy session).
    model_type: str = ""
    sections: list[str]
    item_count: int = 0
    phase: ReviewSessionPhase = "exported"


class ReviewSessionLog(_Base):
    entries: list[ReviewSession] = Field(default_factory=list)
