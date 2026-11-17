"""Weighted (ordinal logistic) probability tables for nodes with many-state parents."""

from __future__ import annotations

import math

import pytest

from latris.operations.bn import weighted_table


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def test_zero_weights_give_the_base_distribution_in_every_row():
    probs = weighted_table(["low", "mid", "high"], [0.2, 0.5, 0.3], [{}], [["a", "b"]])
    assert probs == pytest.approx([0.2, 0.5, 0.3, 0.2, 0.5, 0.3])


def test_two_states_is_logistic_regression():
    probs = weighted_table(["yes", "no"], [0.1, 0.9], [{"on": 2.0}, {"failed": 1.0}],
                           [["on", "off"], ["failed", "ok"]])
    logit = math.log(0.1 / 0.9)
    expected_yes = [_sigmoid(logit + 3), _sigmoid(logit + 2), _sigmoid(logit + 1), 0.1]  # first parent slowest
    assert probs[0::2] == pytest.approx(expected_yes)
    assert [a + b for a, b in zip(probs[0::2], probs[1::2], strict=True)] == pytest.approx([1.0] * 4)


def test_positive_weights_push_toward_the_chosen_end():
    first = weighted_table(["low", "mid", "high"], [1 / 3] * 3, [{"x": 2.0}], [["x", "y"]])
    last = weighted_table(["low", "mid", "high"], [1 / 3] * 3, [{"x": 2.0}], [["x", "y"]], toward_first=False)
    assert first[0] > 1 / 3 and first[2] < 1 / 3  # row x leans to "low"
    assert last[2] > 1 / 3 and last[0] < 1 / 3  # … or to "high"


def test_set_weighted_table_writes_a_full_table(tmp_path, git_identity):
    from latris.operations import bn as bn_ops
    from latris.operations.edges import add_edge
    from latris.operations.init import init_project
    from latris.operations.nodes import add_node

    root = tmp_path / "proj"
    init_project(root, statement="Q?")
    ids = {n: add_node(n, root=root)[0].id for n in ("Bloom", "Barrier", "Exceedance")}
    add_edge(ids["Bloom"], ids["Exceedance"], kind="causal", root=root)
    add_edge(ids["Barrier"], ids["Exceedance"], kind="causal", root=root)
    bn_ops.set_state_space("Bloom", ["none", "moderate", "severe"], root=root)
    bn_ops.set_state_space("Barrier", ["ok", "failed"], root=root)
    bn_ops.set_state_space("Exceedance", ["yes", "no"], root=root)
    cpt, _ = bn_ops.set_weighted_table("Exceedance", [0.02, 0.98],
                                       {"Bloom": {"moderate": 1.5, "severe": 3}, "Barrier": {"failed": 2.5}},
                                       root=root)
    assert len(cpt.rows) == 6
    worst = next(r for r in cpt.rows if r.parent_states == {ids["Bloom"]: "severe", ids["Barrier"]: "failed"})
    assert worst.p[0] == pytest.approx(_sigmoid(math.log(0.02 / 0.98) + 5.5))
    with pytest.raises(ValueError, match="no state"):
        bn_ops.set_weighted_table("Exceedance", [0.02, 0.98], {"Bloom": {"huge": 1}}, root=root)
