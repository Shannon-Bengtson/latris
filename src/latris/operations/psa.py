"""Probabilistic sensitivity analysis (PSA) for decision trees and Markov cohort models.

A decision tree's expected values and a Markov model's costs and outcomes are
computed from point values — a probability, a payoff, a cost per cycle, a
utility weight — that are rarely known exactly. Probabilistic sensitivity
analysis (Briggs, Claxton & Sculpher 2006, ch. 4–5; Doubilet et al. 1985)
gives each uncertain input a distribution, samples them all together and
reruns the model for each sample, so the answer carries the uncertainty of
everything it rests on at once rather than one input at a time.

What can carry a range (stored with the other parameter uncertainty, with
provenance; the cell names what it describes):

- decision tree: a terminal node's payoff (``decision_tree:payoff``); a
  branch's value (``decision_tree:value``); the probability of one branch of a
  two-branch chance node (``decision_tree:probability``, the other branch
  takes the rest); or a chance node's whole set of branch probabilities as a
  Dirichlet "worth n observations" (``decision_tree:probabilities``). Chance
  nodes that resolve the same uncertainty under different choices take the
  same sampled probabilities in a run.
- Markov: a transition probability (``markov:transition``), a state's cost per
  cycle (``markov:cost``) or utility (``markov:utility``), or every
  probability of leaving a state as a Dirichlet (``markov:leaving``); each for
  every strategy, or for one (``:<strategy id>`` on the cell).

The conventional families are beta for probabilities and utilities and gamma
for costs, often described by a mean and standard error from a study;
:func:`moments` converts that to the distribution's parameters (the method of
moments). Probabilities are kept within [0, 1].

The decision-tree PSA reports each first choice's expected value across the
runs, how often each is best, and the expected value of perfect information
on the parameters (Claxton 1999): the most it is worth to remove all of the
parameter uncertainty before choosing. The Markov PSA reports each strategy's
cost and outcome across the runs, the incremental analysis on their means,
and — at each willingness to pay — the probability each strategy is the most
cost-effective (the cost-effectiveness acceptability curve; Fenwick, Claxton
& Sculpher 2001) and the EVPI. Both rank the inputs by how strongly they drive
the decision (Spearman rank correlation).
"""

from __future__ import annotations

import math
import random
from dataclasses import replace
from pathlib import Path
from typing import Any

from latris.operations import _sampling as smp
from latris.operations import uncertainty as unc
from latris.operations._resolve import resolve_target
from latris.operations.commit import auto_commit
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_model, load_model
from latris.schema import Substrate
from latris.schema.attributes import ParameterUncertainty
from latris.schema.common import ProvenanceOrigin, ProvenanceVerification

MODEL_TYPES = ("decision_tree", "markov")
KINDS = {"decision_tree": "dt-psa", "markov": "markov-psa"}
MAX_RUNS = 20_000
CEAC_POINTS = 41
DT_QUANTITIES = ("payoff", "value", "probability", "probabilities")
MARKOV_QUANTITIES = ("transition", "cost", "utility", "leaving")


def moments(distribution: str, mean: float, sd: float) -> dict[str, float]:
    """A beta's or gamma's parameters from its mean and standard deviation (method of moments)."""
    if sd <= 0:
        raise ValueError("the standard deviation must be positive")
    var = sd * sd
    if distribution == "beta":
        if not 0 < mean < 1:
            raise ValueError("a beta's mean must lie strictly between 0 and 1")
        if var >= mean * (1 - mean):
            raise ValueError(f"a beta with mean {mean:g} needs a standard deviation below "
                             f"{math.sqrt(mean * (1 - mean)):.3g}")
        k = mean * (1 - mean) / var - 1
        return {"alpha": mean * k, "beta": (1 - mean) * k}
    if distribution == "gamma":
        if mean <= 0:
            raise ValueError("a gamma's mean must be positive")
        return {"shape": mean * mean / var, "scale": var / mean}
    raise ValueError("a mean and standard deviation convert for beta or gamma; a normal or lognormal takes them "
                     "as they are")


# ── what can be uncertain ────────────────────────────────────────────


def _cell(model_type: str, quantity: str, strategy: str | None = None) -> str:
    return f"{model_type}:{quantity}" + (f":{strategy}" if strategy else "")


