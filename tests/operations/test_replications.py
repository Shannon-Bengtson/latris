"""Replications: every shipped model reproduces its expected results, and each expected value is recomputed
here without Latris — so a typo in a manifest or a regression in an engine fails, not just a mismatch
between the two."""

from __future__ import annotations

import itertools
import json
import math
from pathlib import Path
from typing import Any

import networkx as nx
import pytest

from latris.operations import replications as ops
from latris.operations.errors import NotFoundError
from latris.schema.replication import Replication, ReplicationCheck

REPS = {r.id: r for r in ops.list_replications()}


def _spec(rep_id: str) -> dict[str, Any]:
    return json.loads(ops.spec_path(rep_id).read_text(encoding="utf-8"))


def _check(rep_id: str, check_id: str) -> ReplicationCheck:
    return next(c for c in REPS[rep_id].checks if c.id == check_id)


# ── Every replication passes ─────────────────────────────────────────────────


@pytest.mark.parametrize("rep_id", sorted(REPS))
def test_reproduces(rep_id: str, git_identity: tuple[str, str]) -> None:
    report = ops.check_replication(rep_id)
    failed = [(o.id, o.expected, o.actual) for o in report.outcomes if not o.passed]
    assert report.passed, f"{rep_id}: {failed}"
    assert len(report.outcomes) == len(REPS[rep_id].checks)
    assert report.root is None


def test_keep_builds_a_project(tmp_path: Path, git_identity: tuple[str, str]) -> None:
    report = ops.check_replication("system-archetypes", root=tmp_path / "arch")
    assert report.passed and report.root == str(tmp_path / "arch")
    assert (tmp_path / "arch" / "project.yaml").is_file()


def test_unknown_replication() -> None:
    with pytest.raises(NotFoundError, match="known: "):
        ops.get_replication("nope")


def test_a_wrong_expectation_fails(monkeypatch: pytest.MonkeyPatch, git_identity: tuple[str, str]) -> None:
    rep = REPS["system-archetypes"]
    wrong = rep.model_copy(update={"checks": [rep.checks[0].model_copy(update={"expected": 3.0})]})
    monkeypatch.setattr(ops, "get_replication", lambda _id: wrong)
    report = ops.check_replication("system-archetypes")
    assert not report.passed
    assert report.outcomes[0].actual == 2.0


def test_a_failed_analysis_refuses(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, git_identity: tuple[str, str]) -> None:
    from latris.operations import build

    real = build.build_from_spec

    def broken(*args: Any, **kwargs: Any) -> Any:
        result = real(*args, **kwargs)
        result.notes.append("analysis 'bn_query' not run: boom")
        return result

    monkeypatch.setattr(build, "build_from_spec", broken)
    with pytest.raises(ValueError, match="boom"):
        ops.build_replication("asia", tmp_path / "asia")


# ── Reading values from a thinned series ─────────────────────────────────────


def test_interpolate_and_peak() -> None:
    times = [float(t) for t in range(11)]
    series = [-(t - 4.3) ** 2 + 10 for t in times]
    assert ops._interpolate(times, series, 2.5) == pytest.approx(-(2.5 - 4.3) ** 2 + 10)
    t_peak, v_peak = ops._peak(times, series)
    assert t_peak == pytest.approx(4.3) and v_peak == pytest.approx(10)
    assert ops._peak(times, list(range(11))) == (10.0, 10.0)  # rising to the end: the last point
    assert ops._interpolate([0.0, 1.0], [0.0, 2.0], 0.5) == 1.0
    with pytest.raises(ValueError, match="outside the run"):
        ops._interpolate(times, series, 11)


def test_agrees() -> None:
    base = _check("bass-diffusion", "peak-rate")
    assert ops._agrees(base, base.expected * (1 + 5e-5))
    assert not ops._agrees(base, base.expected * (1 + 5e-4))
    assert not ops._agrees(base, float("nan"))
    flag = _check("pearl-backdoor", "x4-alone-insufficient")
    assert ops._agrees(flag, False) and not ops._agrees(flag, True)
    sets = _check("pearl-backdoor", "minimal-sets")
    assert ops._agrees(sets, [["X1", "X4"], ["X2", "X4"], ["X3", "X4"], ["X4", "X5"]])


# ── Expected values, recomputed without Latris ───────────────────────────────


