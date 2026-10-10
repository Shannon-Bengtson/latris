"""Schema for AI interrogation Phase 2c — CompletenessGate records.

The gate runs before `Interpret*` and reports variables required to
answer the modelling question that are missing from the model.
Reports persist per model type at
``views/{model_type}/completeness-report.yaml`` so override decisions
survive subsequent runs.

Override flow: a human override creates an ``Exclusion`` (existing
schema in ``provenance.py``) with statement
``"Variable '<name>' deliberately excluded from model scope"`` plus a
rationale. The ``MissingVariable`` row carries the back-reference via
``excluded_via_id`` so the gate can dedupe on subsequent runs without
adding a discriminator to ``Exclusion``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from latris.schema.common import now_utc
from latris.schema.ids import new_id

MissingVariableSeverity = Literal["required", "recommended", "optional"]
MissingVariableConfidence = Literal["high", "medium", "low"]
MissingVariableDisposition = Literal["open", "added_to_model", "excluded", "dismissed"]


class MissingVariable(BaseModel):
    """A variable the completeness gate flagged as missing from the model.

    Uses ``disposition`` rather than ``status`` so the word ``status``
    stays reserved for the unified Maturity ladder. See
    docs/design/MATURITY_LADDER.md.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str = Field(default_factory=lambda: new_id("missing-var"))
    name: str
    rationale: str
    required_for: list[str] = Field(default_factory=list)
    severity: MissingVariableSeverity
    confidence: MissingVariableConfidence
    detected_at: datetime = Field(default_factory=now_utc)
    disposition: MissingVariableDisposition = "open"
    excluded_via_id: str | None = None
    added_entity_id: str | None = None


class CompletenessReport(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    model_type: str
    generated_at: datetime = Field(default_factory=now_utc)
    coverage_ratio: float = 0.0
    entries: list[MissingVariable] = Field(default_factory=list)