def _dt_target(target: str, quantity: str | None, paths) -> dict[str, Any]:
    from latris.operations import decision_tree as dt

    t = dt.load_tree(root=paths.root)
    sub = load_model(Substrate, paths.conceptual_yaml)
    tid = resolve_target(target, sub)
    edge = next((e for e in sub.edges if e.id == tid), None)
    if quantity is not None and quantity not in DT_QUANTITIES:
        raise ValueError(f"a decision-tree range is on a {', '.join(DT_QUANTITIES)}")
    if edge is None:
        kind = t.kind.get(tid)
        label = t.labels.get(tid, target)
        if kind == "terminal" and quantity in (None, "payoff"):
            if tid not in t.payoffs:
                raise ValueError(f"{label} has no payoff yet; set one (`latris dt payoff`) first")
            return {"id": tid, "label": f"{label} (payoff)", "cell": _cell("decision_tree", "payoff"),
                    "quantity": "payoff", "value": t.payoffs[tid].value, "bounded": False}
        if kind == "chance" and quantity in (None, "probabilities"):
            kids = t.children.get(tid, [])
            if not kids or any(e not in t.branches or t.branches[e].probability is None for e, _ in kids):
                raise ValueError(f"{label}'s branches need probabilities first (`latris dt branch -p`)")
            return {"id": tid, "label": f"{label} (branch probabilities)",
                    "cell": _cell("decision_tree", "probabilities"), "quantity": "probabilities", "value": None,
                    "bounded": True}
        raise ValueError(f"{label} isn't a terminal node (its payoff) or a chance node (its branch probabilities); "
                         "for a branch, name the link 'Parent -> Child'")
    a, b = edge.from_id, edge.to_id
    label = f"{t.labels[a]} → {t.branch_label(edge.id, b) if t.kind.get(b) else t.labels[b]}"
    kind = t.kind.get(a)
    if kind not in ("decision", "chance") or b not in t.kind:
        raise ValueError("a branch runs from a decision or chance node to another decision-tree node")
    br = t.branches.get(edge.id)
    if quantity is None:
        quantity = "probability" if kind == "chance" else "value"
    if quantity == "probability":
        if kind != "chance":
            raise ValueError("only branches from a chance node have a probability")
        if len(t.children.get(a, [])) != 2:
            raise ValueError(f"{t.labels[a]} has {len(t.children.get(a, []))} branches; a range on one branch's "
                             "probability needs exactly two (the other takes the rest). For more, give the chance "
                             "node a Dirichlet: `latris dt range <chance node> dirichlet --n 50`")
        if br is None or br.probability is None:
            raise ValueError(f"{label} has no probability yet; set one (`latris dt branch -p`) first")
        return {"id": edge.id, "label": f"P({t.uncertainty[a]} = {t.branch_label(edge.id, b)})",
                "cell": _cell("decision_tree", "probability"), "quantity": "probability", "value": br.probability,
                "bounded": True}
    if quantity == "value":
        if br is None:
            raise ValueError(f"{label} has no value along it yet; set one (`latris dt branch --value`) first")
        return {"id": edge.id, "label": f"{label} (value)", "cell": _cell("decision_tree", "value"),
                "quantity": "value", "value": br.value, "bounded": False}
    raise ValueError(f"a branch's range is on its probability or its value, not its {quantity}")


def _mk_target(target: str, quantity: str | None, strategy: str | None, paths) -> dict[str, Any]:
    from latris.operations import markov

    m = markov.load(root=paths.root)
    sub = load_model(Substrate, paths.conceptual_yaml)
    tid = resolve_target(target, sub)
    sid = markov._strategy(paths, strategy)
    who = f" under {m.labels[sid]}" if sid else ""
    if quantity is not None and quantity not in MARKOV_QUANTITIES:
        raise ValueError(f"a Markov range is on a {', '.join(MARKOV_QUANTITIES)}")
    edge = next((e for e in sub.edges if e.id == tid), None)
    if edge is not None:
        if quantity not in (None, "transition"):
            raise ValueError("a link's range is on its transition probability")
        cur = m.transitions.get((tid, sid))
        name = f"{m.labels.get(edge.from_id, '?')} → {m.labels.get(edge.to_id, '?')}"
        if cur is None:
            where = f" for {m.labels[sid]}" if sid else ""
            raise ValueError(f"{name} has no transition probability{where} yet; set it (`latris markov "
                             "transition`) first" + (" — a range for one strategy needs that strategy's own value"
                                                     if sid else ""))
        return {"id": tid, "label": f"P({name}){who}", "cell": _cell("markov", "transition", sid),
                "quantity": "transition", "value": cur.probability, "bounded": True}
    if m.labels.get(tid) is None or tid not in m.states:
        raise ValueError(f"{target!r} is neither a state nor a transition between states")
    label = m.labels[tid]
    if quantity is None:
        raise ValueError(f"say what about {label} is uncertain: --quantity cost, utility, or leaving (a Dirichlet "
                         "over its transitions out)")
    if quantity == "leaving":
        out = [e for e, (a, _) in m.edges.items() if a == tid and m.prob(e, sid)]
        if not out:
            raise ValueError(f"no transition leaves {label}{who}")
        return {"id": tid, "label": f"Leaving {label}{who}", "cell": _cell("markov", "leaving", sid),
                "quantity": "leaving", "value": None, "bounded": True}
    if quantity == "transition":
        raise ValueError("a transition's range goes on the link, 'From state -> To state'")
    r = m.rewards.get((tid, sid))
    v = getattr(r, quantity) if r is not None else None
    if v is None:
        where = f" for {m.labels[sid]}" if sid else ""
        raise ValueError(f"{label} has no {quantity}{where} yet; set it (`latris markov reward --{quantity}`) first")
    return {"id": tid, "label": f"{label} {quantity}{who}", "cell": _cell("markov", quantity, sid),
            "quantity": quantity, "value": v, "bounded": quantity == "utility" and 0 <= v <= 1}


