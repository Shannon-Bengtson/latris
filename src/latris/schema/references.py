from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from latris.schema._base import SchemaModel
from latris.schema.common import now_utc
from latris.schema.ids import new_id

MAX_BIBKEY_LENGTH = 200


def validate_bibkey(bibkey: str) -> str:
    """Reject bibkeys that are unsafe to use anywhere near a file path.

    Applied when a key is created (add, BibTeX/DOI import). It is not a
    model validator, so projects that already hold an odd key still load;
    ``ProjectPaths.references_extract_path`` contains those separately.
    """
    if not isinstance(bibkey, str) or not bibkey.strip():
        raise ValueError("bibkey must be a non-empty string")
    if len(bibkey) > MAX_BIBKEY_LENGTH:
        raise ValueError(f"bibkey is too long (max {MAX_BIBKEY_LENGTH} characters)")
    if bibkey != bibkey.strip() or any(ch.isspace() for ch in bibkey):
        raise ValueError(f"bibkey {bibkey!r} must not contain whitespace")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in bibkey):
        raise ValueError(f"bibkey {bibkey!r} must not contain control characters")
    if "/" in bibkey or "\\" in bibkey or ".." in bibkey or bibkey.startswith((".", "-")):
        raise ValueError(
            f"bibkey {bibkey!r} must not contain '/', '\\\\' or '..', or start with '.' or '-'"
        )
    return bibkey

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


SNAPSHOT_EXTRACT_MAX = 2000
"""Longest ``SourceSnapshot.extract`` operations will store (characters).

Enforced by the operations that write snapshots and reported by
``latris check integrity``; not a schema constraint, so projects saved
before the limit was enforced still load.
"""


class SourceSnapshot(SchemaModel):

    retrieval_url: str
    fetched_at: datetime = Field(default_factory=now_utc)
    content_hash: str  # sha256 hex of the captured text
    extract: str | None = None  # bounded text payload, ≤2000 chars
    kind: SourceSnapshotKind = "abstract"


class Reference(SchemaModel):
    """A single citation in the reference library."""

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
    # The key of the source this one was read through (a review quoting a
    # primary study): the citation is second-hand, and the report says so.
    cited_via: str | None = None


class ReferenceLibrary(SchemaModel):

    entries: list[Reference] = Field(default_factory=list)
