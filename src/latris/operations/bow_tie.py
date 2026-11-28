"""Bow-ties — threats and consequences of one top event, and the barriers between.

A bow-tie (CCPS & Energy Institute 2018, *Bow Ties in Risk Management*)
centres on a **top event** — the moment control of a **hazard** is lost.
On its left, **threats** that could cause it, each on a line through the
**prevention barriers** meant to stop it; on its right, the
**consequences** that could follow, each through **mitigation barriers**.
An **escalation factor** is a condition that degrades a barrier; its own
line runs through the barriers that control it.

In Latris every element is a substrate entity with a bow-tie role, and the
lines are ordinary ``causal`` or ``logical`` edges, so a bow-tie can share
its events with a fault tree or a causal loop diagram. Only entities with a
bow-tie role are in it; a link into it from anything else is listed and left
out.

The analysis (:func:`analyse`) lays out every line and its barriers and
flags the lines that rest on one effective barrier or none, barriers that
sit on several lines (one failure takes them all), escalation factors with
no control, and barriers with no owner. When every threat has a frequency
and every barrier on its lines a probability of failure on demand, it adds a
layer-of-protection estimate (CCPS 2001): the top event's frequency, each
consequence's, and how much each barrier buys. A barrier on more than one
route is counted once — the routes are combined exactly with the fault-tree
engine's decision diagram.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from latris.operations import _ft_engine as engine
from latris.operations._view_store import ViewStore, replace_entry, resolve_factor
from latris.operations._words import a_or_an
from latris.repo.project import require_project
from latris.repo.yaml_io import load_model
from latris.schema import Substrate
from latris.schema.bow_tie import BT_ELEMENTS, BTBarrierEntry, BTBarrierSet, BTFrequencyEntry, BTFrequencySet
from latris.schema.common import ProvenanceOrigin, ProvenanceVerification

MODEL_TYPE = "bow_tie"
EDGE_KINDS = ("causal", "logical")
ELEMENT_NAMES = {
    "hazard": "Hazard", "top_event": "Top event", "threat": "Threat", "consequence": "Consequence",
    "barrier": "Barrier", "escalation_factor": "Escalation factor",
}
_ALLOWED = {
    ("threat", "barrier"), ("threat", "top_event"),
    ("barrier", "barrier"), ("barrier", "top_event"), ("barrier", "consequence"),
    ("top_event", "barrier"), ("top_event", "consequence"),
    ("hazard", "top_event"),
    ("escalation_factor", "barrier"),
}
MAX_LINES = 500
_UNSET = object()


_store = ViewStore(MODEL_TYPE, BT_ELEMENTS)


# ── reads and writes ─────────────────────────────────────────────────


def get_elements(*, root: Path | None = None) -> dict[str, str]:
    """Entity id → bow-tie element."""
    return _store.roles(root)


def get_barriers(*, root: Path | None = None) -> BTBarrierSet:
    return _store.load(root, "barrier", BTBarrierSet)


def get_frequencies(*, root: Path | None = None) -> BTFrequencySet:
    return _store.load(root, "frequency", BTFrequencySet)


def _resolve(paths, target: str) -> tuple[str, str]:
    return resolve_factor(paths, target, link_error=f"{target!r} is a link; bow-tie elements are factors")


def set_element(target: str, element: str, *, root: Path | None = None) -> tuple[str, str]:
    """Give a factor its place in the bow-tie. Returns (target_id, commit_sha)."""
    from latris.operations.view_roles import set_role

    if element not in BT_ELEMENTS:
        raise ValueError(f"{element!r} is not a bow-tie element. Elements: {', '.join(BT_ELEMENTS)}")
    return set_role(target, MODEL_TYPE, element, root=root)


def _require(paths, target: str, element: str, what: str) -> tuple[str, str]:
    tid, label = _resolve(paths, target)
    got = get_elements(root=paths.root).get(tid)
    if got != element:
        raise ValueError(
            f"{label} is {a_or_an(ELEMENT_NAMES[got].lower()) if got else 'not in the bow-tie'}; only "
            f"{a_or_an(ELEMENT_NAMES[element].lower())} takes {what} (`latris bowtie element <factor> {element}` first)"
        )
    return tid, label


def set_barrier(
    target: str,
    *,
    barrier_type: str | None | object = _UNSET,
    status: str | object = _UNSET,
    owner: str | None | object = _UNSET,
    pfd: float | None | object = _UNSET,
    notes: str | None | object = _UNSET,
    origin: ProvenanceOrigin | object = _UNSET,
    source_id: str | None | object = _UNSET,
    verification: ProvenanceVerification | object = _UNSET,
    root: Path | None = None,
) -> tuple[BTBarrierEntry, str]:
    """Update a barrier's type, status, owner, probability of failure on demand or provenance.

    Only the fields given change; the rest keep their stored values.
    """
    paths = require_project(root)
    tid, label = _require(paths, target, "barrier", "a type, status, owner or failure probability")
    store = get_barriers(root=paths.root)
    current = next((e for e in store.entries if e.target_id == tid), None)
    data = current.model_dump() if current else {"target_id": tid}
    given = {"barrier_type": barrier_type, "status": status, "owner": owner, "pfd": pfd, "notes": notes,
             "origin": origin, "source_id": source_id, "verification": verification}
    changed = {k: v for k, v in given.items() if v is not _UNSET}
    if not changed:
        raise ValueError("nothing to set: give a type, status, owner, failure probability, notes or source")
    entry = BTBarrierEntry.model_validate({**data, **changed})
    replace_entry(store, entry)
    body = "\n".join(f"{k}: {v}" for k, v in changed.items())
    sha = _store.save(paths, "barrier", store, subject=f"Set bow-tie barrier {label}: {', '.join(changed)}",
        body=f"target: {tid}\n{body}")
    return entry, sha


def set_frequency(
    target: str,
    frequency: float,
    *,
    origin: ProvenanceOrigin = "human-direct",
    source_id: str | None = None,
    verification: ProvenanceVerification = "unverified",
    notes: str | None = None,
    root: Path | None = None,
) -> tuple[BTFrequencyEntry, str]:
    """Set how often a threat occurs, per year, with where it came from."""
    paths = require_project(root)
    tid, label = _require(paths, target, "threat", "a frequency")
    entry = BTFrequencyEntry(target_id=tid, frequency=frequency, origin=origin, source_id=source_id,
                             verification=verification, notes=notes)
    store = get_frequencies(root=paths.root)
    replace_entry(store, entry)
    sha = _store.save(paths, "frequency", store, subject=f"Set bow-tie threat frequency {label} = {frequency:g}/year",
        body=f"target: {tid}\nfrequency: {frequency}\norigin: {origin}\nsource_id: {source_id}")
    return entry, sha


# ── structure ────────────────────────────────────────────────────────


@dataclass
class BTProblem:
    target_id: str | None
    gap_type: str
    message: str


@dataclass
class Line:
    start: str  # threat (left), top event (right) or escalation factor
    end: str  # top event (left), consequence (right) or the barrier degraded
    barriers: list[str]


@dataclass
class BowTie:
    labels: dict[str, str]
    elements: dict[str, str]
    out: dict[str, list[str]]
    barriers: dict[str, BTBarrierEntry]
    frequencies: dict[str, BTFrequencyEntry]
    top: str | None
    left: list[Line] = field(default_factory=list)
    right: list[Line] = field(default_factory=list)
    escalation: list[Line] = field(default_factory=list)
    problems: list[BTProblem] = field(default_factory=list)
    outside_inputs: list[tuple[str, str]] = field(default_factory=list)
    truncated: bool = False


def _lines(start: str, ends: set[str], out: dict[str, list[str]], elements: dict[str, str],
           through: set[str] | None = None) -> tuple[list[Line], bool]:
    """Every simple path from ``start`` to a node in ``ends`` through barriers only."""
    found: list[Line] = []
    truncated = False

    def walk(node: str, chain: list[str]) -> None:
        nonlocal truncated
        for nxt in out.get(node, []):
            if len(found) >= MAX_LINES:
                truncated = True
                return
            if nxt in ends:
                found.append(Line(start, nxt, list(chain)))
            elif elements.get(nxt) == "barrier" and nxt not in chain and (through is None or nxt in through):
                walk(nxt, chain + [nxt])

    walk(start, [])
    return found, truncated


def _cycle(members: list[str], out: dict[str, list[str]]) -> str | None:
    state: dict[str, int] = {}

    def visit(n: str) -> str | None:
        state[n] = 1
        for m in out.get(n, []):
            if state.get(m) == 1:
                return m
            if m not in state and (hit := visit(m)):
                return hit
        state[n] = 2
        return None

    for m in members:
        if m not in state and (hit := visit(m)):
            return hit
    return None


def _bow_tie_links(substrate: Substrate, el: dict[str, str]
                   ) -> tuple[dict[str, list[str]], list[tuple[str, str]], list[BTProblem]]:
    """The links between bow-tie elements (``out``), links in from outside it, and links of the wrong kind."""
    out: dict[str, list[str]] = defaultdict(list)
    outside: list[tuple[str, str]] = []
    problems: list[BTProblem] = []
    for e in substrate.edges:
        if e.kind not in EDGE_KINDS or e.to_id not in el:
            continue
        if e.from_id not in el:
            outside.append((e.from_id, e.to_id))
            continue
        pair = (el[e.from_id], el[e.to_id])
        if pair not in _ALLOWED:
            problems.append(BTProblem(e.id, "bt_bad_link", (
                f"{a_or_an(ELEMENT_NAMES[pair[0]].lower()).capitalize()} can't lead to "
                f"{a_or_an(ELEMENT_NAMES[pair[1]].lower())}. Lines run "
                "threat → barriers → top event → barriers → consequence; an escalation factor leads to a barrier."
            )))
            continue
        if e.to_id not in out[e.from_id]:
            out[e.from_id].append(e.to_id)
    return out, outside, problems


def _element_problems(of: dict[str, list[str]]) -> list[BTProblem]:
    """Problems with how many of each element there are: one top event, at most one hazard, a threat and a
    consequence."""
    problems: list[BTProblem] = []
    tops = of["top_event"]
    if not tops:
        problems.append(BTProblem(None, "bt_no_top", "No top event: say what moment of lost control the bow-tie "
                                                     "is about."))
    for t in tops[1:]:
        problems.append(BTProblem(t, "bt_many_tops", "A bow-tie has one top event; build one bow-tie per top event."))
    for h in of["hazard"][1:]:
        problems.append(BTProblem(h, "bt_many_hazards", "A bow-tie has at most one hazard."))
    if not of["threat"]:
        problems.append(BTProblem(None, "bt_no_threat", "No threat: say what could cause the top event."))
    if not of["consequence"]:
        problems.append(BTProblem(None, "bt_no_consequence", "No consequence: say what could follow the top event."))
    return problems


def _trace_main_lines(bt: BowTie, top: str, of: dict[str, list[str]]) -> None:
    """The prevention lines (threat → top event) and mitigation lines (top event → consequence)."""
    problems, el = bt.problems, bt.elements
    for h in of["hazard"]:
        if top not in bt.out.get(h, []):
            problems.append(BTProblem(h, "bt_hazard_unlinked", "Link the hazard to the top event."))
    for t in of["threat"]:
        lines, trunc = _lines(t, {top}, bt.out, el)
        bt.left += lines
        bt.truncated |= trunc
        if not lines:
            problems.append(BTProblem(t, "bt_threat_unlinked", "No line to the top event (through barriers only)."))
    right, trunc = _lines(top, set(of["consequence"]), bt.out, el)
    bt.right, bt.truncated = right, bt.truncated or trunc
    reached = {ln.end for ln in right}
    for c in of["consequence"]:
        if c not in reached:
            problems.append(BTProblem(c, "bt_consequence_unlinked", "No line from the top event (through barriers "
                                                                    "only)."))


def _trace_escalation(bt: BowTie, of: dict[str, list[str]]) -> None:
    """The escalation lines (factor → the barrier it degrades), and barriers on no line at all."""
    problems = bt.problems
    # A barrier on both sides would close a loop through the top event, which the cycle check refuses.
    main = {b for ln in bt.left + bt.right for b in ln.barriers}
    for f in of["escalation_factor"]:
        lines, trunc = _lines(f, main, bt.out, bt.elements, through={b for b in of["barrier"] if b not in main})
        bt.escalation += lines
        bt.truncated |= trunc
        if not lines:
            problems.append(BTProblem(f, "bt_escalation_unlinked", "Link it to the barrier it degrades."))
    ef_b = {b for ln in bt.escalation for b in ln.barriers}
    for b in of["barrier"]:
        if b not in main and b not in ef_b:
            problems.append(BTProblem(b, "bt_barrier_off_line", "Not on any line: put it between a threat and the "
                                                                "top event, the top event and a consequence, or an "
                                                                "escalation factor and the barrier it degrades."))


def load_bow_tie(*, root: Path | None = None) -> BowTie:
    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    labels = {e.id: e.label for e in substrate.entities}
    el = {k: v for k, v in get_elements(root=paths.root).items() if k in labels}
    out, outside, problems = _bow_tie_links(substrate, el)
    barriers = {b.target_id: b for b in get_barriers(root=paths.root).entries if b.target_id in el}
    freqs = {f.target_id: f for f in get_frequencies(root=paths.root).entries if f.target_id in el}
    of: dict[str, list[str]] = defaultdict(list)
    for eid, t in el.items():
        of[t].append(eid)
    tops = of["top_event"]
    bt = BowTie(labels=labels, elements=el, out=dict(out), barriers=barriers, frequencies=freqs,
                top=tops[0] if len(tops) == 1 else None, problems=problems, outside_inputs=outside)
    problems += _element_problems(of)
    cyc = _cycle(list(el), bt.out)
    if cyc:
        problems.append(BTProblem(cyc, "bt_cycle", "The lines loop back through this element."))
    if bt.top is None or cyc:
        return bt
    _trace_main_lines(bt, bt.top, of)
    _trace_escalation(bt, of)
    return bt


def structure_problems(*, root: Path | None = None) -> list[BTProblem]:
    return load_bow_tie(root=root).problems


# ── analysis ─────────────────────────────────────────────────────────


def _effective(bt: BowTie, b: str) -> bool:
    entry = bt.barriers.get(b)
    return entry is None or entry.status == "in_place"


def _pfd(bt: BowTie, b: str) -> float | None:
    entry = bt.barriers.get(b)
    if entry is not None and entry.status == "not_in_place":
        return 1.0
    return entry.pfd if entry else None


def _through(lines: list[Line], pfd: dict[str, float]) -> float:
    """P(at least one line has every barrier fail) — barriers independent, each counted once."""
    if any(not ln.barriers for ln in lines):
        return 1.0
    if not lines:
        return 0.0
    gates: engine.Gates = {"__any": ("or", None, [f"__line{i}" for i in range(len(lines))])}
    for i, ln in enumerate(lines):
        gates[f"__line{i}"] = ("and", None, list(dict.fromkeys(ln.barriers)))
    bdd, root = engine.build_bdd("__any", gates)
    return bdd.probability(root, pfd)


def _frequencies(bt: BowTie, pfd: dict[str, float], freq: dict[str, float]) -> tuple[float, dict[str, float]]:
    """Top-event frequency (Σ over threats) and each consequence's frequency, per year."""
    by_threat: dict[str, list[Line]] = defaultdict(list)
    for ln in bt.left:
        by_threat[ln.start].append(ln)
    f_top = sum(freq[t] * _through(lines, pfd) for t, lines in by_threat.items())
    by_cons: dict[str, list[Line]] = defaultdict(list)
    for ln in bt.right:
        by_cons[ln.end].append(ln)
    return f_top, {c: f_top * _through(lines, pfd) for c, lines in by_cons.items()}




