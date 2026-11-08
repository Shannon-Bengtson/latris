"""Finding a check's quote in the text Latris holds for a source.

A quote backs a check only if it can be found: in the fetched full text
(``latris ref fetch``), the stored snapshot extract (``ref snapshot`` or a
build spec's ``extract``), or the reference's abstract. Matching forgives
what copying text changes (whitespace, curly quotes, dashes, case) and
treats an ellipsis in the quote as a gap, so "rigid rosters ... predicted
exits" matches when both parts appear in order. Nothing else is forgiven:
a paraphrase is not found.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from latris.repo.layout import ProjectPaths
from latris.schema import QuoteLocation, Reference
from latris.schema.common import SourceAccess

_FOLD = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
    "“": '"', "”": '"', "„": '"', "″": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-",
    " ": " ",
})
_ELLIPSIS = re.compile(r"\s*(?:\.\s*\.\s*\.|…|\[\s*\.\.\.\s*\])\s*")
_SPACE = re.compile(r"\s+")
# Shorter than this, a quote proves little (any text contains "the").
MIN_QUOTE_CHARS = 20

# What a match in each stored text says about what the checker had read.
_SNAPSHOT_TIER: dict[str, SourceAccess] = {
    "full_text_excerpt": "full_text_chunk",
    "abstract": "abstract",
    "landing_page_text": "title_only",
}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_FOLD)
    return _SPACE.sub(" ", text).strip().casefold()


def _find(quote: str, text: str) -> int | None:
    """Offset of the quote's first part in ``text`` (both normalised), or None."""
    parts = [p for p in (_norm(s) for s in _ELLIPSIS.split(quote)) if p.strip(" \"'")]
    hay = _norm(text)
    pos, first = 0, None
    for p in parts:
        p = p.strip(" \"'")
        i = hay.find(p, pos)
        if i < 0:
            return None
        first = i if first is None else first
        pos = i + len(p)
    return first


@dataclass(frozen=True)
class QuoteMatch:
    location: QuoteLocation
    tier: SourceAccess  # what the quote was found in
    where: str  # in words, for messages


def locate_quote(quote: str, reference: Reference, paths: ProjectPaths) -> QuoteMatch | None:
    """Where ``quote`` appears in the text held for ``reference``, best text first."""
    if len(_norm(quote)) < MIN_QUOTE_CHARS:
        return None
    full = paths.references_extract_path(reference.bibkey)
    if full.exists():
        from latris.operations._chunking import chunk_text

        for chunk in chunk_text(full.read_text(encoding="utf-8")):
            at = _find(quote, chunk.text)
            if at is not None:
                return QuoteMatch(
                    QuoteLocation(chunk_hash=chunk.content_hash, page=None, offset=chunk.offset + at),
                    "full_text_chunk", "the fetched full text",
                )
    snap = reference.source_snapshot
    if snap is not None and snap.extract:
        at = _find(quote, snap.extract)
        if at is not None:
            where = {
                "full_text_excerpt": "the stored excerpt of the text",
                "landing_page_text": "the stored landing page",
            }
            return QuoteMatch(
                QuoteLocation(chunk_hash=snap.content_hash, page=None, offset=at),
                _SNAPSHOT_TIER.get(snap.kind, "abstract"), where.get(snap.kind, "the stored abstract or summary"),
            )
    if reference.abstract:
        at = _find(quote, reference.abstract)
        if at is not None:
            return QuoteMatch(QuoteLocation(chunk_hash="abstract", page=None, offset=at), "abstract", "the abstract")
    return None


def has_stored_text(reference: Reference, paths: ProjectPaths) -> bool:
    snap = reference.source_snapshot
    return bool(
        paths.references_extract_path(reference.bibkey).exists()
        or (snap is not None and snap.extract)
        or reference.abstract
    )
