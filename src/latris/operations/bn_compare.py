"""Comparing BN options: the baseline network and each saved scenario, on the same draws of the tables.

Each arm is the network with a scenario's table overrides and settings applied, asked the same
question: P(target = state | the arm's evidence and the evidence given for every arm). With no table
uncertainty this is a comparison of point probabilities. When tables carry an uncertainty ("worth n
observations"), every arm is asked on the SAME draws of the uncertain tables (common random numbers:
a draw samples the shared tables once, then each arm applies its own overrides on top), so the
difference between two options is measured draw by draw — as ``sd compare`` does for simulations.

Every row names its reference: an option that ``extends`` a compared option is measured against it,
every other one against the baseline (the network with no scenario changes), unless one reference is
given for all (``operations/_compare.py``).
"""

from __future__ import annotations

import random
import time
from typing import Any

from latris.operations import _bn_engine
from latris.operations._compare import arm_label, references, share_text
from latris.operations._sampling import percentile
from latris.operations.bn_inference import applied_likelihood
from latris.operations.bn_montecarlo import draw_tables, sampled_tables
from latris.schema.attributes import ParameterUncertainty
from latris.schema.bn import CPTEntry, NoisyOrEntry

MAX_RUNS = 2000


def _r(x: float) -> float:
    return round(x, 6)


def compare_options(
    state_spaces: dict[str, list[str]],
    cpts: dict[str, CPTEntry],
    noisy: dict[str, NoisyOrEntry],
    specs: dict[str, dict[str, ParameterUncertainty]],
    arms: list[Any],
    target: str,
    *,
    state: str | None = None,
    runs: int = 500,
    seed: int = 1234,
    reference: str | None = None,
    max_seconds: float = 60.0,
    labels: dict[str, str] | None = None,
    intervene: Any = None,
) -> dict[str, Any]:
    """Compare P(target = state) across the baseline and each arm.

    ``arms`` are ``bn.ScenarioApplied`` (the baseline first, ``name=None``): their tables have the
    scenario's overrides applied and their evidence includes the evidence given for every arm.
    ``intervene(tables, interventions)`` applies the do-operator. ``runs=0`` compares point values only.
    """
    labels = labels or {}
    if target not in cpts:
        raise ValueError(f"{labels.get(target, target)!r} is not in the network")
    states = state_spaces[target]
    focus = state or states[0]
    if focus not in states:
        raise ValueError(f"{focus!r} is not a state of {labels.get(target, target)} (states: {', '.join(states)})")
    if runs and not 2 <= runs <= MAX_RUNS:
        raise ValueError(f"runs must be 0 (point values only) or between 2 and {MAX_RUNS}")
    options = [a for a in arms if a.name]
    if not options:
        raise ValueError("name at least one saved BN scenario to compare with the baseline")
    for a in arms:
        if target in a.evidence or target in a.interventions:
            what = "observes" if target in a.evidence else "sets"
            who = a.name or "the evidence given for every option"
            raise ValueError(f"{who} {what} {labels.get(target, target)}, so there's nothing to compare on it")

    class _Opt:  # what the shared reference rules read
        def __init__(self, name: str, extends: str | None) -> None:
            self.name, self.extends = name, extends

    refs, warnings, reference = references([_Opt(a.name, a.extends) for a in options], reference)

    def ask(arm: Any, tables: dict[str, CPTEntry]) -> float:
        if arm.overrides:
            from latris.operations.bn_scenarios import apply_tables

            tables, _ = apply_tables(tables, arm.overrides, labels)
        if arm.interventions:
            tables = intervene(tables, arm.interventions)
        network = _bn_engine.build_network(state_spaces, tables)
        soft = {k: dict(v) for k, v in arm.soft.items()}
        applied = applied_likelihood(network, state_spaces, arm.evidence, soft, dict(arm.likelihood))
        return _bn_engine.query_marginals(network, [target], arm.evidence, likelihood=applied or None)[target][focus]

    names = ["baseline", *(a.name for a in options)]
    point = {n: ask(a, cpts) for n, a in zip(names, arms, strict=True)}
    uncertain = sampled_tables(specs, cpts, noisy) if runs else {}
    per_arm: dict[str, list[float]] = {n: [] for n in names}
    started = time.perf_counter()
    if uncertain:
        rng = random.Random(seed)
        order = sorted(uncertain)
        for i in range(runs):
            if i == 1:
                estimate = (time.perf_counter() - started) * runs
                if estimate > max_seconds:
                    raise ValueError(
                        f"{runs} draws × {len(arms)} options would take about {estimate:.0f} s "
                        f"(limit {max_seconds:g} s); use fewer runs"
                    )
            drawn = draw_tables(rng, state_spaces, cpts, noisy, uncertain, order)
            for n, a in zip(names, arms, strict=True):
                per_arm[n].append(ask(a, drawn))

    def spread(xs: list[float]) -> dict[str, float]:
        ys = sorted(xs)
        return {"p2.5": _r(percentile(ys, 2.5)), "p50": _r(percentile(ys, 50)), "p97.5": _r(percentile(ys, 97.5)),
                "mean": _r(sum(ys) / len(ys))}

    def paired(n: str, ref: str) -> dict[str, float]:
        out: dict[str, float] = {"point": _r(point[n] - point[ref])}
        if per_arm[n]:
            diffs = [x - b for x, b in zip(per_arm[n], per_arm[ref], strict=True)]
            out |= spread(diffs)
            out["share_lower"] = _r(sum(d < -1e-12 for d in diffs) / len(diffs))
            out["share_higher"] = _r(sum(d > 1e-12 for d in diffs) / len(diffs))
        return out

    rows = []
    for n, a in zip(names, arms, strict=True):
        row: dict[str, Any] = {"name": n, "point": _r(point[n])}
        if per_arm[n]:
            row |= spread(per_arm[n])
        ref = refs.get(n)
        if ref is not None:
            row["reference"] = ref
            row["difference"] = paired(n, ref)
            if ref != "baseline":
                row["vs_baseline"] = paired(n, "baseline")
        if a.extends:
            row["extends"] = a.extends
        if a.changes:
            row["changes"] = a.changes
        rows.append(row)
    base = arms[0]
    return {
        "target": target,
        "focus_state": focus,
        "label": labels.get(target, target),
        "options": rows,
        "scenarios": [a.name for a in options],
        "reference": reference,
        "warnings": warnings,
        "evidence": base.evidence,
        "soft": base.soft,
        "likelihood": base.likelihood,
        "interventions": base.interventions,
        "runs": runs if uncertain else 0,
        "seed": seed,
        "uncertain": sorted(labels.get(k, k) for k in uncertain),
        "labels": {k: labels.get(k, k) for k in {target, *base.evidence, *base.soft, *base.likelihood,
                                                 *base.interventions}},
        "seconds": round(time.perf_counter() - started, 3),
    }


