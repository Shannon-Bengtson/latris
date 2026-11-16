"""Markov cohort models — a cohort moving between states over time, and what each strategy costs and buys.

The discrete-time cohort Markov model of decision-analytic modelling
(Sonnenberg & Beck 1993; Briggs, Claxton & Sculpher 2006): a cohort starts
spread over **states**; each **cycle**, a share of each state moves along each
**transition** and the rest stays. Each state has a **cost** per cycle and a
**utility** weight (per year — e.g. quality of life), so a strategy's
discounted totals are its expected cost and outcome (e.g. QALYs) per person.

**Strategies** (standard care, a new drug) share the model and differ where
they override a transition probability or a state's cost or utility. With
two or more, the analysis is the standard **incremental cost-effectiveness
analysis** (Drummond et al. 2015): strategies ordered by cost; those both
dearer and no more effective than another are **dominated**; those whose
ICER exceeds the next one's are **extendedly dominated**; the rest form the
frontier, each with its **ICER** against the previous. With a willingness to
pay per unit of outcome, the **net monetary benefit** names the strategy to
choose — and each ICER is itself the threshold at which the choice changes.

Counting: with half-cycle correction, each cycle counts the average of the
cohort at its start and end (the trapezoid rule) and is discounted at its
midpoint; without, the cohort at the cycle's start, discounted at its start.
Outcomes accrue utility × cycle length in years.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from latris.operations._resolve import resolve_target
from latris.operations.commit import auto_commit
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_model, load_model
from latris.schema import Substrate
from latris.schema.common import ProvenanceOrigin, ProvenanceVerification
from latris.schema.markov import (
    MARKOV_ELEMENTS,
    MarkovRewardEntry,
    MarkovRewardSet,
    MarkovStartEntry,
    MarkovStartSet,
    MarkovTransitionEntry,
    MarkovTransitionSet,
)
from latris.schema.settings import MarkovSettings

MODEL_TYPE = "markov"
BASE_CASE = "Base case"
YEARS = {"days": 1 / 365.25, "weeks": 7 / 365.25, "months": 1 / 12, "years": 1.0}
MAX_TRACE_ROWS = 201
_TOL = 1e-9
_UNSET = object()


def _path(paths, attr: str) -> Path:
    return paths.view_attribute_path(MODEL_TYPE, attr)


def _load(path: Path, cls):
    return load_model(cls, path) if path.exists() else cls()


def _dump(path: Path, store) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    dump_model(store, path)


def get_elements(*, root: Path | None = None) -> dict[str, str]:
    from latris.schema.roles import RoleSet

    paths = require_project(root)
    p = paths.role_path(MODEL_TYPE)
    if not p.exists():
        return {}
    return {e.target_id: e.value for e in load_model(RoleSet, p).entries if e.value in MARKOV_ELEMENTS}


def get_transitions(*, root: Path | None = None) -> MarkovTransitionSet:
    return _load(_path(require_project(root), "transition"), MarkovTransitionSet)


def get_rewards(*, root: Path | None = None) -> MarkovRewardSet:
    return _load(_path(require_project(root), "reward"), MarkovRewardSet)


def get_start(*, root: Path | None = None) -> MarkovStartSet:
    return _load(_path(require_project(root), "start"), MarkovStartSet)


def get_settings(*, root: Path | None = None) -> MarkovSettings:
    return _load(_path(require_project(root), "settings"), MarkovSettings)


# ── writes ───────────────────────────────────────────────────────────


def _entity(paths, target: str, element: str) -> tuple[str, str]:
    sub = load_model(Substrate, paths.conceptual_yaml)
    tid = resolve_target(target, sub)
    label = next((e.label for e in sub.entities if e.id == tid), None)
    if label is None:
        raise ValueError(f"{target!r} is a link, not a {element}")
    if get_elements(root=paths.root).get(tid) != element:
        raise ValueError(f"{label} is not a {element} (`latris markov element <factor> {element}`)")
    return tid, label


def _strategy(paths, strategy: str | None) -> str | None:
    return _entity(paths, strategy, "strategy")[0] if strategy else None


def set_element(target: str, element: str, *, root: Path | None = None) -> tuple[str, str]:
    from latris.operations.view_roles import set_role

    if element not in MARKOV_ELEMENTS:
        raise ValueError(f"{element!r} is not a Markov element. Elements: {', '.join(MARKOV_ELEMENTS)}")
    return set_role(target, MODEL_TYPE, element, root=root)


def set_transition(
    link: str,
    probability: float,
    *,
    strategy: str | None = None,
    origin: ProvenanceOrigin = "human-direct",
    source_id: str | None = None,
    verification: ProvenanceVerification = "unverified",
    notes: str | None = None,
    root: Path | None = None,
) -> tuple[MarkovTransitionEntry, str]:
    """Set the per-cycle probability of moving along a link between two states (for every strategy, or one)."""
    paths = require_project(root)
    sub = load_model(Substrate, paths.conceptual_yaml)
    eid = resolve_target(link, sub)
    e = next((x for x in sub.edges if x.id == eid), None)
    if e is None:
        raise ValueError(f"{link!r} is a factor; a transition is a link, written 'From state -> To state'")
    el = get_elements(root=paths.root)
    if el.get(e.from_id) != "state" or el.get(e.to_id) != "state":
        raise ValueError("a transition runs between two states (`latris markov element <factor> state`)")
    sid = _strategy(paths, strategy)
    entry = MarkovTransitionEntry(target_id=eid, strategy=sid, probability=probability, origin=origin,
                                  source_id=source_id, verification=verification, notes=notes)
    store = get_transitions(root=paths.root)
    store.entries = [x for x in store.entries if (x.target_id, x.strategy) != (eid, sid)] + [entry]
    p = _path(paths, "transition")
    _dump(p, store)
    labels = {x.id: x.label for x in sub.entities}
    sha = auto_commit(paths.root, subject=f"Set Markov transition {labels[e.from_id]} → {labels[e.to_id]} = "
                                          f"{probability:g}" + (f" ({strategy})" if strategy else ""),
                      body=f"edge: {eid}\nstrategy: {sid}\nprobability: {probability}\norigin: {origin}\n"
                           f"source_id: {source_id}", paths=[p])
    return entry, sha


def set_reward(
    state: str,
    *,
    cost: float | None | object = _UNSET,
    utility: float | None | object = _UNSET,
    strategy: str | None = None,
    notes: str | None | object = _UNSET,
    origin: ProvenanceOrigin | object = _UNSET,
    source_id: str | None | object = _UNSET,
    verification: ProvenanceVerification | object = _UNSET,
    root: Path | None = None,
) -> tuple[MarkovRewardEntry, str]:
    """Set a state's cost per cycle and/or utility per year (for every strategy, or one); only what's given changes."""
    paths = require_project(root)
    tid, label = _entity(paths, state, "state")
    sid = _strategy(paths, strategy)
    store = get_rewards(root=paths.root)
    current = next((x for x in store.entries if (x.target_id, x.strategy) == (tid, sid)), None)
    given = {"cost": cost, "utility": utility, "notes": notes, "origin": origin, "source_id": source_id,
             "verification": verification}
    changed = {k: v for k, v in given.items() if v is not _UNSET}
    if not changed:
        raise ValueError("nothing to set: give a cost, utility, notes or source")
    entry = MarkovRewardEntry.model_validate(
        {**(current.model_dump() if current else {"target_id": tid, "strategy": sid}), **changed})
    store.entries = [x for x in store.entries if (x.target_id, x.strategy) != (tid, sid)] + [entry]
    p = _path(paths, "reward")
    _dump(p, store)
    sha = auto_commit(paths.root, subject=f"Set Markov state {label}: {', '.join(changed)}"
                                          + (f" ({strategy})" if strategy else ""),
                      body=f"state: {tid}\nstrategy: {sid}\n" + "\n".join(f"{k}: {v}" for k, v in changed.items()),
                      paths=[p])
    return entry, sha


def set_start(state: str, proportion: float, *, root: Path | None = None) -> tuple[MarkovStartEntry, str]:
    """Set the share of the cohort that starts in a state."""
    paths = require_project(root)
    tid, label = _entity(paths, state, "state")
    entry = MarkovStartEntry(target_id=tid, proportion=proportion)
    store = get_start(root=paths.root)
    store.entries = [x for x in store.entries if x.target_id != tid] + ([entry] if proportion > 0 else [])
    p = _path(paths, "start")
    _dump(p, store)
    sha = auto_commit(paths.root, subject=f"Markov cohort starts {proportion:g} in {label}", body="", paths=[p])
    return entry, sha


def set_settings(*, root: Path | None = None, **fields: Any) -> tuple[MarkovSettings, str]:
    """Update the cycle length and count, time units, discount rates, half-cycle correction, WTP and units."""
    paths = require_project(root)
    s = MarkovSettings.model_validate({**get_settings(root=paths.root).model_dump(), **fields})
    p = _path(paths, "settings")
    _dump(p, s)
    sha = auto_commit(paths.root, subject="Markov settings: " + ", ".join(f"{k}={v}" for k, v in fields.items()),
                      body="", paths=[p])
    return s, sha


# ── structure ────────────────────────────────────────────────────────


@dataclass
class MKProblem:
    target_id: str | None
    gap_type: str
    message: str


@dataclass
class Model:
    labels: dict[str, str]
    states: list[str]
    strategies: list[str]  # ids; empty: one implicit base case
    edges: dict[str, tuple[str, str]]  # transition edge → (from, to)
    transitions: dict[tuple[str, str | None], MarkovTransitionEntry]  # (edge, strategy)
    rewards: dict[tuple[str, str | None], MarkovRewardEntry]
    start: dict[str, float]
    settings: MarkovSettings
    problems: list[MKProblem] = field(default_factory=list)

    def strategy_names(self) -> list[str | None]:
        return list(self.strategies) or [None]

    def prob(self, edge: str, strategy: str | None) -> MarkovTransitionEntry | None:
        return self.transitions.get((edge, strategy)) or self.transitions.get((edge, None))

    def reward(self, state: str, strategy: str | None, what: str) -> tuple[float | None, MarkovRewardEntry | None]:
        for key in ((state, strategy), (state, None)):
            r = self.rewards.get(key)
            if r is not None and getattr(r, what) is not None:
                return getattr(r, what), r
        return None, None


def load(*, root: Path | None = None) -> Model:
    paths = require_project(root)
    sub = load_model(Substrate, paths.conceptual_yaml)
    labels = {e.id: e.label for e in sub.entities}
    el = {k: v for k, v in get_elements(root=paths.root).items() if k in labels}
    states = sorted((k for k, v in el.items() if v == "state"), key=lambda k: labels[k])
    strategies = sorted((k for k, v in el.items() if v == "strategy"), key=lambda k: labels[k])
    edge_ends = {e.id: (e.from_id, e.to_id) for e in sub.edges}
    m = Model(labels=labels, states=states, strategies=strategies, edges={},
              transitions={}, rewards={}, start={}, settings=get_settings(root=paths.root))
    P = m.problems
    for t in get_transitions(root=paths.root).entries:
        ends = edge_ends.get(t.target_id)
        if not ends or el.get(ends[0]) != "state" or el.get(ends[1]) != "state" or ends[0] == ends[1]:
            P.append(MKProblem(t.target_id, "mk_bad_transition", "A transition must join two different states."))
            continue
        if t.strategy is not None and el.get(t.strategy) != "strategy":
            P.append(MKProblem(t.target_id, "mk_bad_transition", "Its strategy is no longer a strategy."))
            continue
        m.edges[t.target_id] = ends
        m.transitions[(t.target_id, t.strategy)] = t
    m.rewards = {(r.target_id, r.strategy): r for r in get_rewards(root=paths.root).entries
                 if r.target_id in states and (r.strategy is None or r.strategy in strategies)}
    m.start = {s.target_id: s.proportion for s in get_start(root=paths.root).entries if s.target_id in states}
    if len(states) < 2:
        P.append(MKProblem(None, "mk_too_few_states", "A Markov model needs at least two states."))
    if not m.start:
        P.append(MKProblem(None, "mk_no_start", "Say where the cohort starts (`latris markov start <state> 1`)."))
    elif abs(sum(m.start.values()) - 1) > 1e-6:
        P.append(MKProblem(None, "mk_start_sum", f"Starting shares sum to {sum(m.start.values()):.4g}, not 1."))
    if not m.edges and len(states) >= 2:
        P.append(MKProblem(None, "mk_no_transitions", "No transitions: nothing would ever change state."))
    for strat in m.strategy_names():
        out: dict[str, float] = defaultdict(float)
        for e, (a, _) in m.edges.items():
            t = m.prob(e, strat)
            if t:
                out[a] += t.probability
        for a, total in out.items():
            if total > 1 + 1e-9:
                who = f" under {labels[strat]}" if strat else ""
                P.append(MKProblem(a, "mk_prob_sum", f"Probabilities of leaving sum to {total:.4g}{who}; at most 1."))
    return m


def structure_problems(*, root: Path | None = None) -> list[MKProblem]:
    return load(root=root).problems


# ── the cohort ───────────────────────────────────────────────────────


def run_strategy(m: Model, strategy: str | None) -> dict[str, Any]:
    import numpy as np

    s = m.settings
    n = len(m.states)
    idx = {st: i for i, st in enumerate(m.states)}
    P = np.zeros((n, n))
    for e, (a, b) in m.edges.items():
        t = m.prob(e, strategy)
        if t:
            P[idx[a], idx[b]] += t.probability
    for i in range(n):
        P[i, i] = 1.0 - P[i].sum() + P[i, i]
    p = np.array([m.start.get(st, 0.0) for st in m.states])
    trace = [p]
    for _ in range(s.num_cycles):
        p = p @ P
        trace.append(p)
    tr = np.array(trace)  # (cycles + 1) × states
    years = s.cycle_length * YEARS[s.time_units]
    rc = s.discount_rate
    ro = s.outcome_discount_rate if s.outcome_discount_rate is not None else rc
    cost = np.array([m.reward(st, strategy, "cost")[0] or 0.0 for st in m.states])
    util = np.array([m.reward(st, strategy, "utility")[0] or 0.0 for st in m.states])
    t = np.arange(1, s.num_cycles + 1)
    if s.half_cycle_correction:
        occ = (tr[:-1] + tr[1:]) / 2
        when = (t - 0.5) * years
    else:
        occ = tr[:-1]
        when = (t - 1) * years
    dc, do = (1 + rc) ** -when, (1 + ro) ** -when
    per_cost = occ @ cost
    per_out = (occ @ util) * years
    step = max(1, (len(tr) - 1) // (MAX_TRACE_ROWS - 1))
    rows = list(range(0, len(tr), step))
    if rows[-1] != len(tr) - 1:
        rows.append(len(tr) - 1)
    return {
        "strategy": m.labels[strategy] if strategy else BASE_CASE,
        "cost": float(per_cost @ dc), "outcome": float(per_out @ do),
        "cost_undiscounted": float(per_cost.sum()), "outcome_undiscounted": float(per_out.sum()),
        "time_in_state": {m.labels[st]: float(occ[:, i].sum() * s.cycle_length) for i, st in enumerate(m.states)},
        "final": {m.labels[st]: float(tr[-1, i]) for i, st in enumerate(m.states)},
        "trace": {"cycles": rows, "states": [m.labels[st] for st in m.states],
                  "rows": [[float(x) for x in tr[r]] for r in rows]},
    }


def incremental(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Incremental cost-effectiveness: dominance, extended dominance, ICERs along the frontier."""
    rows = sorted(({"strategy": r["strategy"], "cost": r["cost"], "outcome": r["outcome"], "status": "frontier",
                    "icer": None, "versus": None} for r in results), key=lambda r: (r["cost"], -r["outcome"]))
    for i, r in enumerate(rows):  # strictly dominated: dearer (or equal) and no more effective than something
        for o in rows[:i]:
            if o["outcome"] >= r["outcome"] - _TOL and o is not r:
                r["status"], r["versus"] = "dominated", o["strategy"]
                break
    while True:
        front = [r for r in rows if r["status"] == "frontier"]
        for a, b in zip(front, front[1:], strict=False):
            b["icer"] = (b["cost"] - a["cost"]) / (b["outcome"] - a["outcome"]) if b["outcome"] > a["outcome"] else None
            b["versus"] = a["strategy"]
        ext = None
        for a, b in zip(front[1:], front[2:], strict=False):
            if a["icer"] is not None and b["icer"] is not None and a["icer"] > b["icer"] + _TOL:
                ext = a
                break
        if ext is None:
            break
        ext["status"], ext["icer"] = "extendedly dominated", None
    for r in rows:
        if r["status"] != "frontier":
            r["icer"] = None
    return rows


