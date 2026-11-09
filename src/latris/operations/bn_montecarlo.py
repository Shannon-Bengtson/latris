"""Probabilistic sensitivity analysis (PSA) for Bayesian networks: how sure is this probability?

A table's numbers are estimates. Saying a table is "worth n observations"
puts a Dirichlet around each of its rows (Noisy-OR: a Beta around each cause's
strength and the leak), centred on the current values. Each draw re-samples
every uncertain table, rebuilds the network and re-asks the query; the spread
of answers is how much the conclusion depends on how well the numbers are
known. Small n — a rough expert guess — gives wide intervals; large n — a table
learned from plenty of data — narrow ones. Tables with no stated uncertainty
are held fixed and listed as such.

The output also says which tables drive the spread: the rank correlation
between each table's sampled values and the answer.
"""

from __future__ import annotations

import random
import time
from typing import Any

from latris.operations import _bn_engine
from latris.operations._bn_canonical import expand_noisy_or
from latris.operations._sampling import beta_around, dirichlet, percentile, spearman
from latris.operations.bn_inference import applied_likelihood
from latris.operations.uncertainty import BN_TABLE, row_cell
from latris.schema.attributes import ParameterUncertainty
from latris.schema.bn import CPTEntry, NoisyOrEntry

MAX_RUNS = 2000
DEFAULT_RUNS = 500
DEFAULT_SEED = 1234
PERCENTILES = (2.5, 25.0, 50.0, 75.0, 97.5)


def _r(x: float) -> float:
    return round(x, 6)


def _row_n(specs: dict[str, ParameterUncertainty], parents: list[str], parent_states: dict[str, str]) -> float | None:
    row = specs.get(row_cell(parents, parent_states)) if parents else None
    whole = specs.get(BN_TABLE)
    spec = row or whole
    return spec.params["n"] if spec else None