def _pts(x: float) -> str:
    return f"{abs(x) * 100:.3g} points"


def describe_option(p: dict[str, Any], row: dict[str, Any]) -> str:
    """One self-contained claim, e.g. 'Barrier upgraded — P(Toxic bloom = yes): 8% (95% of draws 3%–15%);
    vs the baseline (no scenario changes): 4 points lower (95% of draws: -7.1 to -1.2 points), lower in
    99% of draws, higher in 1%; given Hot week = yes'."""
    from latris.operations.bn import evidence_description

    name = "Baseline (no scenario changes)" if row["name"] == "baseline" else row["name"]
    head = f"{name} — P({p['label']} = {p['focus_state']}): {row['point']:.1%}"
    if "p2.5" in row:
        head += f" (95% of draws {row['p2.5']:.1%}–{row['p97.5']:.1%})"
    d = row.get("difference")
    if d:
        word = "lower" if d["point"] < 0 else "higher" if d["point"] > 0 else "no different"
        size = f"{_pts(d['point'])} {word}" if d["point"] else "no different"
        head += f"; vs {arm_label(row.get('reference', 'baseline'))}: {size}"
        if "p2.5" in d:
            head += (f" (95% of draws: {d['p2.5'] * 100:+.3g} to {d['p97.5'] * 100:+.3g} points), "
                     f"{share_text(d)}")
        b = row.get("vs_baseline")
        if b:
            bword = "lower" if b["point"] < 0 else "higher" if b["point"] > 0 else "no different"
            head += f"; vs the baseline: {_pts(b['point'])} {bword}"
    labels = p.get("labels", {})
    given = evidence_description(p.get("evidence", {}), p.get("soft"), p.get("likelihood"), labels)
    do = p.get("interventions") or {}
    if do:
        set_text = "set " + ", ".join(f"{labels.get(k, k)} = {v}" for k, v in sorted(do.items()))
        given = f"{set_text}; {given}" if given else set_text
    if given:
        head += f"; given {given}"
    return head