def _line_row(bt: BowTie, ln: Line, side: str) -> dict[str, Any]:
    lab = bt.labels
    eff = [b for b in ln.barriers if _effective(bt, b)]
    return {"side": side, "from": lab[ln.start], "to": lab[ln.end], "barriers": [lab[b] for b in ln.barriers],
            "effective": len(eff),
            "not_effective": [lab[b] for b in ln.barriers if not _effective(bt, b)]}


def _quantify(bt: BowTie, payload: dict[str, Any], left_b: set[str], right_b: set[str]) -> dict[str, float | None]:
    """The layer-of-protection estimate, into ``payload`` (``missing``, ``quantified``, ``frequency``), when every
    threat with a line has a frequency and every barrier on a line a PFD. Returns each barrier's risk ratio: the
    frequency with it failed over the frequency now (empty when the numbers are missing)."""
    lab = bt.labels
    threats = sorted({ln.start for ln in bt.left})
    on_lines = sorted(left_b | right_b)
    pfd = {b: v for b in on_lines if (v := _pfd(bt, b)) is not None}
    freq = {t: bt.frequencies[t].frequency for t in threats if t in bt.frequencies}
    missing = [lab[t] + " (frequency)" for t in threats if t not in freq]
    missing += [lab[b] + " (failure probability)" for b in on_lines if b not in pfd]
    payload["missing"] = missing
    raw: dict[str, float | None] = {}
    if missing:
        return raw
    f_top, f_cons = _frequencies(bt, pfd, freq)
    payload["quantified"] = True
    payload["frequency"] = {
        "top": f_top, "consequences": {lab[c]: v for c, v in f_cons.items()},
        "threats": {lab[t]: freq[t] for t in threats},
    }
    total_cons = sum(f_cons.values())
    for b in on_lines:
        f2_top, f2_cons = _frequencies(bt, {**pfd, b: 1.0}, freq)
        if b in left_b:
            raw[b] = f2_top / f_top if f_top > 0 else None
        else:
            raw[b] = sum(f2_cons.values()) / total_cons if total_cons > 0 else None
    return raw


