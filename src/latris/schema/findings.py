"""Finding schemas — standardised model output artefacts.

A Finding is a first-class interpretive result produced by analysis
operations, AI interactions, or direct human judgement.  Findings bridge
ephemeral computation outputs and the reporting pipeline, with a fixed
category taxonomy that works across all model types.

Six categories map to report subsections:

- **structure** — graph topology, connectivity, key paths, cycles
- **dynamics** — equilibria, steady states, convergence, time evolution
- **sensitivity** — what matters most: centrality, leverage, key parameters
- **inference** — causal/probabilistic conclusions, independence, effects
- **diagnostics** — model quality, validation, calibration, gaps
- **recommendations** — next steps, priorities, identified gaps
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from latris.schema.common import (
    HumanActor,
    Informants,
    ProvenanceOrigin,
    ProvenanceVerification,
)
from latris.schema.maturity import Maturity

FindingCategory = Literal[
    "structure",
    "dynamics",
    "sensitivity",
    "inference",
    "diagnostics",
    "recommendations",
]

FINDING_CATEGORIES: tuple[FindingCategory, ...] = (
    "structure",
    "dynamics",
    "sensitivity",
    "inference",
    "diagnostics",
    "recommendations",
)

FindingSourceType = Literal[
    "analysis-run",
    "ai-interaction",
    "human-direct",
]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Finding(_Base):
    """A single interpretive result from analysis, AI, or human judgement."""

    id: str
    category: FindingCategory
    model_type: str
    maturity: Maturity = "proposed"

    # Human-readable
    statement: str
    detail: str = ""

    # Machine-readable
    payload: dict = Field(default_factory=dict)

    # Provenance
    origin: ProvenanceOrigin = "human-direct"
    verification: ProvenanceVerification = "unverified"
    source_id: str | None = None
    source_type: FindingSourceType = "human-direct"
    informants: Informants = Field(default_factory=Informants)

    # Supersession (typed pointer to findings this one replaces)
    supersedes: list[str] = Field(default_factory=list)

    # Staleness tracking
    model_commit: str = ""
    target_ids: list[str] = Field(default_factory=list)
    related_attributes: list[str] = Field(default_factory=list)

    # Event timestamps (creation is derived from id via id_timestamp())
    reviewed_at: datetime | None = None
    reviewed_by: HumanActor | None = None


class FindingLog(_Base):
    """In-memory representation of the findings JSONL store."""

    entries: list[Finding] = Field(default_factory=list)
