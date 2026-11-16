"""Fault tree kernels — minimal cut sets, exact top-event probability, importance.

Pure functions over a tree given as ``gates`` (event id → (gate, k, input ids))
and a set of leaf events (basic or undeveloped). No I/O.

- **Minimal cut sets** — MOCUS-style expansion (Fussell & Vesely 1972), done
  bottom-up with superset elimination at every gate, so repeated events are
  handled correctly. A k-out-of-n gate expands through the recurrence
  ``atleast(k, x, rest) = (x AND atleast(k-1, rest)) OR atleast(k, rest)``.
- **Top-event probability** — exact, from a binary decision diagram of the
  tree (Rauzy 1993), assuming the leaf events are independent. Exact even
  when an event feeds more than one gate, where the textbook bottom-up gate
  formulas double-count. The rare-event approximation and the min-cut upper
  bound (Vesely et al. 1981) are reported beside it for comparison.
- **Importance** — Birnbaum, Fussell–Vesely and risk achievement worth, each
  computed exactly on the diagram by setting one event's probability to 1 or 0.
"""

from __future__ import annotations

import math
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import combinations

MAX_CUT_SETS = 20000


class TooManyCutSets(ValueError):
    """The expansion passed ``MAX_CUT_SETS``; a lower max order bounds it."""


Gates = dict[str, tuple[str, int | None, list[str]]]


# ── minimal cut sets ─────────────────────────────────────────────────


def _minimise(sets: Iterable[frozenset[str]], max_order: int | None) -> list[frozenset[str]]:
    kept: list[frozenset[str]] = []
    for s in sorted(set(sets), key=lambda x: (len(x), sorted(x))):
        if max_order is not None and len(s) > max_order:
            continue
        if not any(k <= s for k in kept):
            kept.append(s)
            if len(kept) > MAX_CUT_SETS:
                raise TooManyCutSets(
                    f"more than {MAX_CUT_SETS} cut sets; limit the order (e.g. --max-order 3) to list the shortest"
                )
    return kept


def _and(a: list[frozenset[str]], b: list[frozenset[str]], max_order: int | None) -> list[frozenset[str]]:
    if len(a) * len(b) > MAX_CUT_SETS * 50:
        raise TooManyCutSets(
            f"more than {MAX_CUT_SETS} cut sets; limit the order (e.g. --max-order 3) to list the shortest"
        )
    return _minimise((x | y for x in a for y in b), max_order)


def minimal_cut_sets(top: str, gates: Gates, *, max_order: int | None = None) -> list[frozenset[str]]:
    """The minimal cut sets of ``top``, shortest first (sets above ``max_order`` left out)."""
    memo: dict[str, list[frozenset[str]]] = {}

    def cs(node: str) -> list[frozenset[str]]:
        if node in memo:
            return memo[node]
        if node not in gates:
            out = [frozenset([node])]
        else:
            gate, k, inputs = gates[node]
            parts = [cs(i) for i in inputs]
            if gate == "or":
                out = _minimise((s for p in parts for s in p), max_order)
            elif gate == "and":
                out = [frozenset()]
                for p in parts:
                    out = _and(out, p, max_order)
            else:  # vote: at least k of the inputs
                at: dict[tuple[int, int], list[frozenset[str]]] = {}

                def atleast(need: int, i: int) -> list[frozenset[str]]:
                    if need <= 0:
                        return [frozenset()]
                    if len(parts) - i < need:
                        return []
                    key = (need, i)
                    if key not in at:
                        with_i = _and(parts[i], atleast(need - 1, i + 1), max_order)
                        at[key] = _minimise([*with_i, *atleast(need, i + 1)], max_order)
                    return at[key]

                out = atleast(k or 1, 0)
        memo[node] = out
        return out

    return cs(top)


# ── binary decision diagram ──────────────────────────────────────────


class BDD:
    """A reduced, ordered BDD over the leaf events. Node 0 is false, 1 is true."""

    def __init__(self, order: list[str]):
        self.order = order
        self.index = {v: i for i, v in enumerate(order)}
        self.nodes: list[tuple[int, int, int]] = [(len(order), 0, 0), (len(order), 1, 1)]  # (var, low, high)
        self.unique: dict[tuple[int, int, int], int] = {}
        self._apply: dict[tuple[str, int, int], int] = {}

    def mk(self, var: int, low: int, high: int) -> int:
        if low == high:
            return low
        key = (var, low, high)
        if key not in self.unique:
            self.unique[key] = len(self.nodes)
            self.nodes.append(key)
        return self.unique[key]

    def var(self, name: str) -> int:
        return self.mk(self.index[name], 0, 1)

    def apply(self, op: str, a: int, b: int) -> int:
        if op == "and":
            if a == 0 or b == 0:
                return 0
            if a == 1:
                return b
            if b == 1:
                return a
        else:
            if a == 1 or b == 1:
                return 1
            if a == 0:
                return b
            if b == 0:
                return a
        if a == b:
            return a
        if a > b:
            a, b = b, a
        key = (op, a, b)
        if key in self._apply:
            return self._apply[key]
        va, la, ha = self.nodes[a]
        vb, lb, hb = self.nodes[b]
        v = min(va, vb)
        a0, a1 = (la, ha) if va == v else (a, a)
        b0, b1 = (lb, hb) if vb == v else (b, b)
        out = self.mk(v, self.apply(op, a0, b0), self.apply(op, a1, b1))
        self._apply[key] = out
        return out

    def probability(self, root: int, p: dict[str, float]) -> float:
        memo: dict[int, float] = {0: 0.0, 1: 1.0}

        def pr(n: int) -> float:
            if n in memo:
                return memo[n]
            v, lo, hi = self.nodes[n]
            q = p[self.order[v]]
            memo[n] = q * pr(hi) + (1.0 - q) * pr(lo)
            return memo[n]

        return pr(root)


