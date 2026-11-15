"""Fault trees — events, gates, probabilities, and the analysis of the top event.

A fault tree (Vesely et al. 1981, *Fault Tree Handbook*; IEC 61025) breaks an
undesired **top event** down through **gates** into the **basic events**
that, in combination, cause it. In Latris:

- each event is a substrate entity whose type in the tree is a view role:
  ``top_event``, ``intermediate_event``, ``basic_event`` or
  ``undeveloped_event`` (a leaf not broken down further);
- a link from an input event to the event it feeds is an ordinary ``causal``
  or ``logical`` edge, so a fault tree and a causal loop diagram can share
  their events;
- every top or intermediate event has one gate (``and``, ``or``, or ``vote``
  with ``k``), stored on the event (``schema/fault_tree.py``);
- basic and undeveloped events may carry a probability, each with its own
  provenance.

Only entities with a fault-tree type are in the tree. A link into the tree
from an unclassified factor is left out and reported, never silently used.

The analysis (:func:`analyse`) lists the minimal cut sets and single points
of failure; when every leaf has a probability it adds the exact top-event
probability and each event's importance (``_ft_engine``).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from latris.operations import _ft_engine as engine
from latris.operations._resolve import resolve_target
from latris.operations.commit import auto_commit
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_model, load_model
from latris.schema import Substrate
from latris.schema.common import ProvenanceOrigin, ProvenanceVerification
from latris.schema.fault_tree import (
    FT_EVENT_TYPES,
    FTGateEntry,
    FTGateSet,
    FTProbabilityEntry,
    FTProbabilitySet,
)

MODEL_TYPE = "fault_tree"
EDGE_KINDS = ("causal", "logical")
LEAVES = ("basic_event", "undeveloped_event")
GATED = ("top_event", "intermediate_event")
EVENT_NAMES = {
    "top_event": "Top event",
    "intermediate_event": "Intermediate event",
    "basic_event": "Basic event",
    "undeveloped_event": "Undeveloped event",
}
MAX_LISTED_CUT_SETS = 200


def _gate_path(paths) -> Path:
    return paths.view_attribute_path(MODEL_TYPE, "gate")


def _prob_path(paths) -> Path:
    return paths.view_attribute_path(MODEL_TYPE, "probability")


def _load(path: Path, cls):
    return load_model(cls, path) if path.exists() else cls()


def _dump(path: Path, store) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    dump_model(store, path)


# ── reads ────────────────────────────────────────────────────────────


def get_events(*, root: Path | None = None) -> dict[str, str]:
    """Entity id → event type."""
    from latris.schema.roles import RoleSet

    paths = require_project(root)
    p = paths.role_path(MODEL_TYPE)
    if not p.exists():
        return {}
    return {e.target_id: e.value for e in load_model(RoleSet, p).entries if e.value in FT_EVENT_TYPES}


def get_gates(*, root: Path | None = None) -> FTGateSet:
    return _load(_gate_path(require_project(root)), FTGateSet)


def get_probabilities(*, root: Path | None = None) -> FTProbabilitySet:
    return _load(_prob_path(require_project(root)), FTProbabilitySet)


# ── writes ───────────────────────────────────────────────────────────


def _resolve(paths, target: str) -> tuple[str, str]:
    substrate = load_model(Substrate, paths.conceptual_yaml)
    tid = resolve_target(target, substrate)
    label = next((e.label for e in substrate.entities if e.id == tid), None)
    if label is None:
        raise ValueError(f"{target!r} is a link; fault-tree events are factors")
    return tid, label


def set_event(target: str, event_type: str, *, root: Path | None = None) -> tuple[str, str]:
    """Give a factor its type in the fault tree. Returns (target_id, commit_sha)."""
    from latris.operations.view_roles import set_role

    if event_type not in FT_EVENT_TYPES:
        raise ValueError(f"{event_type!r} is not a fault-tree event type. Types: {', '.join(FT_EVENT_TYPES)}")
    return set_role(target, MODEL_TYPE, event_type, root=root)


def set_gate(
    target: str, gate: str, *, k: int | None = None, root: Path | None = None
) -> tuple[FTGateEntry, str]:
    """Set how a top or intermediate event's inputs combine (and, or, vote with k)."""
    paths = require_project(root)
    tid, label = _resolve(paths, target)
    etype = get_events(root=paths.root).get(tid)
    if etype not in GATED:
        raise ValueError(
            f"{label} is {EVENT_NAMES.get(etype, 'not in the fault tree').lower()}; only a top or intermediate "
            "event has a gate (`latris ft event <factor> intermediate_event` first)"
        )
    entry = FTGateEntry(target_id=tid, gate=gate, k=k)  # type: ignore[arg-type]
    store = get_gates(root=paths.root)
    store.entries = [e for e in store.entries if e.target_id != tid] + [entry]
    path = _gate_path(paths)
    _dump(path, store)
    shown = f"vote {k}" if gate == "vote" else gate
    sha = auto_commit(paths.root, subject=f"Set fault-tree gate on {label}: {shown}",
                      body=f"target: {tid}\ngate: {gate}\nk: {k}", paths=[path])
    return entry, sha


