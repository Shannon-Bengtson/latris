from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = 6


class ProjectFoundation(BaseModel):
    """Anchors the project with a modelling question.

    The modelling question drives AI behaviour and default report packs
    downstream. Creation and last-update timestamps are read from git
    history (first commit, HEAD commit) rather than persisted here.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str = ""
    statement: str
    background: str = ""
    boundary: str = ""
    exclusions: str = ""
    predictions: str = ""
    # Scope contract — optional prose that sharpens AI structural output by
    # pinning down what the model should span, at what resolution, and for whom.
    coverage_dimensions: str = ""  # themes/subsystems the model must span
    granularity_level: str = ""  # intended resolution / abstraction level
    audience: str = ""  # who the model is for
    selected_model_types: list[str] = Field(default_factory=list)
    schema_version: int = SCHEMA_VERSION
