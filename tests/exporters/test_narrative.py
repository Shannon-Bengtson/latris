"""Tests for the narrative exporter — mechanical fallbacks and build_narrative()."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from latris.exporters.narrative import (
    _is_meta_commit,
    _mechanical_history,
    _mechanical_scope,
    build_narrative,
)
from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations.init import init_project
from latris.repo.layout import ProjectPaths

# ── _is_meta_commit ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "subject,expected",
    [
        ("Logged interaction i1", True),
        ("Set approval for i2", True),
        ("Approved interaction i3", True),
        ("Added node Price", False),
        ("Created edge Price → Demand", False),
        ("", False),
    ],
)
def test_is_meta_commit(subject: str, expected: bool) -> None:
    assert _is_meta_commit(subject) is expected


# ── _mechanical_scope ────────────────────────────────────────────────


def _make_entities(kinds: list[str]):
    return [SimpleNamespace(id=f"n{i}", kind=k, label=k) for i, k in enumerate(kinds)]


def _make_edges(pairs: list[tuple[str, str]]):
    return [SimpleNamespace(from_id=a, to_id=b, kind="causal") for a, b in pairs]


def test_mechanical_scope_empty() -> None:
    sub = SimpleNamespace(entities=[], edges=[])
    result = _mechanical_scope(sub, [], [], [], [])
    assert "0 entities" in result
    assert "0 relationships" in result


def test_mechanical_scope_counts_entity_kinds() -> None:
    sub = SimpleNamespace(
        entities=_make_entities(["concept", "concept", "variable"]),
        edges=_make_edges([("n0", "n1")]),
    )
    result = _mechanical_scope(sub, [], [], [], [])
    assert "3 entities" in result
    assert "2 concepts" in result
    assert "1 variable" in result
    assert "1 relationship" in result


def test_mechanical_scope_includes_evidence_and_assumptions() -> None:
    sub = SimpleNamespace(entities=_make_entities(["concept"]), edges=[])
    assumptions = [SimpleNamespace(statement="A1"), SimpleNamespace(statement="A2")]
    evidence = [SimpleNamespace() for _ in range(3)]
    references = [SimpleNamespace() for _ in range(2)]
    result = _mechanical_scope(sub, assumptions, [], evidence, references)
    assert "3 evidence links" in result
    assert "2 references" in result
    assert "2 stated assumptions" in result


def test_mechanical_scope_shows_challenge_counts() -> None:
    sub = SimpleNamespace(entities=[], edges=[])
    challenges = [
        SimpleNamespace(state="open"),
        SimpleNamespace(state="retained-unchanged"),
        SimpleNamespace(state="removed"),
    ]
    result = _mechanical_scope(sub, [], challenges, [], [])
    assert "1 open" in result
    assert "2 resolved" in result


# ── _mechanical_history ──────────────────────────────────────────────


def test_mechanical_history_empty() -> None:
    assert _mechanical_history([]) == ""


def test_mechanical_history_formats_entries() -> None:
    entries = [("2026-01-10", "Added node"), ("2026-01-11", "Added edge")]
    result = _mechanical_history(entries)
    assert "**2026-01-10**" in result
    assert "Added node" in result
    assert "**2026-01-11**" in result


# ── build_narrative (mock mode) ──────────────────────────────────────


def test_build_narrative_mechanical_fallback(tmp_path: Path, git_identity, monkeypatch) -> None:
    """In mock mode, AI narrative fails and falls back to mechanical."""
    monkeypatch.setenv("LATRIS_AI_MOCK", "1")
    root = tmp_path / "proj"
    init_project(root, statement="What drives air quality?")
    a, _ = node_ops.add_node("Emissions", kind="variable", root=root)
    b, _ = node_ops.add_node("Air Quality", kind="variable", root=root)
    edge_ops.add_edge(a.id, b.id, kind="causal", root=root)

    narrative = build_narrative(ProjectPaths(root))
    assert narrative.title  # non-empty
    assert "modelling question" in narrative.purpose
    assert "air quality" in narrative.purpose.lower()
    assert "2 entities" in narrative.structure_description or "2 variables" in narrative.structure_description
