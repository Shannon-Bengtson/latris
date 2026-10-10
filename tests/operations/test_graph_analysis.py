"""Tests for graph analysis algorithms (CLD loops + DAG structural)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from latris.operations.graph_analysis import (
    Loop,
    adjustment_sets,
    classify_loop,
    compute_centrality,
    compute_loop_participation,
    d_separation,
    enumerate_paths,
    find_all_loops,
    markov_blanket,
    propagate_polarity,
    topological_sort,
    weakly_connected_components,
)


@dataclass
class E:
    """Minimal edge for testing."""

    id: str
    from_id: str
    to_id: str


@dataclass
class N:
    """Minimal entity for testing."""

    id: str


# ═══════════════════════════════════════════════════════════════════════
# weakly_connected_components (Build→Formalise gate)
# ═══════════════════════════════════════════════════════════════════════


class TestWeaklyConnectedComponents:
    def test_single_chain_is_one_component(self):
        comps = weakly_connected_components(["a", "b", "c"], [E("e1", "a", "b"), E("e2", "b", "c")])
        assert len(comps) == 1
        assert comps[0] == {"a", "b", "c"}

    def test_direction_is_ignored(self):
        # b→a and b→c still connect all three via the undirected projection.
        comps = weakly_connected_components(["a", "b", "c"], [E("e1", "b", "a"), E("e2", "b", "c")])
        assert len(comps) == 1

    def test_orphan_node_is_its_own_component(self):
        comps = weakly_connected_components(["a", "b", "c"], [E("e1", "a", "b")])
        assert len(comps) == 2
        assert {"c"} in comps

    def test_no_edges_all_singletons(self):
        comps = weakly_connected_components(["a", "b", "c"], [])
        assert len(comps) == 3
        assert all(len(c) == 1 for c in comps)

    def test_two_disjoint_subgraphs(self):
        comps = weakly_connected_components(
            ["a", "b", "c", "d"], [E("e1", "a", "b"), E("e2", "c", "d")]
        )
        assert len(comps) == 2


# ═══════════════════════════════════════════════════════════════════════
# CLD: find_all_loops
# ═══════════════════════════════════════════════════════════════════════


class TestFindAllLoops:
    def test_empty_graph(self):
        assert find_all_loops([]) == []

    def test_no_loops(self):
        edges = [E("e1", "a", "b"), E("e2", "b", "c")]
        assert find_all_loops(edges) == []

    def test_single_self_loop(self):
        edges = [E("e1", "a", "a")]
        loops = find_all_loops(edges)
        assert len(loops) == 1
        assert loops[0].node_ids == ("a",)

    def test_triangle(self):
        edges = [E("e1", "a", "b"), E("e2", "b", "c"), E("e3", "c", "a")]
        loops = find_all_loops(edges)
        assert len(loops) == 1
        assert set(loops[0].node_ids) == {"a", "b", "c"}

    def test_figure_eight(self):
        """Two loops sharing a node."""
        edges = [
            E("e1", "a", "b"),
            E("e2", "b", "a"),  # loop 1: a-b
            E("e3", "a", "c"),
            E("e4", "c", "a"),  # loop 2: a-c
        ]
        loops = find_all_loops(edges)
        assert len(loops) == 2

    def test_diamond_no_extra_loops(self):
        """a→b, a→c, b→d, c→d — no loops (DAG)."""
        edges = [
            E("e1", "a", "b"),
            E("e2", "a", "c"),
            E("e3", "b", "d"),
            E("e4", "c", "d"),
        ]
        assert find_all_loops(edges) == []

    def test_loop_edge_ids_populated(self):
        edges = [E("e1", "a", "b"), E("e2", "b", "a")]
        loops = find_all_loops(edges)
        assert len(loops) == 1
        assert set(loops[0].edge_ids) == {"e1", "e2"}


# ═══════════════════════════════════════════════════════════════════════
# CLD: classify_loop
# ═══════════════════════════════════════════════════════════════════════


class TestClassifyLoop:
    def test_all_positive_is_reinforcing(self):
        loop = Loop(node_ids=("a", "b", "c"), edge_ids=("e1", "e2", "e3"))
        pol = {"e1": "+", "e2": "+", "e3": "+"}
        result = classify_loop(loop, pol)
        assert result.classification == "R"

    def test_one_negative_is_balancing(self):
        loop = Loop(node_ids=("a", "b", "c"), edge_ids=("e1", "e2", "e3"))
        pol = {"e1": "+", "e2": "-", "e3": "+"}
        result = classify_loop(loop, pol)
        assert result.classification == "B"

    def test_two_negatives_is_reinforcing(self):
        loop = Loop(node_ids=("a", "b"), edge_ids=("e1", "e2"))
        pol = {"e1": "-", "e2": "-"}
        result = classify_loop(loop, pol)
        assert result.classification == "R"

    def test_missing_polarity_is_unknown(self):
        loop = Loop(node_ids=("a", "b"), edge_ids=("e1", "e2"))
        pol = {"e1": "+"}  # e2 missing
        result = classify_loop(loop, pol)
        assert result.classification == "unknown"

    def test_ambiguous_polarity_is_unknown(self):
        """An ambiguous edge ("~") cannot contribute a determinate sign,
        so any loop containing one is classified unknown."""
        loop = Loop(node_ids=("a", "b"), edge_ids=("e1", "e2"))
        pol = {"e1": "+", "e2": "~"}
        result = classify_loop(loop, pol)
        assert result.classification == "unknown"


# ═══════════════════════════════════════════════════════════════════════
# CLD: propagate_polarity
# ═══════════════════════════════════════════════════════════════════════


class TestPropagatePolarity:
    def test_simple_chain_positive(self):
        edges = [E("e1", "a", "b"), E("e2", "b", "c")]
        pol = {"e1": "+", "e2": "+"}
        effects = propagate_polarity("a", edges, pol)
        effect_map = {e.entity_id: e.effect for e in effects}
        assert effect_map["b"] == "+"
        assert effect_map["c"] == "+"

    def test_chain_with_negative(self):
        edges = [E("e1", "a", "b"), E("e2", "b", "c")]
        pol = {"e1": "+", "e2": "-"}
        effects = propagate_polarity("a", edges, pol)
        effect_map = {e.entity_id: e.effect for e in effects}
        assert effect_map["b"] == "+"
        assert effect_map["c"] == "-"

    def test_ambiguous_via_two_paths(self):
        """a→b (+), a→c (-), b→d (+), c→d (+).
        Path a→b→d: net +. Path a→c→d: net -.  d should be ambiguous.
        """
        edges = [
            E("e1", "a", "b"),
            E("e2", "a", "c"),
            E("e3", "b", "d"),
            E("e4", "c", "d"),
        ]
        pol = {"e1": "+", "e2": "-", "e3": "+", "e4": "+"}
        effects = propagate_polarity("a", edges, pol)
        effect_map = {e.entity_id: e.effect for e in effects}
        assert effect_map["d"] == "ambiguous"

    def test_no_reachable_nodes(self):
        edges = [E("e1", "b", "c")]
        pol = {"e1": "+"}
        effects = propagate_polarity("a", edges, pol)
        assert effects == []


# ═══════════════════════════════════════════════════════════════════════
# CLD: centrality
# ═══════════════════════════════════════════════════════════════════════


class TestCentrality:
    def test_chain(self):
        entities = [N("a"), N("b"), N("c")]
        edges = [E("e1", "a", "b"), E("e2", "b", "c")]
        results = compute_centrality(entities, edges)
        result_map = {r.entity_id: r for r in results}
        assert result_map["b"].degree_in == 1
        assert result_map["b"].degree_out == 1
        assert result_map["a"].degree_in == 0
        assert result_map["c"].degree_out == 0

    def test_star_center_has_high_betweenness(self):
        """Center of star graph should have highest betweenness."""
        entities = [N("center"), N("a"), N("b"), N("c")]
        edges = [
            E("e1", "a", "center"),
            E("e2", "center", "b"),
            E("e3", "center", "c"),
        ]
        results = compute_centrality(entities, edges)
        result_map = {r.entity_id: r for r in results}
        assert result_map["center"].betweenness > result_map["a"].betweenness


class TestLoopParticipation:
    def test_no_loops(self):
        entities = [N("a"), N("b")]
        result = compute_loop_participation(entities, [])
        assert all(lp.loop_count == 0 for lp in result)

    def test_one_loop(self):
        entities = [N("a"), N("b"), N("c")]
        loops = [Loop(("a", "b"), ("e1", "e2"), "R")]
        result = compute_loop_participation(entities, loops)
        result_map = {lp.entity_id: lp for lp in result}
        assert result_map["a"].loop_count == 1
        assert result_map["a"].reinforcing_count == 1
        assert result_map["c"].loop_count == 0


# ═══════════════════════════════════════════════════════════════════════
# DAG: topological_sort
# ═══════════════════════════════════════════════════════════════════════


class TestTopologicalSort:
    def test_chain(self):
        edges = [E("e1", "a", "b"), E("e2", "b", "c")]
        order = topological_sort(edges)
        assert order.index("a") < order.index("b") < order.index("c")

    def test_diamond(self):
        edges = [
            E("e1", "a", "b"),
            E("e2", "a", "c"),
            E("e3", "b", "d"),
            E("e4", "c", "d"),
        ]
        order = topological_sort(edges)
        assert order.index("a") < order.index("b")
        assert order.index("a") < order.index("c")
        assert order.index("b") < order.index("d")
        assert order.index("c") < order.index("d")

    def test_cycle_raises(self):
        edges = [E("e1", "a", "b"), E("e2", "b", "a")]
        with pytest.raises(ValueError, match="cycle"):
            topological_sort(edges)


# ═══════════════════════════════════════════════════════════════════════
# DAG: d_separation
# ═══════════════════════════════════════════════════════════════════════


class TestDSeparation:
    def test_chain_unconditional(self):
        """a → b → c: a and c are NOT d-separated (active chain)."""
        edges = [E("e1", "a", "b"), E("e2", "b", "c")]
        assert d_separation(edges, {"a"}, {"c"}, set()) is False

    def test_chain_conditioned_on_middle(self):
        """a → b → c: a and c ARE d-separated given b."""
        edges = [E("e1", "a", "b"), E("e2", "b", "c")]
        assert d_separation(edges, {"a"}, {"c"}, {"b"}) is True

    def test_fork_unconditional(self):
        """a ← b → c: a and c are NOT d-separated (active fork)."""
        edges = [E("e1", "b", "a"), E("e2", "b", "c")]
        assert d_separation(edges, {"a"}, {"c"}, set()) is False

    def test_fork_conditioned_on_center(self):
        """a ← b → c: a and c ARE d-separated given b."""
        edges = [E("e1", "b", "a"), E("e2", "b", "c")]
        assert d_separation(edges, {"a"}, {"c"}, {"b"}) is True

    def test_collider_unconditional(self):
        """a → b ← c: a and c ARE d-separated (inactive collider)."""
        edges = [E("e1", "a", "b"), E("e2", "c", "b")]
        assert d_separation(edges, {"a"}, {"c"}, set()) is True

    def test_collider_conditioned_on_collider(self):
        """a → b ← c: a and c are NOT d-separated given b (activated)."""
        edges = [E("e1", "a", "b"), E("e2", "c", "b")]
        assert d_separation(edges, {"a"}, {"c"}, {"b"}) is False

    def test_collider_conditioned_on_descendant(self):
        """a → b ← c, b → d: a and c NOT d-sep given d (collider
        activated via descendant)."""
        edges = [E("e1", "a", "b"), E("e2", "c", "b"), E("e3", "b", "d")]
        assert d_separation(edges, {"a"}, {"c"}, {"d"}) is False

    def test_disconnected_nodes(self):
        """a → b, c → d: a and c ARE d-separated (no path)."""
        edges = [E("e1", "a", "b"), E("e2", "c", "d")]
        assert d_separation(edges, {"a"}, {"c"}, set()) is True


# ═══════════════════════════════════════════════════════════════════════
# DAG: markov_blanket
# ═══════════════════════════════════════════════════════════════════════


class TestMarkovBlanket:
    def test_middle_of_chain(self):
        """a → b → c: blanket of b = {a, c}."""
        edges = [E("e1", "a", "b"), E("e2", "b", "c")]
        assert markov_blanket("b", edges) == {"a", "c"}

    def test_root_node(self):
        """a → b, a → c: blanket of a = {b, c}."""
        edges = [E("e1", "a", "b"), E("e2", "a", "c")]
        assert markov_blanket("a", edges) == {"b", "c"}

    def test_leaf_node(self):
        """a → c, b → c: blanket of c = {a, b}."""
        edges = [E("e1", "a", "c"), E("e2", "b", "c")]
        assert markov_blanket("c", edges) == {"a", "b"}

    def test_co_parents(self):
        """a → c, b → c, c → d: blanket of a = {c, b, d}?
        No: blanket of a = children(a) ∪ parents(a) ∪ co-parents.
        children(a) = {c}, parents(a) = {}, co-parents = other parents
        of a's children = {b}. So blanket = {c, b}.
        """
        edges = [E("e1", "a", "c"), E("e2", "b", "c"), E("e3", "c", "d")]
        assert markov_blanket("a", edges) == {"c", "b"}

    def test_isolated_node(self):
        """No edges involving 'x'."""
        edges = [E("e1", "a", "b")]
        assert markov_blanket("x", edges) == set()


# ═══════════════════════════════════════════════════════════════════════
# DAG: enumerate_paths
# ═══════════════════════════════════════════════════════════════════════


class TestEnumeratePaths:
    def test_single_path(self):
        edges = [E("e1", "a", "b"), E("e2", "b", "c")]
        paths = enumerate_paths("a", "c", edges)
        assert len(paths) == 1
        assert len(paths[0].nodes) == 3

    def test_no_path(self):
        edges = [E("e1", "a", "b")]
        paths = enumerate_paths("a", "c", edges)
        assert paths == []

    def test_two_paths(self):
        """a→b→d, a→c→d: two paths from a to d."""
        edges = [
            E("e1", "a", "b"),
            E("e2", "b", "d"),
            E("e3", "a", "c"),
            E("e4", "c", "d"),
        ]
        paths = enumerate_paths("a", "d", edges)
        assert len(paths) == 2

    def test_collider_classification(self):
        """a → b ← c: path from a to c through collider b."""
        edges = [E("e1", "a", "b"), E("e2", "c", "b")]
        paths = enumerate_paths("a", "c", edges)
        assert len(paths) == 1
        # Middle node should be classified as collider
        assert paths[0].nodes[1].classification == "collider"


# ═══════════════════════════════════════════════════════════════════════
# DAG: adjustment_sets
# ═══════════════════════════════════════════════════════════════════════


class TestAdjustmentSets:
    def test_single_confounder(self):
        """x ← z → y, x → y: adjust for z."""
        edges = [
            E("e1", "z", "x"),
            E("e2", "z", "y"),
            E("e3", "x", "y"),
        ]
        sets = adjustment_sets("x", "y", edges)
        assert any({"z"} == s for s in sets)

    def test_no_confounding(self):
        """x → y only: no backdoor paths, empty set valid."""
        edges = [E("e1", "x", "y")]
        sets = adjustment_sets("x", "y", edges)
        assert set() in sets

    def test_mediator_not_in_set(self):
        """x → m → y: m is a descendant of x, should not be adjusted for."""
        edges = [E("e1", "x", "m"), E("e2", "m", "y")]
        sets = adjustment_sets("x", "y", edges)
        # Should find the empty set (no confounding)
        assert set() in sets
        # m should not appear in any valid adjustment set
        assert not any("m" in s for s in sets)
