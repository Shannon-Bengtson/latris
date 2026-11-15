"""Event trees — from one initiating event, through yes/no headings, to end states.

An event tree (IEC 62502; the PRA Procedures Guide, NUREG/CR-2300) follows
an **initiating event** forward. At each **heading** — a functional event
such as *Gas detected?* or *Ignition?* — the branch splits yes or no, and
each complete **sequence** of answers ends in an **end state** (*safe
shutdown*, *jet fire*, …). Each heading carries P(yes), in general or given
the answers before it; the initiating event may carry a frequency.

In Latris the initiating event, headings and end states are substrate
entities with an event-tree role. The tree — heading order and sequences —
is stored as data (``schema/event_tree.py``), because one heading is asked on
many branches and one end state reached by many sequences.

:func:`load_tree` checks the sequences form a complete tree: every branch
covered, exactly once. :func:`analyse` gives each sequence's probability
(and frequency, with the initiator's), the totals per end state, and which
values on the dominant sequences nobody has verified.
"""

from __future__ import annotations

import math
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
from latris.schema.event_tree import (
    ET_ELEMENTS,
    ETFrequencyEntry,
    ETFrequencySet,
    ETProbabilityEntry,
    ETProbabilitySet,
    ETSequence,
    ETStep,
    ETStructure,
)

MODEL_TYPE = "event_tree"
ELEMENT_NAMES = {"initiating_event": "Initiating event", "functional_event": "Heading", "end_state": "End state"}
ANSWERS = ("yes", "no")


def _path(paths, attr: str) -> Path:
    return paths.view_attribute_path(MODEL_TYPE, attr)


def _load(path: Path, cls):
    return load_model(cls, path) if path.exists() else cls()


def _dump(path: Path, store) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    dump_model(store, path)


# ── reads ────────────────────────────────────────────────────────────


def get_elements(*, root: Path | None = None) -> dict[str, str]:
    from latris.schema.roles import RoleSet

    paths = require_project(root)
    p = paths.role_path(MODEL_TYPE)
    if not p.exists():
        return {}
    return {e.target_id: e.value for e in load_model(RoleSet, p).entries if e.value in ET_ELEMENTS}


def get_structure(*, root: Path | None = None) -> ETStructure:
    return _load(_path(require_project(root), "structure"), ETStructure)


def get_probabilities(*, root: Path | None = None) -> ETProbabilitySet:
    return _load(_path(require_project(root), "probability"), ETProbabilitySet)


def get_frequencies(*, root: Path | None = None) -> ETFrequencySet:
    return _load(_path(require_project(root), "frequency"), ETFrequencySet)


# ── writes ───────────────────────────────────────────────────────────


def _entity(substrate, target: str) -> tuple[str, str]:
    tid = resolve_target(target, substrate)
    label = next((e.label for e in substrate.entities if e.id == tid), None)
    if label is None:
        raise ValueError(f"{target!r} is a link; event-tree elements are factors")
    return tid, label


def _require(paths, substrate, target: str, element: str) -> tuple[str, str]:
    tid, label = _entity(substrate, target)
    got = get_elements(root=paths.root).get(tid)
    if got != element:
        raise ValueError(
            f"{label} is {('a ' + ELEMENT_NAMES[got].lower()) if got else 'not in the event tree'}, not a "
            f"{ELEMENT_NAMES[element].lower()} (`latris et element <factor> {element}`)"
        )
    return tid, label


def _steps(paths, substrate, path: list[tuple[str, str]]) -> list[ETStep]:
    steps = []
    for heading, answer in path:
        if answer not in ANSWERS:
            raise ValueError(f"answer for {heading!r} must be yes or no, not {answer!r}")
        hid, _ = _require(paths, substrate, heading, "functional_event")
        steps.append(ETStep(heading=hid, answer=answer))  # type: ignore[arg-type]
    if len({s.heading for s in steps}) != len(steps):
        raise ValueError("a heading can be answered only once on a sequence")
    return steps