def _target(model_type: str, target: str, quantity: str | None, strategy: str | None, paths) -> dict[str, Any]:
    if model_type == "decision_tree":
        if strategy:
            raise ValueError("--strategy applies to Markov models")
        return _dt_target(target, quantity, paths)
    if model_type == "markov":
        return _mk_target(target, quantity, strategy, paths)
    raise ValueError(f"probabilistic sensitivity analysis here is for {', '.join(MODEL_TYPES)}")


def _bounded(distribution: str, params: dict[str, float], probability: bool) -> dict[str, float]:
    """Keep a probability (or a utility given in [0, 1]) within [0, 1], truncating where the family allows."""
    if not probability:
        return dict(params)
    p = dict(params)
    if distribution in ("normal", "lognormal", "gamma"):
        p.setdefault("min", 0.0)
        p.setdefault("max", 1.0)
    if distribution in ("uniform", "triangular") and not (p["min"] >= 0 and p["max"] <= 1):
        raise ValueError("a probability must lie in [0, 1]; this range goes outside it")
    if distribution == "beta" and not (p.get("min", 0.0) >= 0 and p.get("max", 1.0) <= 1):
        raise ValueError("a probability must lie in [0, 1]; this range goes outside it")
    return p


def set_range(
    model_type: str,
    target: str,
    distribution: str,
    params: dict[str, float],
    *,
    quantity: str | None = None,
    strategy: str | None = None,
    reason: str = "",
    source_id: str | None = None,
    origin: ProvenanceOrigin = "human-direct",
    verification: ProvenanceVerification = "unverified",
    root: Path | None = None,
) -> tuple[ParameterUncertainty, str]:
    """Give a decision tree's or Markov model's input a distribution for PSA (replacing any previous one).

    ``params`` may be ``{"mean": m, "sd": s}`` for a beta or gamma (converted by the method of moments);
    a Dirichlet takes ``{"n": observations}`` and goes on a chance node or a state's transitions out.
    """
    paths = require_project(root)
    t = _target(model_type, target, quantity, strategy, paths)
    params = dict(params)
    if t["quantity"] in ("probabilities", "leaving"):
        if distribution != "dirichlet" or set(params) != {"n"}:
            raise ValueError(f"{t['label']}: a set of probabilities takes a Dirichlet worth n observations "
                             "(dirichlet --n 50)")
    elif distribution == "dirichlet":
        raise ValueError("a Dirichlet goes on a whole set of probabilities: a chance node, or a Markov state with "
                         "--quantity leaving")
    if distribution in ("beta", "gamma") and {"mean", "sd"} <= set(params):
        mean, sd = params.pop("mean"), params.pop("sd")
        params.update(moments(distribution, mean, sd))
        reason = f"mean {mean:g}, sd {sd:g}" + (f"; {reason}" if reason else "")
    params = _bounded(distribution, params, t["bounded"] and distribution != "dirichlet")
    entry = ParameterUncertainty(target_id=t["id"], distribution=distribution, params=params,  # type: ignore[arg-type]
                                 parameter_cell_id=t["cell"], reason=reason, source_id=source_id, origin=origin,
                                 verification=verification)
    if distribution != "dirichlet":
        sampler = smp.Sampler(entry)
        lo, hi = sampler.quantile(0.001), sampler.quantile(0.999)
        if not lo <= t["value"] <= hi:
            raise ValueError(f"{t['label']}'s current value {t['value']:g} lies outside this distribution "
                             f"(99.8% of it is between {lo:.3g} and {hi:.3g})")
    s = unc.load(paths)
    s.entries = [e for e in s.entries if not (e.target_id == t["id"] and e.parameter_cell_id == t["cell"])] + [entry]
    dump_model(s, paths.parameter_uncertainty_yaml)
    pretty = ", ".join(f"{k}={v:.4g}" for k, v in entry.params.items())
    sha = auto_commit(paths.root, subject=f"Set PSA range on {t['label']}: {distribution}({pretty})",
                      body=f"target: {t['id']}\ncell: {t['cell']}\norigin: {origin}\nsource_id: {source_id}\n"
                           f"reason: {reason}", paths=[paths.parameter_uncertainty_yaml])
    return entry, sha


def clear_range(model_type: str, target: str, *, quantity: str | None = None, strategy: str | None = None,
                root: Path | None = None) -> str:
    paths = require_project(root)
    t = _target(model_type, target, quantity, strategy, paths)
    s = unc.load(paths)
    kept = [e for e in s.entries if not (e.target_id == t["id"] and e.parameter_cell_id == t["cell"])]
    if len(kept) == len(s.entries):
        raise ValueError(f"{t['label']} has no range to clear")
    s.entries = kept
    dump_model(s, paths.parameter_uncertainty_yaml)
    return auto_commit(paths.root, subject=f"Clear PSA range on {t['label']}",
                       paths=[paths.parameter_uncertainty_yaml])