def set_probability(
    target: str,
    probability: float,
    *,
    origin: ProvenanceOrigin = "human-direct",
    source_id: str | None = None,
    verification: ProvenanceVerification = "unverified",
    notes: str | None = None,
    root: Path | None = None,
) -> tuple[FTProbabilityEntry, str]:
    """Set a basic or undeveloped event's probability, with where it came from."""
    paths = require_project(root)
    tid, label = _resolve(paths, target)
    etype = get_events(root=paths.root).get(tid)
    if etype not in LEAVES:
        raise ValueError(
            f"{label} is {EVENT_NAMES.get(etype, 'not in the fault tree').lower()}; only basic and undeveloped "
            "events take a probability — the others follow from their gates"
        )
    entry = FTProbabilityEntry(target_id=tid, probability=probability, origin=origin, source_id=source_id,
                               verification=verification, notes=notes)
    store = get_probabilities(root=paths.root)
    store.entries = [e for e in store.entries if e.target_id != tid] + [entry]
    path = _prob_path(paths)
    _dump(path, store)
    sha = auto_commit(
        paths.root, subject=f"Set fault-tree probability of {label} = {probability:g}",
        body=f"target: {tid}\nprobability: {probability}\norigin: {origin}\nsource_id: {source_id}\n"
             f"verification: {verification}",
        paths=[path],
    )
    return entry, sha


# ── structure ────────────────────────────────────────────────────────


@dataclass
class FTProblem:
    target_id: str | None
    gap_type: str
    message: str


@dataclass
class Tree:
    labels: dict[str, str]
    events: dict[str, str]
    inputs: dict[str, list[str]]
    gates: dict[str, FTGateEntry]
    probabilities: dict[str, FTProbabilityEntry]
    top: str | None
    problems: list[FTProblem] = field(default_factory=list)
    outside_inputs: list[tuple[str, str]] = field(default_factory=list)  # (from, to) left out of the tree

    def engine_gates(self) -> engine.Gates:
        return {
            eid: (self.gates[eid].gate, self.gates[eid].k, self.inputs[eid])
            for eid, t in self.events.items() if t in GATED and eid in self.gates
        }


def _find_cycle(members: list[str], inputs: dict[str, list[str]]) -> str | None:
    state: dict[str, int] = {}

    def visit(n: str) -> str | None:
        state[n] = 1
        for i in inputs.get(n, []):
            if state.get(i) == 1:
                return i
            if i not in state:
                hit = visit(i)
                if hit:
                    return hit
        state[n] = 2
        return None

    for m in members:
        if m not in state:
            hit = visit(m)
            if hit:
                return hit
    return None


