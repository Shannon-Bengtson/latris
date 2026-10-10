"""Acceptance criterion for AI interrogation Phase 1: analysis must
filter to causal edges so non-causal kinds (decision_rule, governance)
do not inflate loop counts or centrality.

Per `docs/design/AI_INTERROGATION.md`:
> Adding the new EdgeKind literals without filtering analysis callers
> is a no-op and does not count as completion of this phase.
"""

from __future__ import annotations

from dataclasses import dataclass

from latris.operations.graph_analysis import (
    causal_edges,
    compute_centrality,
    find_all_loops,
)


@dataclass
class E:
    """Minimal edge with kind."""

    id: str
    from_id: str
    to_id: str
    kind: str = "causal"


@dataclass
class N:
    id: str


class TestCausalEdgesHelper:
    def test_empty(self):
        assert causal_edges([]) == []

    def test_all_causal_pass_through(self):
        edges = [E("e1", "a", "b", "causal"), E("e2", "b", "c", "causal")]
        assert causal_edges(edges) == edges

    def test_filters_non_causal(self):
        edges = [
            E("e1", "a", "b", "causal"),
            E("e2", "b", "c", "decision_rule"),
            E("e3", "c", "d", "governance"),
            E("e4", "d", "e", "flow"),
            E("e5", "e", "f", "definitional"),
        ]
        result = causal_edges(edges)
        assert len(result) == 1
        assert result[0].id == "e1"

    def test_accepts_generator(self):
        """Helper accepts any Iterable, not just list."""
        edges = [E("e1", "a", "b", "causal"), E("e2", "b", "c", "decision_rule")]
        result = causal_edges(e for e in edges)
        assert [r.id for r in result] == ["e1"]


class TestLoopCountIgnoresNonCausalEdges:
    """The capability-run inflation bug: loops composed of non-causal
    edges (e.g. Firm Revenue → 4DWW as a decision rule) inflated the
    feedback-loop count. Filter must catch this."""

    def test_decision_rule_loop_is_not_counted(self):
        """A→B (causal), B→A (decision_rule) is not a feedback loop;
        the decision-rule edge represents policy, not mechanism."""
        all_edges = [
            E("e1", "a", "b", "causal"),
            E("e2", "b", "a", "decision_rule"),
        ]
        # Without filtering: looks like a 2-cycle.
        assert len(find_all_loops(all_edges)) == 1
        # With the helper: no loop.
        assert find_all_loops(causal_edges(all_edges)) == []

    def test_mixed_substrate_loop_count(self):
        """Two genuine causal loops + one phantom loop closed by a
        governance edge. Filtered count = 2; unfiltered = 3."""
        all_edges = [
            # Causal loop 1: a → b → a
            E("e1", "a", "b", "causal"),
            E("e2", "b", "a", "causal"),
            # Causal loop 2: c → d → c
            E("e3", "c", "d", "causal"),
            E("e4", "d", "c", "causal"),
            # Phantom loop closed by governance: e → f → e
            E("e5", "e", "f", "causal"),
            E("e6", "f", "e", "governance"),
        ]
        unfiltered = find_all_loops(all_edges)
        filtered = find_all_loops(causal_edges(all_edges))
        assert len(unfiltered) == 3
        assert len(filtered) == 2

    def test_filter_matches_causal_only_subgraph(self):
        """The doc's explicit acceptance criterion: filtered loop count
        equals the loop count for the causal-only subgraph."""
        all_edges = [
            E("e1", "a", "b", "causal"),
            E("e2", "b", "c", "causal"),
            E("e3", "c", "a", "causal"),
            E("e4", "a", "d", "decision_rule"),
            E("e5", "d", "a", "decision_rule"),
        ]
        causal_only = [e for e in all_edges if e.kind == "causal"]
        assert len(find_all_loops(causal_edges(all_edges))) == len(find_all_loops(causal_only))


class TestCentralityIgnoresNonCausalEdges:
    def test_governance_does_not_inflate_degree(self):
        """A node with 1 causal edge and 5 governance edges should report
        causal degree, not total degree, when callers use the filter."""
        nodes = [N("a"), N("b"), N("c"), N("d"), N("e"), N("f"), N("g")]
        edges = [
            E("e1", "a", "b", "causal"),
            E("e2", "a", "c", "governance"),
            E("e3", "a", "d", "governance"),
            E("e4", "a", "e", "governance"),
            E("e5", "a", "f", "governance"),
            E("e6", "a", "g", "governance"),
        ]
        unfiltered = {c.entity_id: c for c in compute_centrality(nodes, edges)}
        filtered = {c.entity_id: c for c in compute_centrality(nodes, causal_edges(edges))}
        assert unfiltered["a"].degree_total == 6
        assert filtered["a"].degree_total == 1