def analyse(*, root: Path | None = None) -> dict[str, Any]:
    m = load(root=root)
    lab = m.labels
    s = m.settings
    payload: dict[str, Any] = {
        "states": [lab[x] for x in m.states], "strategies": [lab[x] for x in m.strategies] or [BASE_CASE],
        "settings": s.model_dump(exclude={"model_type", "set_by", "rationale"}),
        "problems": [{"label": lab.get(p.target_id or "", "(model)"), "gap_type": p.gap_type, "message": p.message}
                     for p in m.problems],
    }
    if m.problems:
        return payload
    results = [run_strategy(m, st) for st in m.strategy_names()]
    payload["results"] = results
    if len(results) > 1:
        rows = incremental(results)
        payload["incremental"] = rows
        if s.wtp is not None:
            nmb = {r["strategy"]: s.wtp * r["outcome"] - r["cost"] for r in results}
            payload["nmb"] = nmb
            payload["choice"] = max(nmb, key=lambda k: nmb[k])
    missing_cost = [lab[x] for x in m.states if all(m.reward(x, st, "cost")[0] is None for st in m.strategy_names())]
    missing_util = [lab[x] for x in m.states
                    if all(m.reward(x, st, "utility")[0] is None for st in m.strategy_names())]
    weak_t = sorted({f"{lab[m.edges[e][0]]} → {lab[m.edges[e][1]]}" for (e, _), t in m.transitions.items()
                     if t.verification != "human-verified"})
    payload.update(missing_cost=missing_cost, missing_utility=missing_util, unverified_transitions=weak_t,
                   unsourced_transitions=sorted({f"{lab[m.edges[e][0]]} → {lab[m.edges[e][1]]}"
                                                 for (e, _), t in m.transitions.items() if not t.source_id}))
    return payload