def ranges(model_type: str, paths) -> list[ParameterUncertainty]:
    """This type's PSA ranges."""
    return [e for e in unc.load(paths).entries
            if (e.parameter_cell_id or "").startswith(f"{model_type}:") and e.distribution != "unknown"]


def describe_cell(cell: str) -> tuple[str, str | None]:
    """(quantity, strategy id or None) from a stored cell."""
    parts = cell.split(":", 2)
    return parts[1], (parts[2] if len(parts) == 3 else None)


# ── sampling ─────────────────────────────────────────────────────────


def _draws(scalar: dict[str, ParameterUncertainty], sets: dict[str, tuple[ParameterUncertainty, list[float]]],
           runs: int, seed: int, sampling: str) -> list[dict[str, Any]]:
    """``runs`` joint draws: a value for every scalar range, a probability vector for every Dirichlet one."""
    base = smp.sample(scalar, runs, seed=seed, method=sampling) if scalar else [{} for _ in range(runs)]
    rng = random.Random(seed + 7919)
    out = []
    for d in base:
        d = dict(d)
        for k in sorted(sets):
            e, probs = sets[k]
            d[k] = smp.dirichlet(rng, probs, e.params["n"])
        out.append(d)
    return out


def _summary(values, point: float | None) -> dict[str, Any]:
    s = sorted(float(v) for v in values)
    mean = math.fsum(s) / len(s)
    return {"point": point, "mean": mean, "p5": smp.percentile(s, 5), "p50": smp.percentile(s, 50),
            "p95": smp.percentile(s, 95), "min": s[0], "max": s[-1]}


def _check_runs(runs: int) -> None:
    if not 10 <= runs <= MAX_RUNS:
        raise ValueError(f"runs must be between 10 and {MAX_RUNS}")


def _driver(label: str, e: ParameterUncertainty, point: float | None, column: list[float],
            target: list[float]) -> dict[str, Any]:
    if e.distribution == "dirichlet":
        lo, hi = smp.percentile(sorted(column), 5), smp.percentile(sorted(column), 95)
    else:
        lo, hi = smp.Sampler(e).quantile(0.05), smp.Sampler(e).quantile(0.95)
    return {"input": label, "point": point, "distribution": e.distribution, "params": dict(e.params),
            "reason": e.reason, "origin": e.origin, "source": e.source_id,
            "weak": e.verification != "human-verified" or e.contested, "p5": lo, "p95": hi,
            "spearman": smp.spearman(column, target)}


# ── decision tree ────────────────────────────────────────────────────


def _dt_inputs(t, rs: list[ParameterUncertainty]):
    """Map ranges onto the tree: scalar ranges by key, Dirichlet ranges by key, and how to apply a draw."""
    from latris.operations import decision_tree as dt

    groups, nodes, _ = dt._groups(t)
    group_of = {n: u for u, ns in nodes.items() for n in ns}
    parent = {e: n for n, kids in t.children.items() for e, _ in kids}
    scalar: dict[str, ParameterUncertainty] = {}
    sets: dict[str, tuple[ParameterUncertainty, list[float]]] = {}
    labels: dict[str, str] = {}
    points: dict[str, float | None] = {}
    claimed: dict[str, str] = {}  # uncertainty → key already ranging it

    def siblings(n: str) -> list[str]:
        return nodes[group_of[n]] if n in group_of else [n]

    def claim(n: str, key: str) -> None:
        u = group_of.get(n, n)
        if u in claimed:
            raise ValueError(f"{t.uncertainty.get(n, t.labels[n])} has more than one probability range; give it "
                             "one (on one of its chance nodes)")
        claimed[u] = key

    for e in sorted(rs, key=lambda x: (x.parameter_cell_id or "", x.target_id)):
        q = describe_cell(e.parameter_cell_id or "")[0]
        key = f"{e.target_id}|{e.parameter_cell_id}"
        if q == "payoff" and e.target_id in t.payoffs:
            scalar[key] = e
            labels[key], points[key] = f"{t.labels[e.target_id]} (payoff)", t.payoffs[e.target_id].value
        elif q == "value" and e.target_id in parent and e.target_id in t.branches:
            n = parent[e.target_id]
            child = dict(t.children[n])[e.target_id]
            scalar[key] = e
            labels[key] = f"{t.labels[n]} → {t.branch_label(e.target_id, child)} (value)"
            points[key] = t.branches[e.target_id].value
        elif q == "probability" and e.target_id in parent and len(t.children[parent[e.target_id]]) == 2:
            n = parent[e.target_id]
            claim(n, key)
            child = dict(t.children[n])[e.target_id]
            scalar[key] = e
            labels[key] = f"P({t.uncertainty[n]} = {t.branch_label(e.target_id, child)})"
            points[key] = t.branches[e.target_id].probability
        elif q == "probabilities" and t.kind.get(e.target_id) == "chance":
            claim(e.target_id, key)
            kids = t.children[e.target_id]
            sets[key] = (e, [t.branches[x].probability or 0.0 for x, _ in kids])
            labels[key] = f"{t.uncertainty[e.target_id]} (branch probabilities)"
            points[key] = None

    def apply(d: dict[str, Any]):
        payoffs = dict(t.payoffs)
        branches = dict(t.branches)
        for key, v in d.items():
            target, cell = key.split("|", 1)
            q = describe_cell(cell)[0]
            if q == "payoff":
                payoffs[target] = payoffs[target].model_copy(update={"value": v})
            elif q == "value":
                branches[target] = branches[target].model_copy(update={"value": v})
            else:
                n = target if q == "probabilities" else parent[target]
                if q == "probabilities":
                    by_label = {t.branch_label(x, c): p for (x, c), p in zip(t.children[n], v, strict=True)}
                else:
                    chosen = t.branch_label(target, dict(t.children[n])[target])
                    p = min(max(v, 0.0), 1.0)
                    by_label = {t.branch_label(x, c): (p if t.branch_label(x, c) == chosen else 1.0 - p)
                                for x, c in t.children[n]}
                for s in siblings(n):
                    for x, c in t.children[s]:
                        lab = t.branch_label(x, c)
                        if lab in by_label:
                            branches[x] = branches[x].model_copy(update={"probability": by_label[lab]})
        return replace(t, payoffs=payoffs, branches=branches)

    return scalar, sets, labels, points, apply