def _barrier_row(bt: BowTie, b: str, side: str, lines: int, factors: list[dict[str, Any]],
                 raw: float | None) -> dict[str, Any]:
    e = bt.barriers.get(b)
    return {
        "barrier": bt.labels[b], "side": side,
        "type": e.barrier_type if e else None, "status": e.status if e else "in_place",
        "owner": e.owner if e else None, "pfd": e.pfd if e else None,
        "origin": e.origin if e else None, "source": e.source_id if e else None,
        "verification": e.verification if e else None, "weak": e is None or e.pfd is None or e.is_weak,
        "lines": lines, "escalation_factors": factors, "raw": raw,
    }


def _barrier_rows(bt: BowTie, left_b: set[str], right_b: set[str], raw: dict[str, float | None]
                  ) -> list[dict[str, Any]]:
    """One row per barrier, the one whose failure raises the risk most first."""
    lab = bt.labels
    lines_of: dict[str, int] = defaultdict(int)
    for ln in bt.left + bt.right:
        for b in set(ln.barriers):
            lines_of[b] += 1
    ef_on: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ln in bt.escalation:
        ef_on[ln.end].append({"factor": lab[ln.start], "controls": [lab[b] for b in ln.barriers]})
    ef_b = {b for ln in bt.escalation for b in ln.barriers}
    rows = []
    for b in sorted(bt.barriers.keys() | left_b | right_b | ef_b, key=lambda x: lab[x]):
        side = "prevention" if b in left_b else "mitigation" if b in right_b else "escalation control"
        rows.append(_barrier_row(bt, b, side, lines_of.get(b, 0), ef_on.get(b, []), raw.get(b)))
    rows.sort(key=lambda r: (-(r["raw"] or 0), r["barrier"]))
    return rows


