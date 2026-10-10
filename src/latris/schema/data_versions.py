"""Dataset versioning schemas.

Named snapshots of a dataset at a specific git commit.  Versioning is
per-dataset — independent of project-level milestones.  Restoring a
version checks out the file from the recorded commit SHA and writes it
back as a new commit.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from latris.schema.common import HumanActor


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class DatasetVersion(_Base):
    """A named snapshot of a dataset at a specific commit."""

    id: str
    dataset_id: str
    name: str
    description: str = ""
    commit_sha: str
    content_hash: str
    row_count: int
    column_count: int
    column_names: list[str] = Field(default_factory=list)
    created_by: HumanActor | None = None


class DatasetVersionLibrary(_Base):
    """All dataset versions in the project."""

    entries: list[DatasetVersion] = Field(default_factory=list)