def _dt_options(t, ev: dict[str, float]) -> dict[str, float]:
    if t.kind[t.root] != "decision":
        return {t.labels[t.root]: ev[t.root]}
    return {t.branch_label(e, c): (t.branches[e].value if e in t.branches else 0.0) + ev[c]
            for e, c in t.children[t.root]}


def _dt_fixed(t, used: set[str]) -> list[str]:
    out = []
    for n, k in t.kind.items():
        if k == "terminal" and f"{n}|decision_tree:payoff" not in used:
            out.append(f"{t.labels[n]} (payoff)")
    return sorted(out)


def dt_psa(*, runs: int = 2000, seed: int = 1234, sampling: str = "lhs",
           root: Path | None = None) -> dict[str, Any]:
    """Sample every decision-tree input with a range; each option's expected value, how often it's best, EVPI."""
    from latris.operations import decision_tree as dt

    _check_runs(runs)
    paths = require_project(root)
    t = dt.load_tree(root=paths.root)
    if t.problems:
        raise ValueError("the decision tree is incomplete; `latris dt check` lists what's missing")
    scalar, sets, labels, points, apply = _dt_inputs(t, ranges("decision_tree", paths))
    if not scalar and not sets:
        raise ValueError("no input has a range yet; give some a distribution first "
                         "(e.g. `latris dt range 'Launched, high demand' normal --mean 500 --sd 100`)")
    sign = t.sign
    point = _dt_options(t, dt.rollback(t)[0])
    draws = _draws(scalar, sets, runs, seed, sampling)
    values: dict[str, list[float]] = {o: [] for o in point}
    best_count = dict.fromkeys(point, 0)
    for d in draws:
        opts = _dt_options(t, dt.rollback(apply(d))[0])
        for o, v in opts.items():
            values[o].append(v)
        best_count[max(opts, key=lambda o: (sign * opts[o], -list(opts).index(o)))] += 1
    means = {o: math.fsum(v) / runs for o, v in values.items()}
    order = sorted(point, key=lambda o: (-sign * means[o], list(point).index(o)))
    best = order[0]
    point_best = max(point, key=lambda o: (sign * point[o], -list(point).index(o)))
    per_run_best = [max(sign * values[o][i] for o in point) for i in range(runs)]
    evpi = max(0.0, math.fsum(per_run_best) / runs - sign * means[best])
    outputs = []
    for o in order:
        row = {"output": o, **_summary(values[o], point[o]), "p_best": best_count[o] / runs}
        row["mean_over_point"] = (row["mean"] / point[o] if point[o] > 0
                                  else 1.0 if point[o] == 0 and row["mean"] == 0 else None)
        outputs.append(row)
    if len(order) > 1:
        rival = order[1]
        target = [values[best][i] - values[rival][i] for i in range(runs)]
        driver_target = f"advantage of {best} over {rival}"
    else:
        rival = None
        target = values[best]
        driver_target = f"expected value of {best}"
    drivers = []
    for key in sorted(scalar, key=lambda k: labels[k]):
        drivers.append(_driver(labels[key], scalar[key], points[key], [d[key] for d in draws], target))
    for key in sorted(sets, key=lambda k: labels[k]):
        e, _ = sets[key]
        kids = t.children[key.split("|", 1)[0]]
        for i, (x, c) in enumerate(kids[:-1] if len(kids) == 2 else kids):
            n = key.split("|", 1)[0]
            drivers.append(_driver(f"P({t.uncertainty[n]} = {t.branch_label(x, c)})", e, t.branches[x].probability,
                                   [d[key][i] for d in draws], target))
    drivers.sort(key=lambda r: -abs(r["spearman"] or 0))
    return {
        "model_type": "decision_tree", "quantity": "expected value", "objective": t.settings.objective,
        "units": t.settings.units,
        "runs": runs, "seed": seed, "sampling": sampling, "decision": t.labels[t.root],
        "primary": best, "best": best, "point_best": point_best, "rival": rival,
        "p_best": best_count[best] / runs, "evpi": evpi, "outputs": outputs,
        "driver_target": driver_target, "drivers": drivers,
        "fixed": _dt_fixed(t, set(scalar)),
    }