def analyse(*, root: Path | None = None) -> dict[str, Any]:
    """The bow-tie's lines, what weakens them, and (with the numbers) a layer-of-protection estimate."""
    bt = load_bow_tie(root=root)
    lab = bt.labels
    counts = {t: sum(1 for v in bt.elements.values() if v == t) for t in BT_ELEMENTS}
    payload: dict[str, Any] = {
        "top": lab.get(bt.top) if bt.top else None,
        "hazard": next((lab[k] for k, v in bt.elements.items() if v == "hazard"), None),
        "counts": counts,
        "problems": [{"label": lab.get(p.target_id or "", "(bow-tie)"), "gap_type": p.gap_type,
                      "message": p.message} for p in bt.problems],
        "outside_inputs": [f"{lab.get(a, a)} → {lab.get(b, b)}" for a, b in bt.outside_inputs],
        "lines": [], "barriers": [], "escalation": [], "truncated": bt.truncated,
        "quantified": False, "missing": [], "frequency": None,
    }
    if bt.problems:
        return payload

    payload["lines"] = ([_line_row(bt, ln, "prevention") for ln in bt.left]
                        + [_line_row(bt, ln, "mitigation") for ln in bt.right])
    payload["escalation"] = [{"factor": lab[ln.start], "degrades": lab[ln.end],
                              "controls": [lab[b] for b in ln.barriers]} for ln in bt.escalation]
    left_b = {b for ln in bt.left for b in ln.barriers}
    right_b = {b for ln in bt.right for b in ln.barriers}
    raw = _quantify(bt, payload, left_b, right_b)
    payload["barriers"] = _barrier_rows(bt, left_b, right_b, raw)
    return payload


