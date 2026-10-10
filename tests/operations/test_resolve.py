"""Tests for the entity/edge resolution helpers (operations/_resolve.py).

Every entity/edge lookup in the system flows through these functions.
These are pure-function tests — no I/O, no git, no project setup needed.
"""

from __future__ import annotations

import pytest

from latris.operations._resolve import (
    ResolveError,
    resolve_edge,
    resolve_entity,
    resolve_target,
)
from latris.schema import Edge, Entity, Substrate


def _entity(id: str, label: str) -> Entity:
    return Entity(id=id, kind="concept", label=label)


def _edge(id: str, from_id: str = "node_A", to_id: str = "node_B") -> Edge:
    return Edge(id=id, from_id=from_id, to_id=to_id, kind="causal")


# ── resolve_entity ──────────────────────────────────────────────────


class TestResolveEntity:
    ENTITIES = [
        _entity("node_AAAA1111BBBB2222CCCC33", "Price"),
        _entity("node_DDDD4444EEEE5555FFFF66", "Demand"),
        _entity("node_GGGG7777HHHH8888IIII99", "Supply"),
    ]

    def test_exact_id(self) -> None:
        result = resolve_entity("node_AAAA1111BBBB2222CCCC33", self.ENTITIES)
        assert result.label == "Price"

    def test_label_case_insensitive(self) -> None:
        result = resolve_entity("price", self.ENTITIES)
        assert result.id == "node_AAAA1111BBBB2222CCCC33"

    def test_label_exact_case(self) -> None:
        result = resolve_entity("Price", self.ENTITIES)
        assert result.id == "node_AAAA1111BBBB2222CCCC33"

    def test_unambiguous_id_prefix(self) -> None:
        result = resolve_entity("node_AAAA", self.ENTITIES)
        assert result.label == "Price"

    def test_ambiguous_label_raises(self) -> None:
        entities = [
            _entity("node_111", "Price"),
            _entity("node_222", "Price"),
        ]
        with pytest.raises(ResolveError, match="ambiguous"):
            resolve_entity("Price", entities)

    def test_ambiguous_prefix_raises(self) -> None:
        entities = [
            _entity("node_SAME_AAAA", "A"),
            _entity("node_SAME_BBBB", "B"),
        ]
        with pytest.raises(ResolveError, match="ambiguous"):
            resolve_entity("node_SAME", entities)

    def test_no_match_raises(self) -> None:
        with pytest.raises(ResolveError, match="no node matches"):
            resolve_entity("Nonexistent", self.ENTITIES)

    def test_prefix_too_short_ignored(self) -> None:
        """Prefix shorter than 4 chars after underscore should not match."""
        with pytest.raises(ResolveError, match="no node matches"):
            resolve_entity("nod", self.ENTITIES)

    def test_prefix_with_underscore_separator(self) -> None:
        """Prefix containing the kind separator _ is valid even if short."""
        result = resolve_entity("node_AAAA", self.ENTITIES)
        assert result.label == "Price"

    def test_empty_entities_raises(self) -> None:
        with pytest.raises(ResolveError, match="no node matches"):
            resolve_entity("anything", [])


# ── resolve_edge ────────────────────────────────────────────────────


class TestResolveEdge:
    EDGES = [
        _edge("edge_AAAA1111BBBB2222CCCC33"),
        _edge("edge_DDDD4444EEEE5555FFFF66"),
    ]

    def test_exact_id(self) -> None:
        result = resolve_edge("edge_AAAA1111BBBB2222CCCC33", self.EDGES)
        assert result.id == "edge_AAAA1111BBBB2222CCCC33"

    def test_unambiguous_prefix(self) -> None:
        result = resolve_edge("edge_AAAA", self.EDGES)
        assert result.id == "edge_AAAA1111BBBB2222CCCC33"

    def test_ambiguous_prefix_raises(self) -> None:
        edges = [_edge("edge_SAME_AA"), _edge("edge_SAME_BB")]
        with pytest.raises(ResolveError, match="ambiguous"):
            resolve_edge("edge_SAME", edges)

    def test_no_match_raises(self) -> None:
        with pytest.raises(ResolveError, match="no edge matches"):
            resolve_edge("edge_ZZZZ", self.EDGES)

    def test_no_label_resolution_for_edges(self) -> None:
        """Edges don't resolve by label — only by ID or prefix."""
        with pytest.raises(ResolveError, match="no edge matches"):
            resolve_edge("some label", self.EDGES)


# ── resolve_target ──────────────────────────────────────────────────


class TestResolveTarget:
    def test_resolves_entity_first(self) -> None:
        substrate = Substrate(
            entities=[_entity("node_AAAA1111BBBB2222CCCC33", "Price")],
            edges=[_edge("edge_BBBB1111CCCC2222DDDD33")],
        )
        result = resolve_target("Price", substrate)
        assert result == "node_AAAA1111BBBB2222CCCC33"

    def test_falls_back_to_edge(self) -> None:
        substrate = Substrate(
            entities=[_entity("node_AAAA1111BBBB2222CCCC33", "Price")],
            edges=[_edge("edge_BBBB1111CCCC2222DDDD33")],
        )
        result = resolve_target("edge_BBBB", substrate)
        assert result == "edge_BBBB1111CCCC2222DDDD33"

    def test_neither_entity_nor_edge_raises(self) -> None:
        substrate = Substrate(entities=[], edges=[])
        with pytest.raises(ResolveError):
            resolve_target("nothing", substrate)