def test_asia_by_enumeration() -> None:
    """Enumerate the joint distribution the spec's tables define and compare with every BN check."""
    spec = _spec("asia")["bn"]
    states = {s["node"]: s["states"] for s in spec["states"]}
    tables = {t["node"]: t for t in spec["tables"]}
    nodes = list(states)
    joint: list[tuple[dict[str, str], float]] = []
    for combo in itertools.product(*(states[n] for n in nodes)):
        world = dict(zip(nodes, combo, strict=True))
        p = 1.0
        for n in nodes:
            t = tables[n]
            parents = t.get("parents", [])
            # Rows run over the parents' states, first parent slowest; each row lists the node's states.
            row = 0
            for parent in parents:
                row = row * len(states[parent]) + states[parent].index(world[parent])
            p *= t["probabilities"][row * len(states[n]) + states[n].index(world[n])]
        joint.append((world, p))
    assert sum(p for _, p in joint) == pytest.approx(1.0)

    analyses = _spec("asia")["analyses"]
    for c in REPS["asia"].checks:
        evidence = analyses[c.measure.analysis]["evidence"]
        given = [(w, p) for w, p in joint if all(w[k] == v for k, v in evidence.items())]
        value = sum(p for w, p in given if w[c.measure.node] == c.measure.state) / sum(p for _, p in given)
        assert value == pytest.approx(c.expected, abs=1e-12), c.id


def _constants(rep_id: str) -> dict[str, float]:
    sd = _spec(rep_id)["sd"]
    return {v["node"]: v["value"] for v in sd["constants"] + sd["stocks"]}


def test_bass_closed_form() -> None:
    k = _constants("bass-diffusion")
    p, q, m = k["Innovation coefficient"], k["Imitation coefficient"], k["Market size"]

    def adopters(t: float) -> float:
        e = math.exp(-(p + q) * t)
        return m * (1 - e) / (1 + q / p * e)

    for t in (5, 10, 20):
        assert _check("bass-diffusion", f"adopters-year-{t}").expected == pytest.approx(adopters(t), rel=1e-12)
    assert _check("bass-diffusion", "peak-time").expected == pytest.approx(math.log(q / p) / (p + q), rel=1e-12)
    assert _check("bass-diffusion", "peak-rate").expected == pytest.approx(m * (p + q) ** 2 / (4 * q), rel=1e-12)


def test_sir_closed_form() -> None:
    from scipy.optimize import brentq

    k = _constants("sir-epidemic")
    n = k["Population"]
    r0 = k["Contact rate"] / k["Recovery rate"]
    s0, i0 = k["Susceptible"] / n, k["Infectious"] / n
    s_inf = brentq(lambda s: math.log(s / s0) - r0 * (s - s0 - i0), 1e-12, s0 - 1e-12)
    assert _check("sir-epidemic", "final-size").expected == pytest.approx(n * (1 - s_inf), rel=1e-9)
    i_max = i0 + s0 - (1 + math.log(r0 * s0)) / r0
    assert _check("sir-epidemic", "peak-prevalence").expected == pytest.approx(n * i_max, rel=1e-12)


def _digraph(rep_id: str) -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_nodes_from(f["label"] for f in _spec(rep_id)["factors"])
    g.add_edges_from((link["from"], link["to"]) for link in _spec(rep_id)["links"])
    return g


def _backdoor(g: nx.DiGraph, x: str, y: str, z: set[str]) -> bool:
    if z & nx.descendants(g, x):
        return False
    cut = g.copy()
    cut.remove_edges_from(list(g.out_edges(x)))
    return bool(nx.is_d_separator(cut, {x}, {y}, z))


def test_pearl_by_exhaustive_search() -> None:
    g = _digraph("pearl-backdoor")
    for c in REPS["pearl-backdoor"].checks:
        if c.measure.kind == "dag_adjustment_valid":
            assert _backdoor(g, c.measure.exposure, c.measure.outcome, set(c.measure.adjust_for)) is c.expected, c.id
    candidates = sorted(set(g) - {"X", "Y"} - nx.descendants(g, "X"))
    valid = [
        set(z) for size in range(len(candidates) + 1)
        for z in itertools.combinations(candidates, size) if _backdoor(g, "X", "Y", set(z))
    ]
    minimal = sorted(sorted(z) for z in valid if not any(other < z for other in valid))
    assert _check("pearl-backdoor", "minimal-sets").expected == minimal


def test_archetype_loops_by_networkx() -> None:
    spec = _spec("system-archetypes")
    sign = {(link["from"], link["to"]): link["polarity"] for link in spec["links"]}
    counts = {"R": 0, "B": 0}
    for cycle in nx.simple_cycles(_digraph("system-archetypes")):
        negatives = sum(sign[(a, b)] == "-" for a, b in zip(cycle, cycle[1:] + cycle[:1], strict=True))
        counts["B" if negatives % 2 else "R"] += 1
    for c in REPS["system-archetypes"].checks:
        assert counts[c.measure.polarity] == c.expected, c.id


def test_every_replication_is_recomputed_here() -> None:
    """A new replication needs its own recomputation above (and its id here)."""
    assert set(REPS) == {"asia", "bass-diffusion", "pearl-backdoor", "sir-epidemic", "system-archetypes"}


def test_listing_is_schema_models() -> None:
    assert all(isinstance(r, Replication) for r in REPS.values())