def parse_answers(items: list[str]) -> list[tuple[str, str]]:
    """``["Gas detected=no", "Ignition=yes"]`` → ``[("Gas detected", "no"), ("Ignition", "yes")]``."""
    out = []
    for item in items:
        if "=" not in item:
            raise ValueError(f"write each answer as 'Heading=yes' or 'Heading=no', not {item!r}")
        h, a = item.rsplit("=", 1)
        out.append((h.strip(), a.strip().lower()))
    return out


def set_element(target: str, element: str, *, root: Path | None = None) -> tuple[str, str]:
    from latris.operations.view_roles import set_role

    if element not in ET_ELEMENTS:
        raise ValueError(f"{element!r} is not an event-tree element. Elements: {', '.join(ET_ELEMENTS)}")
    return set_role(target, MODEL_TYPE, element, root=root)


def set_order(headings: list[str], *, root: Path | None = None) -> tuple[ETStructure, str]:
    """Set the headings, left to right (the order questions are asked on every branch)."""
    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    ids = [_require(paths, substrate, h, "functional_event")[0] for h in headings]
    if len(set(ids)) != len(ids):
        raise ValueError("a heading is listed twice")
    store = get_structure(root=paths.root)
    store.headings = ids
    path = _path(paths, "structure")
    _dump(path, store)
    labels = {e.id: e.label for e in substrate.entities}
    sha = auto_commit(paths.root, subject="Set event-tree heading order: " + " → ".join(labels[i] for i in ids),
                      body="\n".join(ids), paths=[path])
    return store, sha


def set_sequence(end_state: str, path: list[tuple[str, str]], *, root: Path | None = None) -> tuple[ETSequence, str]:
    """Add a sequence (its answers, and the end state it reaches); the same answers again replace it."""
    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    end_id, end_label = _require(paths, substrate, end_state, "end_state")
    steps = _steps(paths, substrate, path)
    store = get_structure(root=paths.root)
    order = {h: i for i, h in enumerate(store.headings)}
    missing = [s.heading for s in steps if s.heading not in order]
    if missing:
        labels = {e.id: e.label for e in substrate.entities}
        raise ValueError(f"set the heading order first (`latris et order …`); not in it: "
                         f"{', '.join(labels[m] for m in missing)}")
    steps.sort(key=lambda s: order[s.heading])
    seq = ETSequence(path=steps, end_state=end_id)
    key = [(s.heading, s.answer) for s in steps]
    store.sequences = [s for s in store.sequences if [(x.heading, x.answer) for x in s.path] != key] + [seq]
    store.sequences.sort(key=lambda s: [(order.get(x.heading, 99), ANSWERS.index(x.answer)) for x in s.path])
    p = _path(paths, "structure")
    _dump(p, store)
    sha = auto_commit(paths.root, subject=f"Set event-tree sequence → {end_label}",
                      body="\n".join(f"{s.heading}: {s.answer}" for s in steps), paths=[p])
    return seq, sha


def remove_sequence(path: list[tuple[str, str]], *, root: Path | None = None) -> str:
    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    key = sorted((s.heading, s.answer) for s in _steps(paths, substrate, path))
    store = get_structure(root=paths.root)
    kept = [s for s in store.sequences if sorted((x.heading, x.answer) for x in s.path) != key]
    if len(kept) == len(store.sequences):
        raise ValueError("no sequence has exactly those answers")
    store.sequences = kept
    p = _path(paths, "structure")
    _dump(p, store)
    return auto_commit(paths.root, subject="Removed an event-tree sequence", body=str(key), paths=[p])