def _money(x: float, units: str | None) -> str:
    return f"{units or ''}{x:,.0f}" if units and len(units) <= 2 else f"{x:,.0f}" + (f" {units}" if units else "")


def describe(p: dict[str, Any]) -> str:
    if p["problems"]:
        return f"The Markov model is incomplete ({len(p['problems'])} structure problem(s))"
    s = p["settings"]
    cu, ou = s["cost_units"], s["outcome_units"] or "outcome units"
    parts = [f"{len(p['states'])} states over {s['num_cycles']} cycles of {s['cycle_length']:g} {s['time_units']}"]
    for r in p["results"]:
        parts.append(f"{r['strategy']}: {_money(r['cost'], cu)}, {r['outcome']:.3f} {ou}")
    for r in p.get("incremental", []):
        if r["icer"] is not None:
            parts.append(f"ICER of {r['strategy']} vs {r['versus']}: {_money(r['icer'], cu)} per {ou}")
        elif r["status"] != "frontier":
            parts.append(f"{r['strategy']} {r['status']}")
    if p.get("choice"):
        parts.append(f"at {_money(s['wtp'], cu)} per {ou}, choose {p['choice']}")
    return "; ".join(parts)


def record(payload: dict[str, Any], *, root: Path | None = None) -> tuple[str, str]:
    from latris.operations.analysis_results import record_result

    sha, run = record_result(
        kind="markov-analysis",
        key="markov-analysis",
        payload=payload,
        purpose="simulation",
        algorithm="discrete-time cohort Markov model"
                  + (" with half-cycle correction" if payload["settings"]["half_cycle_correction"] else "")
                  + "; incremental cost-effectiveness with dominance and extended dominance",
        library_version="latris (numpy)",
        summary=describe(payload),
        model_type=MODEL_TYPE,
        metrics={"strategies": len(payload["strategies"]), "choice": payload.get("choice")},
        commit_subject="Analysis: Markov cohort model",
        root=root,
    )
    return sha, run.id
