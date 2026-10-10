"""Lineage models — version tree metadata and milestones.

Each git branch carries a ``LineageNode`` describing that version.
Milestones are named checkpoints within a version's save history.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from latris.schema.common import HumanActor
from latris.schema.maturity import Maturity


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class LineageNode(_Base):
    """Metadata for a single version in the lineage tree.

    Stored at ``.graph-tooling/lineage-node.yaml`` on each branch.
    Parent/child topology is derived from git via
    ``repo/lineage_index.py``; only workflow-level fields live here.
    """

    id: str
    name: str
    maturity: Maturity = "proposed"
    relationship: Literal["original", "alternative"]
    created_by: HumanActor
    notes: str | None = None
    # Lifecycle (orthogonal to maturity): a version retired by a Reconcile
    # decision is archived rather than deleted, recording the surviving
    # version that superseded it. Additive + defaulted so pre-existing
    # committed lineage-node.yaml round-trips unchanged.
    archived: bool = False
    superseded_by: str | None = None


class Milestone(_Base):
    """A named checkpoint within a version's save history.

    Creation timestamp is derived from ``commit_sha`` via
    ``commit_timestamp()`` in ``repo/git.py``.
    """

    id: str
    name: str
    commit_sha: str
    maturity: Maturity = "proposed"
    created_by: HumanActor
    notes: str | None = None


class MilestoneLog(_Base):
    """All milestones on the current branch."""

    entries: list[Milestone] = Field(default_factory=list)
