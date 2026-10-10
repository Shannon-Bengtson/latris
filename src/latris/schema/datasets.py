"""Dataset registration schemas.

First-class representation of structured data sources that algorithms can
consume — distinct from ``Reference`` (a citation of an external document).
See ``docs/design/DATA_AND_ANALYSIS.md`` for the full design rationale.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from latris.schema.common import AIActor, HumanActor


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ColumnSpec(_Base):
    """Current metadata for a single column in a dataset.

    Tracks the column name (matching the CSV header), inferred dtype,
    optional semantic role, and optional description.  Updated after
    every structural data operation (rename, cast, drop, etc.).
    """

    name: str
    dtype: Literal[
        "string",
        "int64",
        "float64",
        "bool",
        "datetime",
        "category",
    ] = "string"
    role: Literal["feature", "target", "index", "ignore", "id"] | None = None
    description: str | None = None


class Dataset(_Base):
    """A registered dataset that analysis runs can reference."""

    id: str
    name: str
    description: str
    source_type: Literal["file", "url", "database", "api", "synthetic"]
    location: str
    schema_info: dict | None = None
    rows: int | None = None
    columns: list[ColumnSpec] = Field(default_factory=list)
    license: str | None = None
    storage_policy: Literal["committed", "external", "lfs"] = "external"
    registered_by: HumanActor | AIActor | None = None


class DatasetLibrary(_Base):
    """All registered datasets in a project."""

    entries: list[Dataset] = Field(default_factory=list)
