"""Fault tree kernels: cut sets, exact probability, importance."""

from __future__ import annotations

import random

import pytest

from latris.operations import _ft_engine as ft


def fs(*sets):
    return [frozenset(s) for s in sets]


def test_or_of_and():
    gates = {"T": ("or", None, ["G", "c"]), "G": ("and", None, ["a", "b"])}
    assert ft.minimal_cut_sets("T", gates) == fs({"c"}, {"a", "b"})
    p = {"a": 0.1, "b": 0.2, "c": 0.05}
    q = ft.quantify("T", gates, p, ft.minimal_cut_sets("T", gates))
    assert q.top_probability == pytest.approx(1 - (1 - 0.02) * (1 - 0.05))
    assert q.rare_event == pytest.approx(0.07)


def test_repeated_event_is_exact_and_absorbed():
    # T = (a OR b) AND (a OR c)  →  cut sets {a}, {b, c}
    gates = {"T": ("and", None, ["G1", "G2"]), "G1": ("or", None, ["a", "b"]), "G2": ("or", None, ["a", "c"])}
    assert ft.minimal_cut_sets("T", gates) == fs({"a"}, {"b", "c"})
    p = {"a": 0.3, "b": 0.4, "c": 0.5}
    q = ft.quantify("T", gates, p, ft.minimal_cut_sets("T", gates))
    naive = (1 - 0.7 * 0.6) * (1 - 0.7 * 0.5)  # treats the two branches as independent: wrong
    assert q.top_probability == pytest.approx(0.3 + 0.7 * 0.4 * 0.5)
    assert q.top_probability != pytest.approx(naive)


def test_vote_gate():
    gates = {"T": ("vote", 2, ["a", "b", "c"])}
    assert ft.minimal_cut_sets("T", gates) == fs({"a", "b"}, {"a", "c"}, {"b", "c"})
    p = {"a": 0.1, "b": 0.1, "c": 0.1}
    q = ft.quantify("T", gates, p, ft.minimal_cut_sets("T", gates))
    assert q.top_probability == pytest.approx(3 * 0.01 * 0.9 + 0.001)


def test_max_order_limits_listing():
    gates = {"T": ("or", None, ["a", "G"]), "G": ("and", None, ["b", "c", "d"])}
    assert ft.minimal_cut_sets("T", gates, max_order=2) == fs({"a"})


def test_importance():
    gates = {"T": ("or", None, ["G", "c"]), "G": ("and", None, ["a", "b"])}
    p = {"a": 0.1, "b": 0.2, "c": 0.05}
    q = ft.quantify("T", gates, p, ft.minimal_cut_sets("T", gates))
    imp = {i.event: i for i in q.importance}
    assert imp["c"].birnbaum == pytest.approx(1 - 0.02)
    assert imp["a"].birnbaum == pytest.approx(0.2 * (1 - 0.05))
    assert imp["c"].fussell_vesely == pytest.approx((q.top_probability - 0.02) / q.top_probability)
    assert q.importance[0].event == "c"  # ranked by Fussell–Vesely
    assert imp["c"].raw == pytest.approx(1 / q.top_probability)


def test_too_many_cut_sets(monkeypatch):
    monkeypatch.setattr(ft, "MAX_CUT_SETS", 10)
    gates = {"T": ("and", None, ["G1", "G2", "G3"])}
    for i in range(1, 4):
        gates[f"G{i}"] = ("or", None, [f"x{i}{j}" for j in range(4)])
    with pytest.raises(ft.TooManyCutSets):
        ft.minimal_cut_sets("T", gates)


@pytest.mark.parametrize("seed", range(25))
def test_random_trees_match_brute_force(seed):
    rng = random.Random(seed)
    leaves = [f"x{i}" for i in range(rng.randint(3, 7))]
    gates: dict = {}
    pool = list(leaves)
    for g in range(rng.randint(1, 4)):
        name = f"G{g}"
        inputs = rng.sample(pool, rng.randint(2, min(4, len(pool))))
        kind = rng.choice(["and", "or", "vote"])
        gates[name] = (kind, rng.randint(1, len(inputs)) if kind == "vote" else None, inputs)
        pool.append(name)
    top = f"G{len(gates) - 1}"
    used = ft.leaves_under(top, gates)
    p = {v: rng.uniform(0.01, 0.6) for v in used}
    cuts = ft.minimal_cut_sets(top, gates)
    q = ft.quantify(top, gates, p, cuts)
    assert q.top_probability == pytest.approx(ft.brute_force_probability(top, gates, p))
    assert q.top_probability <= q.min_cut_upper_bound + 1e-9
    assert q.min_cut_upper_bound <= q.rare_event + 1e-9
    # every minimal cut set triggers the top; removing any one event from it doesn't
    for c in cuts:
        on = {v: 1.0 if v in c else 0.0 for v in used}
        assert ft.brute_force_probability(top, gates, on) == pytest.approx(1.0)
        for e in c:
            off = {**on, e: 0.0}
            assert ft.brute_force_probability(top, gates, off) == pytest.approx(0.0)