def _leaf_order(top: str, gates: Gates) -> list[str]:
    """Leaves in depth-first order from the top — a good BDD variable order for trees."""
    seen: set[str] = set()
    order: list[str] = []

    def walk(n: str) -> None:
        if n in seen:
            return
        seen.add(n)
        if n in gates:
            for i in gates[n][2]:
                walk(i)
        else:
            order.append(n)

    walk(top)
    return order


def build_bdd(top: str, gates: Gates) -> tuple[BDD, int]:
    bdd = BDD(_leaf_order(top, gates))
    memo: dict[str, int] = {}

    def node(n: str) -> int:
        if n in memo:
            return memo[n]
        if n not in gates:
            out = bdd.var(n)
        else:
            gate, k, inputs = gates[n]
            fs = [node(i) for i in inputs]
            if gate in ("and", "or"):
                out = 1 if gate == "and" else 0
                for f in fs:
                    out = bdd.apply(gate, out, f)
            else:
                at: dict[tuple[int, int], int] = {}

                def atleast(need: int, i: int) -> int:
                    if need <= 0:
                        return 1
                    if len(fs) - i < need:
                        return 0
                    if (need, i) not in at:
                        at[(need, i)] = bdd.apply(
                            "or", bdd.apply("and", fs[i], atleast(need - 1, i + 1)), atleast(need, i + 1)
                        )
                    return at[(need, i)]

                out = atleast(k or 1, 0)
        memo[n] = out
        return out

    limit = sys.getrecursionlimit()
    sys.setrecursionlimit(max(limit, 10000))
    try:
        return bdd, node(top)
    finally:
        sys.setrecursionlimit(limit)


# ── quantification ───────────────────────────────────────────────────


@dataclass
class Importance:
    event: str
    probability: float
    birnbaum: float  # P(top | event) − P(top | not event)
    fussell_vesely: float  # share of the top-event probability that needs this event
    raw: float | None  # risk achievement worth: P(top | event) / P(top)


@dataclass
class Quantification:
    top_probability: float  # exact (BDD)
    rare_event: float  # Σ P(cut set)
    min_cut_upper_bound: float  # 1 − Π (1 − P(cut set))
    importance: list[Importance]


def cut_set_probability(cut: frozenset[str], p: dict[str, float]) -> float:
    return math.prod(p[e] for e in cut)


def quantify(top: str, gates: Gates, p: dict[str, float], cut_sets: list[frozenset[str]]) -> Quantification:
    """Exact top-event probability and importance; ``p`` must cover every leaf under ``top``."""
    bdd, root = build_bdd(top, gates)
    p_top = bdd.probability(root, p)
    importance = []
    for e in bdd.order:
        up = bdd.probability(root, {**p, e: 1.0})
        down = bdd.probability(root, {**p, e: 0.0})
        importance.append(Importance(
            event=e, probability=p[e], birnbaum=up - down,
            fussell_vesely=(p_top - down) / p_top if p_top > 0 else 0.0,
            raw=up / p_top if p_top > 0 else None,
        ))
    importance.sort(key=lambda i: (-i.fussell_vesely, -i.birnbaum, i.event))
    probs = [cut_set_probability(c, p) for c in cut_sets]
    return Quantification(
        top_probability=p_top,
        rare_event=sum(probs),
        min_cut_upper_bound=1.0 - math.prod(1.0 - x for x in probs),
        importance=importance,
    )


def leaves_under(top: str, gates: Gates) -> list[str]:
    return _leaf_order(top, gates)


def brute_force_probability(top: str, gates: Gates, p: dict[str, float]) -> float:
    """Truth-table enumeration — for tests only (exponential in the number of leaves)."""
    leaves = _leaf_order(top, gates)

    def occurs(n: str, state: dict[str, bool]) -> bool:
        if n not in gates:
            return state[n]
        gate, k, inputs = gates[n]
        hits = sum(occurs(i, state) for i in inputs)
        return hits == len(inputs) if gate == "and" else hits >= 1 if gate == "or" else hits >= (k or 1)

    total = 0.0
    for r in range(len(leaves) + 1):
        for on in combinations(leaves, r):
            state = {v: v in on for v in leaves}
            if occurs(top, state):
                total += math.prod(p[v] if state[v] else 1 - p[v] for v in leaves)
    return total
