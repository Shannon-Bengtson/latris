"""What the person said at each checkpoint — the record that an AI building a model asked them.

An AI building a model in chat (or driving the CLI) stops at five checkpoints, one per modelling
phase, and asks the person a few specific questions: the framing, the structure, the values that
matter, whether the result surprises them, and who the report is for. Each answer — or each
explicit skip — is one ``PersonInput``. The report shows them, so a reader can tell a model the
person shaped from one the AI built alone. See latris-app ``docs/design/CHAT_CHECKPOINTS.md``.

Answers are the person's words as relayed by the agent (``relayed_by``), not a sign-off: approving
a model is a separate act (``Signoff``, the maturity ladder).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from latris.schema._base import SchemaModel
from latris.schema.common import HumanActor, now_utc

CheckpointId = Literal["framing", "structure", "values", "surprise", "audience"]
# Phase order: the first open checkpoint in this order is the one to ask.
CHECKPOINT_ORDER: tuple[CheckpointId, ...] = ("framing", "structure", "values", "surprise", "audience")

Pace = Literal["ask", "just_build"]


class _Base(SchemaModel):
    """Shared base for this module's models (strict; see ``schema._base``)."""


class PersonInput(_Base):
    """One checkpoint, answered or skipped."""

    id: str
    checkpoint: CheckpointId
    outcome: Literal["answered", "skipped"]
    questions: list[str] = Field(default_factory=list)  # what was asked
    answers: str | None = None  # the person's words, as relayed
    reason: str | None = None  # why it was skipped
    covers: list[str] = Field(default_factory=list)  # element ids the checkpoint covered (structure: staleness)
    relayed_by: str | None = None  # the agent that relayed it ("claude-code", "latris-mcp"); None: typed by the person
    authored_by: HumanActor  # the responsible person (no AI-authored records)
    recorded_at: datetime = Field(default_factory=now_utc)

    @model_validator(mode="after")
    def _outcome_has_its_text(self) -> PersonInput:
        if self.outcome == "answered" and not (self.answers and self.answers.strip()):
            raise ValueError("an answered checkpoint needs the person's answers")
        if self.outcome == "skipped" and not (self.reason and self.reason.strip()):
            raise ValueError("a skipped checkpoint needs a reason")
        return self


class PersonInputLog(_Base):
    """Append-only: the latest entry for a checkpoint is its current state."""

    pace: Pace = "ask"
    entries: list[PersonInput] = Field(default_factory=list)
