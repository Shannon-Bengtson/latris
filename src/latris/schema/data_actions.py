"""Data action log schemas.

Structured audit trail for every data operation applied to a dataset.
Each action records what was done, who did it, the effect on row/column
counts, and the git commit that persisted the change.  The action log
is informational — not a replay mechanism.  Undo is via dataset version
restore, not by reversing the log.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from latris.schema.common import AIActor, HumanActor

DataActionKind = Literal[
    # Cleaning
    "rename_column",
    "cast_column",
    "drop_columns",
    "drop_nan_rows",
    "fill_nan",
    "filter_rows",
    "sort_rows",
    "deduplicate",
    "replace_values",
    "strip_whitespace",
    "lowercase",
    "uppercase",
    "clip_values",
    "remove_outliers",
    # Transformation
    "log_transform",
    "normalize",
    "standardize",
    "round_values",
    "bin_discretize",
    "rank_transform",
    # Feature engineering
    "derived_column",
    "date_extract",
    "lag_lead",
    "rolling_window",
    "difference",
    "cumulative_sum",
    "pct_change",
    "ratio",
    "one_hot_encode",
    "label_encode",
    "string_split",
    "group_aggregate",
    # Reshaping
    "melt",
    "pivot",
    # Row operations
    "insert_row",
    "delete_rows",
    "duplicate_rows",
    # Cell editing
    "update_cell",
    # Column reorder
    "reorder_columns",
]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class DataAction(_Base):
    """A single recorded data operation (audit log entry)."""

    id: str
    dataset_id: str
    kind: DataActionKind
    params: dict
    summary: str
    rows_before: int | None = None
    rows_after: int | None = None
    columns_affected: list[str] = Field(default_factory=list)
    performed_by: HumanActor | AIActor | None = None
    commit_sha: str = ""


class DataActionLog(_Base):
    """Per-dataset action log.  One file per dataset under ``data/actions/``."""

    dataset_id: str
    entries: list[DataAction] = Field(default_factory=list)