# ── Markov ───────────────────────────────────────────────────────────


def _mk_inputs(m, rs: list[ParameterUncertainty]):
    scalar: dict[str, ParameterUncertainty] = {}
    sets: dict[str, tuple[ParameterUncertainty, list[float]]] = {}
    labels: dict[str, str] = {}
    points: dict[str, float | None] = {}
    leaving: dict[str, list[str]] = {}  # key → the edges out, in the Dirichlet's order (stay last)
    for e in sorted(rs, key=lambda x: (x.parameter_cell_id or "", x.target_id)):
        q, sid = describe_cell(e.parameter_cell_id or "")
        if sid is not None and sid not in m.strategies:
            continue
        who = f" under {m.labels[sid]}" if sid else ""
        key = f"{e.target_id}|{e.parameter_cell_id}"
        if q == "transition" and (e.target_id, sid) in m.transitions:
            a, b = m.edges[e.target_id]
            scalar[key] = e
            labels[key] = f"P({m.labels[a]} → {m.labels[b]}){who}"
            points[key] = m.transitions[(e.target_id, sid)].probability
        elif q in ("cost", "utility") and (e.target_id, sid) in m.rewards \
                and getattr(m.rewards[(e.target_id, sid)], q) is not None:
            scalar[key] = e
            labels[key] = f"{m.labels[e.target_id]} {q}{who}"
            points[key] = getattr(m.rewards[(e.target_id, sid)], q)
        elif q == "leaving" and e.target_id in m.states:
            out = sorted((x for x, (a, _) in m.edges.items() if a == e.target_id and m.prob(x, sid)),
                         key=lambda x: m.labels[m.edges[x][1]])
            if not out:
                continue
            ps = [m.prob(x, sid).probability for x in out]  # type: ignore[union-attr]
            sets[key] = (e, [*ps, max(0.0, 1.0 - sum(ps))])
            leaving[key] = out
            labels[key] = f"Leaving {m.labels[e.target_id]}{who}"
            points[key] = None
    for key in sets:
        sid = describe_cell(key.split("|", 1)[1])[1]
        for x in leaving[key]:
            clash = f"{x}|markov:transition" + (f":{sid}" if sid else "")
            if clash in scalar:
                raise ValueError(f"{labels[clash]} has a range of its own and is also in {labels[key]}'s Dirichlet; "
                                 "keep one")

    def apply(d: dict[str, Any]):
        transitions = dict(m.transitions)
        rewards = dict(m.rewards)
        for key, v in d.items():
            target, cell = key.split("|", 1)
            q, sid = describe_cell(cell)
            if q == "transition":
                transitions[(target, sid)] = transitions[(target, sid)].model_copy(
                    update={"probability": min(max(v, 0.0), 1.0)})
            elif q in ("cost", "utility"):
                rewards[(target, sid)] = rewards[(target, sid)].model_copy(update={q: v})
            else:
                for x, p in zip(leaving[key], v, strict=False):
                    cur = transitions.get((x, sid)) or transitions[(x, None)]
                    transitions[(x, sid)] = cur.model_copy(update={"probability": p, "strategy": sid})
        return replace(m, transitions=transitions, rewards=rewards)

    return scalar, sets, labels, points, leaving, apply


def _nice_ceiling(x: float) -> float:
    if x <= 0:
        return 1.0
    mag = 10 ** math.floor(math.log10(x))
    for step in (1, 2, 2.5, 5, 10):
        if step * mag >= x:
            return step * mag
    return 10 * mag


def _wtp_grid(wtp: float | None, icers: list[float]) -> list[float]:
    top = max([2 * wtp if wtp else 0.0] + [2 * i for i in icers if i and i > 0])
    top = _nice_ceiling(top if top > 0 else 100_000.0)
    return [top * i / (CEAC_POINTS - 1) for i in range(CEAC_POINTS)]


