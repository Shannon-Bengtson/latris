from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from latris.schema.common import AIActor, HumanActor, now_utc

ChallengeState = Literal[
    "open",
    "retained-unchanged",
    "retained-with-caveat",
    "modified",
    "split",
    "removed",
    "unresolved",
]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, protected_namespaces=())


class ConversationTurn(_Base):
    """One exchange in a challenge or AI-mediated discussion."""

    speaker: HumanActor | AIActor
    message: str
    at: datetime = Field(default_factory=now_utc)


class Challenge(_Base):
    """A challenge attacks a specific link or attribute, resolves to a terminal state."""

    id: str
    target_id: str | None = None  # entity/edge id, or None for project-level
    target_attribute: str | None = None
    argument: str
    conversation: list[ConversationTurn] = Field(default_factory=list)
    state: ChallengeState = "open"
    opened_by: HumanActor | AIActor
    resolved_at: datetime | None = None
    resolution_rationale: str | None = None


class ChallengeLog(_Base):
    entries: list[Challenge] = Field(default_factory=list)


class AIInteraction(_Base):
    """One record in ai/interactions.jsonl — append-only.

    The ``target_ids`` / ``related_attributes`` fields exist so a future
    retrieval layer can cheaply pull "what past interactions touched edge X
    or attribute Y" without digging through the free-form ``prompt_inputs``
    dict. This is how the interaction log doubles as bespoke project memory.
    """

    id: str
    prompt_name: str  # canonical prompt library key
    prompt_inputs: dict = Field(default_factory=dict)
    model_id: str  # which LLM was used (free-form, e.g. "claude-opus-4-6")
    target_ids: list[str] = Field(default_factory=list)
    related_attributes: list[str] = Field(default_factory=list)
    response_summary: str  # short human-readable summary
    response_full: str | None = None  # full model output, inline; swap to blob ref if it grows
    proposal_ids: list[str] = Field(default_factory=list)
    # Whether a human adopted the AI proposal. Renamed from `approval`
    # to `adoption` to avoid colliding with the Maturity ladder's
    # `approved` value (the word "approved" now means "this artifact is
    # fit for the model"). See docs/design/MATURITY_LADDER.md.
    #
    # `failed` records a call that never produced a parseable response —
    # the adapter raised before we had a `parsed` proposal. The error
    # fields below carry the diagnostic. Without this state, failed
    # calls vanished from the audit trail entirely.
    adoption: Literal["pending", "approved", "rejected", "failed"] = "pending"
    approved_by: HumanActor | None = None
    # Token usage and cost from the provider response (populated on real calls
    # via the adapter layer). Keys are free-form to accommodate any provider's
    # shape; we standardise on ``input_tokens`` / ``output_tokens`` /
    # ``cache_read_tokens`` / ``cache_write_tokens`` where available.
    token_usage: dict = Field(default_factory=dict)
    cost_usd: float | None = None
    # Populated only when ``adoption == "failed"``. The raw-response excerpt
    # is truncated to the first 4 KB of the model's last completion so the
    # JSONL stays manageable; full traces live in the runner output.
    error_class: str | None = None
    error_message: str | None = None
    raw_response_excerpt: str | None = None
