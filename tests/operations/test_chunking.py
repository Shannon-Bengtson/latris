"""Tests for operations/_chunking.py — Phase 4b chunk + score primitives."""

from __future__ import annotations

import pytest

from latris.operations._chunking import (
    Chunk,
    chunk_text,
    score_chunks,
    top_k,
)

# ── chunk_text ───────────────────────────────────────────────────────


class TestChunkText:
    def test_empty_text_returns_empty(self) -> None:
        assert chunk_text("") == []

    def test_short_text_one_chunk(self) -> None:
        out = chunk_text("hello", window=100, overlap=10)
        assert len(out) == 1
        assert out[0].text == "hello"
        assert out[0].offset == 0
        assert out[0].length == 5
        assert out[0].content_hash.startswith("sha256:")

    def test_window_overlap_step(self) -> None:
        # 30 chars; window 10; overlap 4 → step 6 → offsets 0, 6, 12, 18, 24
        text = "a" * 10 + "b" * 10 + "c" * 10
        out = chunk_text(text, window=10, overlap=4)
        offsets = [c.offset for c in out]
        assert offsets == [0, 6, 12, 18, 24]
        for c in out:
            assert c.length == len(c.text)
            assert c.length <= 10

    def test_hash_is_deterministic(self) -> None:
        """Hash stability invariant: same text → same chunk hashes."""
        text = "Vehicle emissions drive urban air quality decline."
        a = chunk_text(text, window=50, overlap=10)
        b = chunk_text(text, window=50, overlap=10)
        assert [c.content_hash for c in a] == [c.content_hash for c in b]

    def test_hash_changes_with_text(self) -> None:
        a = chunk_text("hello world", window=50, overlap=10)
        b = chunk_text("hello earth", window=50, overlap=10)
        assert a[0].content_hash != b[0].content_hash

    def test_invalid_window_raises(self) -> None:
        with pytest.raises(ValueError, match="window must be positive"):
            chunk_text("x", window=0)

    def test_invalid_overlap_raises(self) -> None:
        with pytest.raises(ValueError, match="overlap"):
            chunk_text("x", window=10, overlap=10)
        with pytest.raises(ValueError, match="overlap"):
            chunk_text("x", window=10, overlap=-1)


# ── score_chunks / top_k ─────────────────────────────────────────────


class TestScoring:
    @staticmethod
    def _chunk(text: str, offset: int = 0) -> Chunk:
        return Chunk(text=text, content_hash=f"h{offset}", offset=offset, length=len(text))

    def test_empty_chunks_returns_empty(self) -> None:
        assert score_chunks([], "claim") == []

    def test_no_content_words_in_claim_falls_back_to_zero(self) -> None:
        chunks = [self._chunk("Vehicle emissions drive air quality decline.")]
        # All-stopword claim → tokens empty → fall back, score 0.
        scored = score_chunks(chunks, "the and of")
        assert scored[0][1] == 0.0

    def test_relevant_chunk_outranks_irrelevant(self) -> None:
        chunks = [
            self._chunk("Cooking shows on television are entertainment.", 0),
            self._chunk("Vehicle emissions drive urban air quality decline.", 100),
            self._chunk("The weather report will be sunny tomorrow.", 200),
        ]
        scored = score_chunks(chunks, "vehicle emissions and air quality")
        # Top chunk should be the one mentioning emissions + air quality.
        assert scored[0][0].offset == 100
        # Highest score must be > the others.
        assert scored[0][1] > scored[1][1]

    def test_top_k_returns_at_most_k(self) -> None:
        chunks = [self._chunk(f"chunk {i} vehicle emissions", i * 10) for i in range(5)]
        out = top_k(chunks, "vehicle emissions", k=2)
        assert len(out) == 2

    def test_top_k_zero_returns_empty(self) -> None:
        chunks = [self._chunk("anything")]
        assert top_k(chunks, "claim", k=0) == []

    def test_score_is_deterministic(self) -> None:
        chunks = [
            self._chunk("Vehicle emissions drive air quality.", 0),
            self._chunk("Carbon dioxide rises with traffic volume.", 50),
        ]
        a = score_chunks(chunks, "emissions and traffic")
        b = score_chunks(chunks, "emissions and traffic")
        assert [(c.offset, s) for c, s in a] == [(c.offset, s) for c, s in b]