def monte_carlo(
    state_spaces: dict[str, list[str]],
    cpts: dict[str, CPTEntry],
    noisy: dict[str, NoisyOrEntry],
    specs: dict[str, dict[str, ParameterUncertainty]],
    target: str,
    *,
    state: str | None = None,
    evidence: dict[str, str] | None = None,
    soft: dict[str, dict[str, float]] | None = None,
    likelihood: dict[str, dict[str, float]] | None = None,
    runs: int = DEFAULT_RUNS,
    seed: int = DEFAULT_SEED,
    max_seconds: float = 60.0,
    labels: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Re-ask P(target | evidence) under ``runs`` draws of the uncertain tables."""
    if not 2 <= runs <= MAX_RUNS:
        raise ValueError(f"runs must be between 2 and {MAX_RUNS}")
    evidence = dict(evidence or {})
    labels = labels or {}
    if target not in cpts:
        raise ValueError(f"{labels.get(target, target)!r} is not in the network")
    if target in evidence:
        raise ValueError(f"{labels.get(target, target)} is observed; ask about a node that isn't")
    uncertain = {k: v for k, v in specs.items() if k in cpts}
    if not uncertain:
        raise ValueError(
            "no probability table has an uncertainty yet — say how many observations one is worth, "
            "e.g. `latris bn set-uncertainty Flood --n 20`"
        )

    def query(tables: dict[str, CPTEntry]) -> dict[str, float]:
        network = _bn_engine.build_network(state_spaces, tables)
        soft_done = {k: dict(v) for k, v in (soft or {}).items()}
        applied = applied_likelihood(network, state_spaces, evidence, soft_done, dict(likelihood or {}))
        return _bn_engine.query_marginals(network, [target], evidence, likelihood=applied or None)[target]

    point = query(cpts)
    rng = random.Random(seed)
    order = sorted(uncertain)  # fixed order: a seed fully determines the draws
    answers: list[dict[str, float]] = []
    # Per table, per sampled row (or Noisy-OR parameter): its value in each draw.
    sampled: dict[str, dict[str, list[float]]] = {k: {} for k in order}
    started = time.perf_counter()
    for i in range(runs):
        if i == 1:
            estimate = (time.perf_counter() - started) * runs
            if estimate > max_seconds:
                raise ValueError(
                    f"{runs} draws would take about {estimate:.0f} s (limit {max_seconds:g} s); use fewer --runs"
                )
        tables = dict(cpts)
        for node in order:
            node_specs = uncertain[node]
            if node in noisy:
                n = node_specs[BN_TABLE].params["n"]
                ne = noisy[node]
                drawn = ne.model_copy(
                    update={
                        "leak": beta_around(rng, ne.leak, n),
                        "links": [lk.model_copy(update={"prob": beta_around(rng, lk.prob, n)}) for lk in ne.links],
                    }
                )
                tables[node] = expand_noisy_or(drawn, state_spaces)
                sampled[node].setdefault("leak", []).append(drawn.leak)
                for lk in drawn.links:
                    sampled[node].setdefault(lk.parent_id, []).append(lk.prob)
                continue
            entry = cpts[node]
            rows = []
            for j, row in enumerate(entry.rows):
                n = _row_n(node_specs, entry.parents, row.parent_states)
                p = dirichlet(rng, row.p, n) if n else list(row.p)
                rows.append(row.model_copy(update={"p": p}))
                if n:
                    sampled[node].setdefault(str(j), []).append(p[0])
            tables[node] = entry.model_copy(update={"rows": rows})
        answers.append(query(tables))
    seconds = time.perf_counter() - started

    states = state_spaces[target]
    by_state: dict[str, Any] = {}
    for s in states:
        values = sorted(a[s] for a in answers)
        by_state[s] = {
            "point": _r(point[s]),
            "mean": _r(sum(values) / len(values)),
            **{f"p{p:g}": _r(percentile(values, p)) for p in PERCENTILES},
        }
    if state is not None and state not in states:
        raise ValueError(f"{state!r} is not a state of {labels.get(target, target)} (states: {states})")
    focus = state or states[0]  # the state asked about; by default the first (usually the event)
    # A table drives the spread as much as its most influential row (rank correlation with the answer).
    focus_values = [a[focus] for a in answers]
    drivers = []
    for node in order:
        rhos = [r for r in (spearman(v, focus_values) for v in sampled[node].values()) if r is not None]
        rho = max(rhos, key=abs) if rhos else None
        drivers.append({"node": node, "label": labels.get(node, node), "rho": None if rho is None else _r(rho)})
    drivers.sort(key=lambda d: -abs(d["rho"] or 0.0))

    tables_out = []
    for node in sorted(cpts, key=lambda k: labels.get(k, k)):
        node_specs = uncertain.get(node)
        if not node_specs:
            tables_out.append({"node": node, "label": labels.get(node, node), "fixed": True})
            continue
        whole = node_specs.get(BN_TABLE)
        tables_out.append(
            {
                "node": node,
                "label": labels.get(node, node),
                "fixed": False,
                "n": whole.params["n"] if whole else None,
                "row_overrides": len([c for c in node_specs if c != BN_TABLE]),
                "reason": (whole or next(iter(node_specs.values()))).reason,
                "origin": (whole or next(iter(node_specs.values()))).origin,
                "verification": (whole or next(iter(node_specs.values()))).verification,
                "noisy_or": node in noisy,
            }
        )
    return {
        "target": target,
        "focus_state": focus,
        "states": states,
        "by_state": by_state,
        "evidence": evidence,
        "soft": dict(soft or {}),
        "likelihood": dict(likelihood or {}),
        "runs": runs,
        "seed": seed,
        "tables": tables_out,
        "drivers": drivers,
        "labels": {**{k: labels.get(k, k) for k in cpts}},
        "seconds": round(seconds, 3),
    }


def describe(p: dict[str, Any]) -> str:
    """'P(Flood = yes | Rain = heavy): 44% (95% of draws 31%–58%)'."""
    labels = p["labels"]
    s = p["focus_state"]
    b = p["by_state"][s]
    given = ", ".join(f"{labels.get(k, k)} = {v}" for k, v in sorted(p["evidence"].items()))
    soft = ", ".join(
        f"{labels.get(k, k)} ~ " + "/".join(f"{st} {q:.0%}" for st, q in d.items())
        for k, d in sorted(p["soft"].items())
    )
    cond = "; ".join(x for x in (given, soft) if x)
    return (
        f"P({labels.get(p['target'], p['target'])} = {s}{' | ' + cond if cond else ''}): {b['point']:.0%} "
        f"(95% of {p['runs']} draws {b['p2.5']:.0%}–{b['p97.5']:.0%})"
    )
