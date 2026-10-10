"""Tests for entity/edge kind coercion helpers in schema/substrate.py."""

from __future__ import annotations

import pytest

from latris.schema.substrate import coerce_edge_kind, coerce_entity_kind


class TestCoerceEntityKind:
    def test_valid_kind_passes_through_unchanged(self):
        assert coerce_entity_kind("variable") == ("variable", False)
        assert coerce_entity_kind("concept") == ("concept", False)

    @pytest.mark.parametrize(
        "role,expected",
        [
            ("driver", "variable"),
            ("lever", "variable"),
            ("outcome", "variable"),
            ("stock", "variable"),
            ("goal", "concept"),
            ("factor", "concept"),
        ],
    )
    def test_known_roles_map_to_substrate_kind(self, role, expected):
        kind, changed = coerce_entity_kind(role)
        assert kind == expected
        assert changed is True

    def test_unknown_kind_falls_back_to_concept(self):
        assert coerce_entity_kind("wibble") == ("concept", True)

    def test_is_case_insensitive(self):
        assert coerce_entity_kind("Variable") == ("variable", True)
        assert coerce_entity_kind("DRIVER") == ("variable", True)

    def test_none_and_empty_fall_back(self):
        assert coerce_entity_kind(None) == ("concept", True)
        assert coerce_entity_kind("") == ("concept", True)


class TestCoerceEdgeKind:
    def test_valid_kind_passes_through_unchanged(self):
        assert coerce_edge_kind("causal") == ("causal", False)
        assert coerce_edge_kind("association") == ("association", False)

    def test_unknown_kind_falls_back_to_causal(self):
        assert coerce_edge_kind("drives") == ("causal", True)

    def test_is_case_insensitive(self):
        assert coerce_edge_kind("Causal") == ("causal", True)

    def test_none_falls_back(self):
        assert coerce_edge_kind(None) == ("causal", True)
