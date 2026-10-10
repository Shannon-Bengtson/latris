"""Interpretation schemas — persistent storage for the Interpret phase.

The Interpret phase bridges Model (analysis results) and Communicate
(report assembly).  Each InterpretSection pairs template-generated claims
(deterministic, from findings/analysis) with AI-generated prose
(editable by the user).

Ten section types span two audiences:

- **Technical** (for the modeller): structural_summary, key_findings,
  sensitivity, assumptions_limitations, evidence_gaps, evidence_coverage
- **Stakeholder** (flows to report): answer_to_question, implications,
  confidence_assessment, open_questions
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from latris.schema.common import now_utc

InterpretSectionId = Literal[
    "structural_summary",
    "key_findings",
    "sensitivity",
    "assumptions_limitations",
    "evidence_gaps",
    "evidence_coverage",
    "answer_to_question",
    "implications",
    "confidence_assessment",
    "open_questions",
]

INTERPRET_SECTION_IDS: tuple[InterpretSectionId, ...] = (
    "structural_summary",
    "key_findings",
    "sensitivity",
    "assumptions_limitations",
    "evidence_gaps",
    "evidence_coverage",
    "answer_to_question",
    "implications",
    "confidence_assessment",
    "open_questions",
)

InterpretSectionGenerationState = Literal[
    "empty",
    "claims_only",
    "generated",
    "edited",
]

InterpretTextSource = Literal["ai", "human-edit"]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class InterpretTextVersion(_Base):
    """A single version of the prose text for an interpretation section.

    Creation timestamp derives from ``version_id`` via ``id_timestamp``.
    """

    version_id: str
    text: str
    source: InterpretTextSource
    model_commit: str = ""


class InterpretSection(_Base):
    """A single interpretation section combining claims and prose."""

    id: str
    section_type: InterpretSectionId
    model_type: str

    # Template-generated claims (current state from analysis/findings)
    claims: list[str] = Field(default_factory=list)

    # Claims that were active when prose was last generated (staleness check)
    claims_at_generation: list[str] = Field(default_factory=list)

    # Editable prose (AI-generated, then human-edited)
    prose: str = ""
    prose_versions: list[InterpretTextVersion] = Field(default_factory=list)

    # Content-derivation state (renamed from `status` — the word is
    # reserved for the unified Maturity ladder; see
    # docs/design/MATURITY_LADDER.md).
    generation_state: InterpretSectionGenerationState = "empty"
    model_commit: str = ""

    # Staleness signal — the moment prose was last regenerated. Creation
    # is derived from ``id`` via ``id_timestamp``.
    updated_at: datetime = Field(default_factory=now_utc)


class InterpretationStore(_Base):
    """Top-level container persisted to interpretation.yaml."""

    sections: list[InterpretSection] = Field(default_factory=list)
