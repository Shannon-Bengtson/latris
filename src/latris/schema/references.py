from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from latris.schema.common import now_utc
from latris.schema.ids import new_id

# AI interrogation Phase 2: a record of what the system actually
# fetched from a publisher. Distinct from `Reference.notes`, which is
# user-authored. The kind discriminator lets verification logic
# (Phase 4) distinguish abstract-grade content from landing-page text
# that should NOT confer abstract-level source access.
SourceSnapshotKind = Literal[
    "abstract",
    "landing_page_text",
    "full_text_excerpt",
]


class SourceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    retrieval_url: str
    fetched_at: datetime = Field(default_factory=now_utc)
    content_hash: str  # sha256 hex of the captured text
    extract: str | None = None  # bounded text payload, ≤2000 chars
    kind: SourceSnapshotKind = "abstract"


class Reference(BaseModel):
    """A single citation in the reference library."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str = Field(default_factory=lambda: new_id("reference"))
    bibkey: str
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    container: str | None = None  # journal, conference, book title
    doi: str | None = None
    url: str | None = None
    abstract: str | None = None
    imported_from: str | None = None  # e.g. "zotero", "manual"
    notes: str | None = None
    source_snapshot: SourceSnapshot | None = None


class ReferenceLibrary(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    entries: list[Reference] = Field(default_factory=list)