def set_probability(
    heading: str,
    p_yes: float,
    *,
    given: list[tuple[str, str]] | None = None,
    origin: ProvenanceOrigin = "human-direct",
    source_id: str | None = None,
    verification: ProvenanceVerification = "unverified",
    notes: str | None = None,
    root: Path | None = None,
) -> tuple[ETProbabilityEntry, str]:
    """Set P(yes) for a heading — in general, or given earlier headings' answers."""
    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    hid, label = _require(paths, substrate, heading, "functional_event")
    cond = _steps(paths, substrate, given or [])
    if any(c.heading == hid for c in cond):
        raise ValueError("a heading's probability can't be conditional on its own answer")
    entry = ETProbabilityEntry(target_id=hid, p_yes=p_yes, given=sorted(cond, key=lambda c: c.heading),
                               origin=origin, source_id=source_id, verification=verification, notes=notes)
    key = (hid, frozenset((c.heading, c.answer) for c in cond))
    store = get_probabilities(root=paths.root)
    store.entries = [e for e in store.entries
                     if (e.target_id, frozenset((c.heading, c.answer) for c in e.given)) != key] + [entry]
    p = _path(paths, "probability")
    _dump(p, store)
    labels = {e.id: e.label for e in substrate.entities}
    cond_txt = (" given " + ", ".join(f"{labels[c.heading]}={c.answer}" for c in cond)) if cond else ""
    sha = auto_commit(paths.root, subject=f"Set event-tree P({label}=yes{cond_txt}) = {p_yes:g}",
                      body=f"target: {hid}\np_yes: {p_yes}\norigin: {origin}\nsource_id: {source_id}", paths=[p])
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
) -> tuple[ETFrequencyEntry, str]:
    """Set how often the initiating event occurs, per year."""
    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    tid, label = _require(paths, substrate, target, "initiating_event")
    entry = ETFrequencyEntry(target_id=tid, frequency=frequency, origin=origin, source_id=source_id,
                             verification=verification, notes=notes)
    store = get_frequencies(root=paths.root)
    store.entries = [e for e in store.entries if e.target_id != tid] + [entry]
    p = _path(paths, "frequency")
    _dump(p, store)
    sha = auto_commit(paths.root, subject=f"Set event-tree initiating frequency {label} = {frequency:g}/year",
                      body=f"target: {tid}\nfrequency: {frequency}\norigin: {origin}\nsource_id: {source_id}",
                      paths=[p])
    return entry, sha


# ── structure ────────────────────────────────────────────────────────


@dataclass
class ETProblem:
    target_id: str | None
    gap_type: str
    message: str


@dataclass
class Tree:
    labels: dict[str, str]
    elements: dict[str, str]
    structure: ETStructure
    probabilities: list[ETProbabilityEntry]
    frequency: ETFrequencyEntry | None
    initiator: str | None
    problems: list[ETProblem] = field(default_factory=list)

    def answer_text(self, steps) -> str:
        return ", ".join(f"{self.labels.get(s[0], s[0])}={s[1]}" for s in steps) or "(start)"


def _check_tree(tree: Tree) -> None:
    """The sequences must split cleanly at each heading and cover every branch exactly once."""
    seqs = [([(s.heading, s.answer) for s in q.path], q.end_state) for q in tree.structure.sequences]
    problems = tree.problems
    lab = tree.labels

    def check(group: list[tuple[list[tuple[str, str]], str]], prefix: list[tuple[str, str]]) -> None:
        if len(group) == 1 and not group[0][0]:
            return
        if any(not rest for rest, _ in group):
            problems.append(ETProblem(None, "et_overlap", f"After {tree.answer_text(prefix)}, one sequence ends "
                                                          "while others ask more questions."))
            return
        nexts = {rest[0][0] for rest, _ in group}
        if len(nexts) > 1:
            problems.append(ETProblem(None, "et_inconsistent", f"After {tree.answer_text(prefix)}, sequences ask "
                                      f"different next questions: {', '.join(sorted(lab.get(n, n) for n in nexts))}."))
            return
        h = nexts.pop()
        for ans in ANSWERS:
            sub = [(rest[1:], end) for rest, end in group if rest[0][1] == ans]
            branch = prefix + [(h, ans)]
            if not sub:
                problems.append(ETProblem(h, "et_missing_branch",
                                          f"No sequence for {tree.answer_text(branch)}: say where that branch ends."))
            else:
                check(sub, branch)

    if not seqs:
        problems.append(ETProblem(None, "et_no_sequences", "No sequences yet: add each path through the tree "
                                                           "and its end state (`latris et sequence`)."))
        return
    keys = [tuple(p) for p, _ in seqs]
    if len(set(keys)) != len(keys):
        problems.append(ETProblem(None, "et_duplicate", "Two sequences give the same answers."))
        return
    check(seqs, [])