def load_tree(*, root: Path | None = None) -> Tree:
    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    labels = {e.id: e.label for e in substrate.entities}
    events = {k: v for k, v in get_events(root=paths.root).items() if k in labels}
    inputs: dict[str, list[str]] = defaultdict(list)
    outside: list[tuple[str, str]] = []
    for e in substrate.edges:
        if e.kind not in EDGE_KINDS or e.to_id not in events:
            continue
        if e.from_id in events:
            if e.from_id not in inputs[e.to_id]:
                inputs[e.to_id].append(e.from_id)
        else:
            outside.append((e.from_id, e.to_id))
    gates = {g.target_id: g for g in get_gates(root=paths.root).entries if g.target_id in events}
    probs = {p.target_id: p for p in get_probabilities(root=paths.root).entries if p.target_id in events}

    problems: list[FTProblem] = []
    tops = [eid for eid, t in events.items() if t == "top_event"]
    if not tops:
        problems.append(FTProblem(None, "ft_no_top", "No top event: say which undesired event the tree explains."))
    elif len(tops) > 1:
        for t in tops[1:]:
            problems.append(FTProblem(t, "ft_many_tops", "A fault tree has one top event; make the others "
                                                          "intermediate events or build a tree for each."))
    for eid, t in events.items():
        n_in = len(inputs.get(eid, []))
        if t in GATED:
            if eid not in gates:
                problems.append(FTProblem(eid, "ft_no_gate", "No gate: say whether its inputs combine with and, "
                                                             "or, or vote (`latris ft gate`)."))
            if n_in == 0:
                problems.append(FTProblem(eid, "ft_no_inputs", "No input events: link the events that cause it, "
                                                               "or make it a basic or undeveloped event."))
            g = gates.get(eid)
            if g and g.gate == "vote" and g.k and g.k > n_in:
                problems.append(FTProblem(eid, "ft_vote_k", f"Vote gate needs {g.k} of {n_in} input(s)."))
        elif n_in:
            problems.append(FTProblem(eid, "ft_leaf_has_inputs", f"{EVENT_NAMES[t]} with input events: make it an "
                                                                  "intermediate event with a gate."))
    cyc = _find_cycle(list(events), inputs)
    if cyc:
        problems.append(FTProblem(cyc, "ft_cycle", "The tree loops back on itself through this event."))
    elif len(tops) == 1:
        reach: set[str] = set()
        stack = [tops[0]]
        while stack:
            n = stack.pop()
            if n not in reach:
                reach.add(n)
                stack.extend(inputs.get(n, []))
        for eid in events:
            if eid not in reach:
                problems.append(FTProblem(eid, "ft_not_in_tree", "Doesn't lead to the top event."))
    return Tree(labels=labels, events=events, inputs=dict(inputs), gates=gates, probabilities=probs,
                top=tops[0] if len(tops) == 1 else None, problems=problems, outside_inputs=outside)


def structure_problems(*, root: Path | None = None) -> list[FTProblem]:
    return load_tree(root=root).problems


# ── analysis ─────────────────────────────────────────────────────────


def _weak(p: FTProbabilityEntry) -> bool:
    return p.verification != "human-verified" or p.contested


