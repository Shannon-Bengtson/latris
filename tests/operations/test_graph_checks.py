"""Tests for shared graph-structure checks."""

from dataclasses import dataclass

from latris.operations._graph_checks import find_cycle


@dataclass
class _E:
    from_id: str
    to_id: str


def test_empty_graph_has_no_cycle():
    assert find_cycle([]) == (False, None)


def test_acyclic_chain():
    edges = [_E("a", "b"), _E("b", "c"), _E("c", "d")]
    assert find_cycle(edges) == (False, None)


def test_acyclic_diamond():
    edges = [_E("a", "b"), _E("a", "c"), _E("b", "d"), _E("c", "d")]
    assert find_cycle(edges) == (False, None)


def test_simple_cycle_detected():
    edges = [_E("a", "b"), _E("b", "c"), _E("c", "a")]
    has_cycle, node = find_cycle(edges)
    assert has_cycle is True
    assert node is not None


def test_self_loop_detected():
    edges = [_E("a", "a")]
    has_cycle, node = find_cycle(edges)
    assert has_cycle is True
    assert node == "a"


def test_single_edge_no_cycle():
    edges = [_E("x", "y")]
    assert find_cycle(edges) == (False, None)


def test_disconnected_components_one_cyclic():
    edges = [_E("a", "b"), _E("c", "d"), _E("d", "c")]
    has_cycle, node = find_cycle(edges)
    assert has_cycle is True
    # The cyclic node should be from the c-d component
    assert node in ("c", "d")