def markov_psa(*, runs: int = 1000, seed: int = 1234, sampling: str = "lhs",
               root: Path | None = None) -> dict[str, Any]:
    """Sample every Markov input with a range; costs and outcomes per strategy, the CEAC and the EVPI."""
    import numpy as np

    from latris.operations import markov

    _check_runs(runs)
    paths = require_project(root)
    m = markov.load(root=paths.root)
    if m.problems:
        raise ValueError("the Markov model is incomplete; `latris markov check` lists what's missing")
    scalar, sets, labels, points, leaving, apply = _mk_inputs(m, ranges("markov", paths))
    if not scalar and not sets:
        raise ValueError("no input has a range yet; give some a distribution first "
                         "(e.g. `latris markov range 'Healthy -> Sick' beta --mean 0.1 --sd 0.02`)")
    s = m.settings
    strategies = m.strategy_names()
    names = [m.labels[x] if x else markov.BASE_CASE for x in strategies]
    point = {n: markov.totals(m, x)[:2] for n, x in zip(names, strategies, strict=True)}
    draws = _draws(scalar, sets, runs, seed, sampling)
    cost = np.zeros((runs, len(strategies)))
    out = np.zeros((runs, len(strategies)))
    rescaled = 0
    for i, d in enumerate(draws):
        mi = apply(d)
        hit = False
        for j, x in enumerate(strategies):
            cost[i, j], out[i, j], r = markov.totals(mi, x, rescale=True)
            hit = hit or r
        rescaled += hit
    results = [{"strategy": n, "cost": float(cost[:, j].mean()), "outcome": float(out[:, j].mean())}
               for j, n in enumerate(names)]
    rows = markov.incremental(results) if len(names) > 1 else []
    grid = _wtp_grid(s.wtp, [r["icer"] for r in rows if r["icer"] is not None])
    ceac = {"wtp": grid, "strategies": names, "p": [[] for _ in names], "frontier": [], "evpi": []}
    for w in grid:
        nmb = w * out - cost
        win = nmb.argmax(axis=1)
        for j in range(len(names)):
            ceac["p"][j].append(float((win == j).mean()))
        mean_nmb = nmb.mean(axis=0)
        ceac["frontier"].append(names[int(mean_nmb.argmax())])
        ceac["evpi"].append(float(nmb.max(axis=1).mean() - mean_nmb.max()))
    strat_rows = []
    for j, n in enumerate(names):
        row = {"strategy": n, "cost": _summary(cost[:, j], point[n][0]), "outcome": _summary(out[:, j], point[n][1])}
        if s.wtp is not None:
            row["nmb"] = _summary(s.wtp * out[:, j] - cost[:, j], s.wtp * point[n][1] - point[n][0])
        strat_rows.append(row)
    payload: dict[str, Any] = {
        "model_type": "markov", "runs": runs, "seed": seed, "sampling": sampling,
        "cost_units": s.cost_units, "outcome_units": s.outcome_units, "wtp": s.wtp,
        "strategies": strat_rows, "incremental": rows, "ceac": ceac, "rescaled_runs": rescaled,
    }
    # What drives the decision: incremental net benefit at the willingness to pay, else incremental outcome.
    target: Any
    if len(names) > 1 and s.wtp is not None:
        nmb = s.wtp * out - cost
        means = nmb.mean(axis=0)
        order = list(np.argsort(-means, kind="stable"))
        a, b = int(order[0]), int(order[1])
        win = nmb.argmax(axis=1)
        payload.update(choice=names[a], rival=names[b], p_cost_effective=float((win == a).mean()),
                       evpi=float(nmb.max(axis=1).mean() - means.max()))
        target = nmb[:, a] - nmb[:, b]
        driver_target = f"net monetary benefit of {names[a]} over {names[b]}"
    elif len(names) > 1:
        a = int(np.argmax(out.mean(axis=0)))
        b = int(np.argmin(out.mean(axis=0)))
        target = out[:, a] - out[:, b] if a != b else out[:, a]
        driver_target = f"{s.outcome_units or 'outcome'} gained by {names[a]} over {names[b]}"
    else:
        target = out[:, 0]
        driver_target = f"{s.outcome_units or 'outcome'} of {names[0]}"
    tlist = [float(v) for v in target]
    drivers = [_driver(labels[k], scalar[k], points[k], [d[k] for d in draws], tlist)
               for k in sorted(scalar, key=lambda k: labels[k])]
    for k in sorted(sets, key=lambda k: labels[k]):
        e, _ = sets[k]
        sid = describe_cell(k.split("|", 1)[1])[1]
        who = f" under {m.labels[sid]}" if sid else ""
        for i, x in enumerate(leaving[k]):
            a_, b_ = m.edges[x]
            drivers.append(_driver(f"P({m.labels[a_]} → {m.labels[b_]}){who}", e,
                                   m.prob(x, sid).probability,  # type: ignore[union-attr]
                                   [d[k][i] for d in draws], tlist))
    drivers.sort(key=lambda r: -abs(r["spearman"] or 0))
    used = {(k.split("|", 1)[0], describe_cell(k.split("|", 1)[1])[1]) for k in scalar
            if describe_cell(k.split("|", 1)[1])[0] == "transition"}
    used |= {(x, describe_cell(k.split("|", 1)[1])[1]) for k in sets for x in leaving[k]}
    fixed = sorted(f"P({m.labels[m.edges[e][0]]} → {m.labels[m.edges[e][1]]})"
                   + (f" under {m.labels[sid]}" if sid else "")
                   for (e, sid) in m.transitions if (e, sid) not in used)
    fixed += sorted(f"{m.labels[st]} {q}" + (f" under {m.labels[sid]}" if sid else "")
                    for (st, sid), r in m.rewards.items() for q in ("cost", "utility")
                    if getattr(r, q) is not None and f"{st}|{_cell('markov', q, sid)}" not in scalar)
    payload.update(driver_target=driver_target, drivers=drivers, fixed=fixed)
    return payload