def analyse(*, max_order: int | None = None, root: Path | None = None) -> dict[str, Any]:
    """Cut sets, single points of failure and (with every leaf's probability) the quantification."""
    tree = load_tree(root=root)
    lab = tree.labels
    payload: dict[str, Any] = {
        "top": lab.get(tree.top) if tree.top else None,
        "counts": {t: sum(1 for v in tree.events.values() if v == t) for t in FT_EVENT_TYPES},
        "problems": [{"label": lab.get(p.target_id or "", "(tree)"), "gap_type": p.gap_type, "message": p.message}
                     for p in tree.problems],
        "outside_inputs": [f"{lab.get(a, a)} → {lab.get(b, b)}" for a, b in tree.outside_inputs],
        "max_order": max_order,
        "cut_sets": [], "cut_sets_total": 0, "by_order": {}, "single_points": [],
        "quantified": False, "missing_probabilities": [], "probability": None, "importance": [],
        "error": None,
    }
    if tree.problems or not tree.top:
        return payload
    gates = tree.engine_gates()
    try:
        cuts = engine.minimal_cut_sets(tree.top, gates, max_order=max_order)
    except engine.TooManyCutSets as exc:
        payload["error"] = str(exc)
        return payload
    leaves = engine.leaves_under(tree.top, gates)
    p = {e: tree.probabilities[e].probability for e in leaves if e in tree.probabilities}
    missing = [e for e in leaves if e not in p]
    payload["missing_probabilities"] = [lab[e] for e in missing]

    def cs_row(c: frozenset[str]) -> dict[str, Any]:
        return {"events": sorted(lab[e] for e in c), "order": len(c),
                "probability": engine.cut_set_probability(c, p) if not missing else None}

    rows = [cs_row(c) for c in cuts]
    if not missing:
        rows.sort(key=lambda r: (r["order"], -r["probability"], r["events"]))
    by_order: dict[int, int] = defaultdict(int)
    for c in cuts:
        by_order[len(c)] += 1
    payload.update(
        cut_sets=rows[:MAX_LISTED_CUT_SETS], cut_sets_total=len(cuts), by_order=dict(sorted(by_order.items())),
        single_points=sorted(lab[next(iter(c))] for c in cuts if len(c) == 1),
    )
    if missing:
        return payload
    if max_order is not None:
        # The quantification needs every cut set; the order limit only shortens the listing.
        cuts = engine.minimal_cut_sets(tree.top, gates)
    q = engine.quantify(tree.top, gates, p, cuts)
    payload.update(
        quantified=True,
        probability={"exact": q.top_probability, "rare_event": q.rare_event,
                     "min_cut_upper_bound": q.min_cut_upper_bound},
        importance=[
            {"event": lab[i.event], "probability": i.probability, "birnbaum": i.birnbaum,
             "fussell_vesely": i.fussell_vesely, "raw": i.raw,
             "origin": tree.probabilities[i.event].origin,
             "verification": tree.probabilities[i.event].verification,
             "source": tree.probabilities[i.event].source_id, "weak": _weak(tree.probabilities[i.event])}
            for i in q.importance
        ],
    )
    return payload


def describe(payload: dict[str, Any]) -> str:
    """One-line summary of an analysis payload."""
    if payload.get("problems"):
        return f"The fault tree is incomplete ({len(payload['problems'])} structure problem(s))"
    if payload.get("error"):
        return payload["error"]
    n = payload["cut_sets_total"]
    orders = ", ".join(f"{c} of order {o}" for o, c in payload["by_order"].items())
    spof = payload["single_points"]
    parts = [f"{n} minimal cut set(s) for {payload['top']}" + (f" ({orders})" if orders else "")]
    parts.append(f"single points of failure: {', '.join(spof)}" if spof else "no single point of failure")
    if payload["quantified"]:
        top = payload["importance"][0] if payload["importance"] else None
        parts.append(f"top-event probability {payload['probability']['exact']:.3g}")
        if top:
            parts.append(f"largest contributor {top['event']} (Fussell–Vesely {top['fussell_vesely']:.2f})")
    elif payload["missing_probabilities"]:
        parts.append(f"no probability yet for {len(payload['missing_probabilities'])} event(s), so not quantified")
    return "; ".join(parts)


def record(payload: dict[str, Any], *, root: Path | None = None) -> tuple[str, str]:
    """Record an analysis so reports show it. Returns (commit_sha, run_id)."""
    from latris.operations.analysis_results import record_result

    weak = [i["event"] for i in payload["importance"][:5] if i["weak"]]
    sha, run = record_result(
        kind="ft-analysis",
        key=f"ft-analysis|{payload.get('max_order') or 'all'}",
        payload=payload,
        purpose="inference" if payload["quantified"] else "validation",
        algorithm="minimal cut sets (MOCUS, superset elimination); exact top-event probability by BDD; "
                  "Birnbaum, Fussell–Vesely and RAW importance",
        library_version="latris",
        summary=describe(payload),
        model_type=MODEL_TYPE,
        hyperparameters={"max_order": payload.get("max_order")},
        metrics={"cut_sets": payload["cut_sets_total"], "single_points": len(payload["single_points"]),
                 "top_probability": (payload["probability"] or {}).get("exact"), "weak_top_contributors": weak},
        commit_subject="Analysis: fault tree",
        root=root,
    )
    return sha, run.id