def load_tree(*, root: Path | None = None) -> Tree:
    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    labels = {e.id: e.label for e in substrate.entities}
    el = {k: v for k, v in get_elements(root=paths.root).items() if k in labels}
    structure = get_structure(root=paths.root)
    of = defaultdict(list)
    for eid, t in el.items():
        of[t].append(eid)
    freq = next((f for f in get_frequencies(root=paths.root).entries if f.target_id in of["initiating_event"]), None)
    tree = Tree(labels=labels, elements=el, structure=structure,
                probabilities=[p for p in get_probabilities(root=paths.root).entries if p.target_id in el],
                frequency=freq, initiator=of["initiating_event"][0] if len(of["initiating_event"]) == 1 else None)
    problems = tree.problems
    if not of["initiating_event"]:
        problems.append(ETProblem(None, "et_no_initiator", "No initiating event: say what starts the sequence."))
    for x in of["initiating_event"][1:]:
        problems.append(ETProblem(x, "et_many_initiators", "An event tree has one initiating event; build one tree "
                                                           "per initiating event."))
    if not of["end_state"]:
        problems.append(ETProblem(None, "et_no_end_state", "No end state: say where the sequences can end."))
    order = structure.headings
    for h in order:
        if el.get(h) != "functional_event":
            problems.append(ETProblem(h if h in labels else None, "et_bad_heading",
                                      f"{labels.get(h, 'A removed factor')} is in the heading order but isn't a "
                                      "heading."))
    for h in of["functional_event"]:
        if h not in order:
            problems.append(ETProblem(h, "et_heading_unordered", "Not in the heading order (`latris et order`)."))
    pos = {h: i for i, h in enumerate(order)}
    bad = False
    for q in structure.sequences:
        idx = [pos.get(s.heading) for s in q.path]
        if el.get(q.end_state) != "end_state" or None in idx or idx != sorted(set(idx)):  # type: ignore[type-var]
            problems.append(ETProblem(q.end_state if q.end_state in labels else None, "et_bad_sequence",
                                      f"The sequence {tree.answer_text([(s.heading, s.answer) for s in q.path])} "
                                      "doesn't follow the heading order or doesn't end in an end state."))
            bad = True
    if not bad:
        _check_tree(tree)
    asked = {s.heading for q in structure.sequences for s in q.path}
    for h in order:
        if h in el and h not in asked and structure.sequences:
            problems.append(ETProblem(h, "et_heading_unused", "No sequence asks this heading."))
    reached = {q.end_state for q in structure.sequences}
    for e in of["end_state"]:
        if e not in reached and structure.sequences:
            problems.append(ETProblem(e, "et_end_state_unused", "No sequence ends here."))
    return tree


def structure_problems(*, root: Path | None = None) -> list[ETProblem]:
    return load_tree(root=root).problems


# ── analysis ─────────────────────────────────────────────────────────


def _lookup(tree: Tree, heading: str, prefix: list[tuple[str, str]]) -> ETProbabilityEntry | str | None:
    """The most specific probability entry that applies; a message if two disagree; None if none."""
    have = set(prefix)
    fits = [e for e in tree.probabilities
            if e.target_id == heading and all((c.heading, c.answer) in have for c in e.given)]
    if not fits:
        return None
    best = max(len(e.given) for e in fits)
    top = [e for e in fits if len(e.given) == best]
    if len({e.p_yes for e in top}) > 1:
        return "ambiguous"
    return top[0]


def _weak(entry) -> bool:
    return entry.verification != "human-verified" or entry.contested


