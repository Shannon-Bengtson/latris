from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


def now_utc() -> datetime:
    """Current UTC time with tzinfo set. ISO-8601 on serialisation."""
    return datetime.now(UTC)


# -- Provenance axes (M11) --------------------------------------------------

ProvenanceOrigin = Literal[
    "human-direct",
    "human-elicited",
    "ai-proposed",
    "data-derived",
    "imported",
    "mixed",
]

ProvenanceVerification = Literal[
    "unverified",
    "ai-verified",
    "human-verified",
]

# -- AI interrogation Phase 1 audit axes (EvidenceLink only) ----------------
# A single "verified" badge can't carry the four orthogonal questions a
# reviewer needs to answer about an evidence link. The four axes below
# split the concern: who proposed it (verified_by), what they actually
# saw (SourceAccess), whether the source backs the specific claim
# (SupportVerdict), and where exactly (quote + QuoteLocation). See
# docs/design/AI_INTERROGATION.md.

SourceAccess = Literal[
    "title_only",  # proposer saw only title + bibkey
    "abstract",  # proposer saw an abstract or short snapshot
    "full_text_chunk",  # proposer saw a top-k chunk from full text
    "full_text",  # proposer saw the full document
]

SupportVerdict = Literal[
    "unverified",  # no claim-level verification has been performed
    "supports",  # source supports the specific claim (verbatim quote)
    "contradicts",  # source contradicts the claim
    "orthogonal",  # source is on-topic but doesn't address the claim
    "insufficient_extract",  # extract is too narrow to decide
]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, protected_namespaces=())


class HumanActor(_Base):
    kind: Literal["human"] = "human"
    name: str
    email: str | None = None


class AIActor(_Base):
    kind: Literal["ai"] = "ai"
    model_id: str  # e.g. "claude-opus-4-6", "gpt-4o"


class ExpertActor(_Base):
    """Domain expert participating in structured elicitation."""

    kind: Literal["expert"] = "expert"
    name: str
    email: str | None = None
    credentials: str | None = None
    affiliation: str | None = None
    calibration_score: float | None = None


Actor = Annotated[HumanActor | AIActor | ExpertActor, Field(discriminator="kind")]


class Informants(_Base):
    """Who did what to an attribute. Every role is a list of actors."""

    proposed_by: list[HumanActor | AIActor | ExpertActor] = Field(default_factory=list)
    extended_by: list[HumanActor | AIActor | ExpertActor] = Field(default_factory=list)
    contested_by: list[HumanActor | AIActor | ExpertActor] = Field(default_factory=list)
    approved_by: list[HumanActor | AIActor | ExpertActor] = Field(default_factory=list)


class QuoteLocation(_Base):
    """Pointer to a verbatim span in a source document.

    Populated by Phase 4's source-verification flow; defined here so
    Phase 1's EvidenceLink schema is forward-compatible without
    further migration. `chunk_hash` identifies a stable extract; `page`
    and `offset` locate the span within it.
    """

    chunk_hash: str
    page: int | None = None
    offset: int | None = None