def flags(payload: dict[str, Any]) -> dict[str, list[str]]:
    """What a reader should look at: thin lines, shared barriers, uncontrolled escalation, no owner."""
    lines = payload["lines"]
    return {
        "unprotected": [f"{ln['from']} → {ln['to']}" for ln in lines if ln["effective"] == 0],
        "single_barrier": [f"{ln['from']} → {ln['to']}" for ln in lines if ln["effective"] == 1],
        "shared": [b["barrier"] for b in payload["barriers"] if b["lines"] > 1],
        "uncontrolled_escalation": [f"{e['factor']} → {e['degrades']}" for e in payload["escalation"]
                                    if not e["controls"]],
        "not_in_place": [b["barrier"] for b in payload["barriers"] if b["status"] != "in_place"],
        "no_owner": [b["barrier"] for b in payload["barriers"] if not b["owner"]],
    }


def describe(payload: dict[str, Any]) -> str:
    if payload["problems"]:
        return f"The bow-tie is incomplete ({len(payload['problems'])} structure problem(s))"
    c = payload["counts"]
    n_prev = sum(1 for ln in payload["lines"] if ln["side"] == "prevention")
    n_mit = len(payload["lines"]) - n_prev
    f = flags(payload)
    parts = [f"{payload['top']}: {c['threat']} threat(s) on {n_prev} prevention line(s), {c['consequence']} "
             f"consequence(s) on {n_mit} mitigation line(s), {c['barrier']} barrier(s)"]
    if f["unprotected"]:
        parts.append(f"{len(f['unprotected'])} line(s) with no effective barrier")
    if f["single_barrier"]:
        parts.append(f"{len(f['single_barrier'])} resting on one barrier")
    if f["shared"]:
        parts.append(f"{len(f['shared'])} barrier(s) on more than one line")
    if f["uncontrolled_escalation"]:
        parts.append(f"{len(f['uncontrolled_escalation'])} escalation factor(s) with no control")
    if payload["quantified"]:
        parts.append(f"top-event frequency {payload['frequency']['top']:.3g}/year")
    elif payload["missing"]:
        parts.append(f"{len(payload['missing'])} value(s) missing, so not quantified")
    return "; ".join(parts)


def record(payload: dict[str, Any], *, root: Path | None = None) -> tuple[str, str]:
    """Record an analysis so reports show it. Returns (commit_sha, run_id)."""
    from latris.operations.analysis_results import record_result

    f = flags(payload)
    sha, run = record_result(
        kind="bt-analysis",
        key="bt-analysis",
        payload=payload,
        purpose="inference" if payload["quantified"] else "validation",
        algorithm="bow-tie line enumeration; barrier counts and flags; layer-of-protection frequencies with "
                  "routes combined exactly (BDD)",
        library_version="latris",
        summary=describe(payload),
        model_type=MODEL_TYPE,
        metrics={"lines": len(payload["lines"]), "unprotected": len(f["unprotected"]),
                 "single_barrier": len(f["single_barrier"]), "shared": len(f["shared"]),
                 "top_frequency": (payload["frequency"] or {}).get("top")},
        commit_subject="Analysis: bow-tie",
        root=root,
    )
    return sha, run.id
