"""Deterministic text chunking + lexical scoring (Phase 4b).

Pure functions, no I/O. Used by the verification context builder to
select top-k chunks from a fetched reference's full text against a
specific claim. Embedding-based selection is explicitly out of scope
for Phase 4b — keyword/BM25-lite suffices because the audit guarantee
comes from the apply()-time verbatim check, not from chunk-selection
quality. (See docs/design/AI_INTERROGATION.md Phase 4 notes.)
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    """A contiguous span of source text plus a stable hash.

    The hash is the audit-load-bearing identifier used by
    `EvidenceLink.quote_location.chunk_hash` to point at exactly
    which span the verbatim quote was matched against.
    """

    text: str
    content_hash: str  # sha256 hex of `text`
    offset: int  # character offset in the source
    length: int  # len(text); cached for convenience


def chunk_text(
    text: str,
    *,
    window: int = 1000,
    overlap: int = 200,
) -> list[Chunk]:
    """Deterministic windowed chunks.

    Slides a ``window``-character window across the text with
    ``overlap`` characters of overlap. Last chunk is the tail of the
    text; never empty unless ``text`` itself is empty. Hashes are
    sha256 of the chunk bytes; deterministic for identical input.

    Hash-stability invariant (tested): given the same text and the
    same window/overlap, ``chunk_text`` returns identical Chunks
    across platforms and runs.
    """
    if window <= 0:
        raise ValueError(f"window must be positive, got {window!r}")
    if overlap < 0 or overlap >= window:
        raise ValueError(f"overlap must be in [0, window), got {overlap!r}")
    if not text:
        return []

    chunks: list[Chunk] = []
    step = window - overlap
    offset = 0
    while offset < len(text):
        chunk_str = text[offset : offset + window]
        digest = hashlib.sha256(chunk_str.encode("utf-8")).hexdigest()
        chunks.append(
            Chunk(
                text=chunk_str,
                content_hash=f"sha256:{digest}",
                offset=offset,
                length=len(chunk_str),
            )
        )
        if offset + window >= len(text):
            break
        offset += step
    return chunks


# A small inline stopword list. We aren't building a full IR system —
# just enough to score chunks against a claim's content words. Kept
# inline so chunking has zero external dependencies.
_STOPWORDS: frozenset[str] = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "but", "by", "can",
        "do", "does", "for", "from", "had", "has", "have", "he", "her",
        "his", "how", "i", "if", "in", "into", "is", "it", "its", "may",
        "might", "of", "on", "or", "our", "should", "so", "such", "than",
        "that", "the", "their", "them", "there", "these", "they", "this",
        "those", "to", "was", "we", "were", "what", "when", "where",
        "which", "who", "why", "will", "with", "would", "you", "your",
    }
)


_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9'-]*")


def _tokenize(text: str) -> list[str]:
    """Lowercase word tokens, stopwords removed."""
    return [
        m.group(0).lower()
        for m in _WORD_RE.finditer(text)
        if m.group(0).lower() not in _STOPWORDS
    ]


def score_chunks(chunks: list[Chunk], claim: str) -> list[tuple[Chunk, float]]:
    """Score each chunk against the claim with BM25-lite.

    Computes TF (per-chunk) × IDF (across the chunk corpus) summed
    over claim tokens. Returns ``[(chunk, score)]`` sorted descending.
    Pure stdlib; deterministic.

    Tradeoff: this favours chunks that contain rare words from the
    claim, which is what we want for verification — we'd rather route
    the model to a chunk containing the specific concept than to one
    repeating common framing terms. Since the audit guarantee is the
    verbatim quote check at apply-time, even a mid-quality ranker is
    safe — the worst case is the model not finding a quote and
    returning ``insufficient_extract``.
    """
    if not chunks:
        return []
    claim_tokens = _tokenize(claim)
    if not claim_tokens:
        # No content terms — fall back to source order.
        return [(c, 0.0) for c in chunks]

    # IDF over the chunk corpus.
    n = len(chunks)
    chunk_token_sets: list[set[str]] = [set(_tokenize(c.text)) for c in chunks]
    df: dict[str, int] = {}
    for token_set in chunk_token_sets:
        for tok in token_set:
            df[tok] = df.get(tok, 0) + 1
    idf: dict[str, float] = {
        tok: math.log((n - count + 0.5) / (count + 0.5) + 1.0)
        for tok, count in df.items()
    }

    # TF per chunk (token → count in chunk).
    chunk_tf: list[dict[str, int]] = []
    for chunk in chunks:
        counts: dict[str, int] = {}
        for tok in _tokenize(chunk.text):
            counts[tok] = counts.get(tok, 0) + 1
        chunk_tf.append(counts)

    scored: list[tuple[Chunk, float]] = []
    for chunk, tf in zip(chunks, chunk_tf):  # noqa: B905
        score = sum(tf.get(tok, 0) * idf.get(tok, 0.0) for tok in claim_tokens)
        scored.append((chunk, score))
    # Stable sort: highest score first; ties resolved by chunk offset.
    scored.sort(key=lambda pair: (-pair[1], pair[0].offset))
    return scored


def top_k(chunks: list[Chunk], claim: str, *, k: int = 3) -> list[Chunk]:
    """Convenience wrapper: return the top ``k`` chunks by claim relevance."""
    if k <= 0:
        return []
    scored = score_chunks(chunks, claim)
    return [chunk for chunk, _ in scored[:k]]