# ── describing and recording ─────────────────────────────────────────


def _g(x: float | None) -> str:
    return "—" if x is None else f"{x:,.4g}"


def money(x: float | None, units: str | None) -> str:
    from latris.operations.markov import _money

    return "—" if x is None else _money(x, units)


def describe(p: dict[str, Any]) -> str:
    if p["model_type"] == "decision_tree":
        from latris.operations.decision_tree import fmt

        u = p["units"]
        main = next(o for o in p["outputs"] if o["output"] == p["best"])
        s = (f"Over {p['runs']} runs, {p['best']} has the best expected value (mean {fmt(main['mean'], u)}, 90% "
             f"between {fmt(main['p5'], u)} and {fmt(main['p95'], u)}) and is best in {p['p_best']:.0%} of them")
        if p["point_best"] != p["best"]:
            s += f"; on the point values {p['point_best']} is best instead"
        s += f"; removing all the parameter uncertainty before choosing is worth up to {fmt(p['evpi'], u)}"
    else:
        cu, ou = p["cost_units"], p["outcome_units"] or "outcome unit"
        if p.get("choice"):
            s = (f"At {money(p['wtp'], cu)} per {ou}, {p['choice']} is the most cost-effective in "
                 f"{p['p_cost_effective']:.0%} of {p['runs']} runs; the expected value of perfect information is "
                 f"{money(p['evpi'], cu)} per person")
        else:
            st = p["strategies"][0]
            s = (f"Over {p['runs']} runs, {st['strategy']}: cost {money(st['cost']['mean'], cu)} (90% "
                 f"{money(st['cost']['p5'], cu)}–{money(st['cost']['p95'], cu)}), {st['outcome']['mean']:.3f} {ou} "
                 f"(90% {st['outcome']['p5']:.3f}–{st['outcome']['p95']:.3f})")
        for r in p["incremental"]:
            if r["icer"] is not None:
                s += f"; probabilistic ICER of {r['strategy']} vs {r['versus']} {money(r['icer'], cu)} per {ou}"
    top = p["drivers"][0] if p["drivers"] else None
    if top and top["spearman"] is not None:
        s += f"; the {p['driver_target']} depends most on {top['input']} (rank correlation {top['spearman']:+.2f})"
    return s


def run(model_type: str, *, runs: int | None = None, seed: int | None = None, sampling: str | None = None,
        root: Path | None = None) -> dict[str, Any]:
    fn = {"decision_tree": dt_psa, "markov": markov_psa}.get(model_type)
    if fn is None:
        raise ValueError(f"probabilistic sensitivity analysis here is for {', '.join(MODEL_TYPES)}")
    kw: dict[str, Any] = {"seed": 1234 if seed is None else seed, "sampling": sampling or "lhs", "root": root}
    if runs is not None:
        kw["runs"] = runs
    return fn(**kw)


def record(payload: dict[str, Any], *, root: Path | None = None) -> tuple[str, str]:
    from latris.operations.analysis_results import record_result

    mt = payload["model_type"]
    if mt == "decision_tree":
        main = next(o for o in payload["outputs"] if o["output"] == payload["best"])
        metrics = {"best": payload["best"], "p_best": payload["p_best"], "evpi": payload["evpi"],
                   "mean": main["mean"], "p5": main["p5"], "p95": main["p95"]}
        algorithm = "Monte Carlo rollback of the decision tree; EVPI over the parameters; Spearman rank correlation"
    else:
        metrics = {"choice": payload.get("choice"), "p_cost_effective": payload.get("p_cost_effective"),
                   "evpi": payload.get("evpi")}
        algorithm = ("Monte Carlo through the cohort model; incremental analysis on the means; cost-effectiveness "
                     "acceptability curve and EVPI over a willingness-to-pay grid; Spearman rank correlation")
    sha, r = record_result(
        kind=KINDS[mt],
        key=KINDS[mt],
        payload=payload,
        purpose="sensitivity-analysis",
        algorithm=f"{algorithm} ({'Latin hypercube' if payload['sampling'] == 'lhs' else 'random'} sampling)",
        library_version="latris",
        summary=describe(payload),
        model_type=mt,
        hyperparameters={"runs": payload["runs"], "sampling": payload["sampling"]},
        uncertainty=True,
        seed=payload["seed"],
        metrics=metrics,
        commit_subject=f"Analysis: probabilistic sensitivity analysis of the {mt.replace('_', ' ')}",
        root=root,
    )
    return sha, r.id