def analyse(*, root: Path | None = None) -> dict[str, Any]:
    tree = load_tree(root=root)
    lab = tree.labels
    payload: dict[str, Any] = {
        "initiator": lab.get(tree.initiator) if tree.initiator else None,
        "headings": [lab.get(h, h) for h in tree.structure.headings],
        "counts": {t: sum(1 for v in tree.elements.values() if v == t) for t in ET_ELEMENTS},
        "problems": [{"label": lab.get(p.target_id or "", "(tree)"), "gap_type": p.gap_type, "message": p.message}
                     for p in tree.problems],
        "sequences": [], "end_states": [], "missing": [], "quantified": False,
        "frequency": None, "values": [],
    }
    if tree.problems:
        return payload
    f = tree.frequency
    payload["frequency"] = ({"per_year": f.frequency, "origin": f.origin, "source": f.source_id,
                             "weak": _weak(f)} if f else None)
    missing: dict[str, None] = {}
    used: dict[int, ETProbabilityEntry] = {}
    rows = []
    for n, q in enumerate(tree.structure.sequences, 1):
        prefix: list[tuple[str, str]] = []
        prob: float | None = 1.0
        weak_here = []
        for s in q.path:
            e = _lookup(tree, s.heading, prefix)
            if not isinstance(e, ETProbabilityEntry):
                note = " (two values disagree)" if e == "ambiguous" else ""
                missing[f"P({lab[s.heading]}=yes given {tree.answer_text(prefix)}){note}"] = None
                prob = None
            else:
                used[id(e)] = e
                if prob is not None:
                    prob *= e.p_yes if s.answer == "yes" else 1.0 - e.p_yes
                if _weak(e):
                    weak_here.append(lab[s.heading])
            prefix.append((s.heading, s.answer))
        rows.append({
            "n": n, "answers": [{"heading": lab[s.heading], "answer": s.answer} for s in q.path],
            "text": tree.answer_text([(s.heading, s.answer) for s in q.path]),
            "end_state": lab[q.end_state], "probability": prob,
            "frequency": prob * f.frequency if (prob is not None and f) else None,
            "unverified": sorted(set(weak_here)),
        })
    payload["sequences"] = rows
    payload["missing"] = list(missing)
    payload["values"] = [
        {"heading": lab[e.target_id], "given": tree.answer_text([(c.heading, c.answer) for c in e.given]),
         "p_yes": e.p_yes, "origin": e.origin, "source": e.source_id, "verification": e.verification,
         "weak": _weak(e)}
        for e in used.values()
    ]
    if not missing:
        payload["quantified"] = True
        total = math.fsum(r["probability"] for r in rows)
        payload["total_probability"] = total
        ends: dict[str, dict[str, Any]] = {}
        for r in rows:
            d = ends.setdefault(r["end_state"], {"end_state": r["end_state"], "probability": 0.0,
                                                 "frequency": 0.0 if f else None, "sequences": []})
            d["probability"] += r["probability"]
            if f:
                d["frequency"] += r["frequency"]
            d["sequences"].append(r["n"])
        for d in ends.values():
            top = max((r for r in rows if r["end_state"] == d["end_state"]), key=lambda r: r["probability"])
            d["dominant"] = {"n": top["n"], "text": top["text"], "share": top["probability"] / d["probability"]
                             if d["probability"] > 0 else None}
        payload["end_states"] = sorted(ends.values(), key=lambda d: -d["probability"])
    return payload


def describe(payload: dict[str, Any]) -> str:
    if payload["problems"]:
        return f"The event tree is incomplete ({len(payload['problems'])} structure problem(s))"
    n = len(payload["sequences"])
    c = payload["counts"]
    parts = [f"{payload['initiator']}: {c['functional_event']} heading(s), {n} sequence(s), "
             f"{c['end_state']} end state(s)"]
    if payload["quantified"]:
        fr = payload["frequency"]
        ends = ", ".join(
            f"{d['end_state']} {d['frequency']:.3g}/year" if fr else f"{d['end_state']} {d['probability']:.3g}"
            for d in payload["end_states"]
        )
        parts.append(("per year: " if fr else "probability given the initiating event: ") + ends)
    elif payload["missing"]:
        parts.append(f"{len(payload['missing'])} probability(ies) missing, so not quantified")
    return "; ".join(parts)


def record(payload: dict[str, Any], *, root: Path | None = None) -> tuple[str, str]:
    from latris.operations.analysis_results import record_result

    sha, run = record_result(
        kind="et-analysis",
        key="et-analysis",
        payload=payload,
        purpose="inference" if payload["quantified"] else "validation",
        algorithm="event tree: complete-tree check; sequence probabilities as products of (conditional) branch "
                  "probabilities; end-state totals",
        library_version="latris",
        summary=describe(payload),
        model_type=MODEL_TYPE,
        metrics={"sequences": len(payload["sequences"]), "end_states": len(payload["end_states"]),
                 "initiator_frequency": (payload["frequency"] or {}).get("per_year")},
        commit_subject="Analysis: event tree",
        root=root,
    )
    return sha, run.id
