"""Analysis run schemas.

Append-only log of algorithm executions (structure learning, parameter
estimation, validation, etc.) — distinct from ``AIInteraction`` (LLM calls).
See ``docs/design/DATA_AND_ANALYSIS.md`` for the full design rationale.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from latris.schema.common import HumanActor


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class AnalysisRun(_Base):
    """Record of a single algorithm execution against the project."""

    id: str
    run_by: HumanActor
    purpose: Literal[
        "structure-learning",
        "parameter-estimation",
        "validation",
        "sensitivity-analysis",
        "inference",
        "calibration",
        "simulation",
        "other",
    ]
    algorithm: str
    library_version: str
    hyperparameters: dict = Field(default_factory=dict)
    seed: int | None = None
    input_dataset_ids: list[str] = Field(default_factory=list)
    input_model_commit: str = ""
    target_view: str | None = None
    output_summary: str = ""
    output_artifacts: list[str] = Field(default_factory=list)
    metrics: dict = Field(default_factory=dict)
    affected_target_ids: list[str] = Field(default_factory=list)
    duration_seconds: float | None = None
