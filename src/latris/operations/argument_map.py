"""Argument maps — does the conclusion stand, and what does it rest on?

An argument laid out as claims and the links between them (Toulmin 1958;
IBIS, Kunz & Rittel 1970; design in ``docs/engineering/ARGUMENT_MAP.md``):
one **conclusion**, the **claims** offered for and against it, and the
objections and answers to those. A link from a premise to a claim
**supports** or **attacks** it; premises sharing a **reason** work only
together (a linked argument), separate reasons each stand alone. A link can
carry its warrant and qualifier.

Evaluation is grounded labelling (Dung 1995) extended to support (bipolar
argumentation, Cayrol & Lagasquie-Schiex 2005), to a fixed point: a claim is
**in** when every attack on it fails and it has a reason whose premises are
all in — or is a premise taken as given (not argued further, not rejected,
its sources not against it); **out** when an attack on it succeeds, a person
rejected it, or every reason offered for it fails; otherwise **undecided**.
An open challenge on a link is an objection to the inference itself
(Pollock's undercutter): the reason or attack it carries counts for nothing
until the challenge is resolved. A claim's grounds are its ordinary
citations, read as checked, cited, contested or unsourced.

The analysis gives the conclusion's status and the reasons it stands on,
unanswered objections, the **linchpins** — premises whose rejection would
stop it standing — and what the premises rest on: checked sources, unchecked
ones, a person's acceptance, or nothing.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from latris.operations._resolve import resolve_target
from latris.operations._view_store import ViewStore, replace_entry, resolve_factor
from latris.repo.project import require_project
from latris.repo.yaml_io import load_model
from latris.schema import Substrate
from latris.schema.argument_map import (
    ARGUMENT_ELEMENTS,
    QUALIFIERS,
    RELATIONS,
    ArgumentClaimEntry,
    ArgumentClaimSet,
    ArgumentLinkEntry,
    ArgumentLinkSet,
)
from latris.schema.common import ProvenanceOrigin, ProvenanceVerification

MODEL_TYPE = "argument_map"
IN, OUT, UNDECIDED = "in", "out", "undecided"
OPEN_CHALLENGE = ("open", "unresolved")
_UNSET = object()

_store = ViewStore(MODEL_TYPE, ARGUMENT_ELEMENTS)


def get_elements(*, root: Path | None = None) -> dict[str, str]:
    return _store.roles(root)


def get_links(*, root: Path | None = None) -> ArgumentLinkSet:
    return _store.load(root, "link", ArgumentLinkSet)


def get_claims(*, root: Path | None = None) -> ArgumentClaimSet:
    return _store.load(root, "claim", ArgumentClaimSet)


# ── writes ───────────────────────────────────────────────────────────


def set_element(target: str, element: str, *, root: Path | None = None) -> tuple[str, str]:
    from latris.operations.view_roles import set_role

    if element not in ARGUMENT_ELEMENTS:
        raise ValueError(f"{element!r} is not an argument-map element. Elements: {', '.join(ARGUMENT_ELEMENTS)}")
    return set_role(target, MODEL_TYPE, element, root=root)


def set_link(
    link: str,
    *,
    relation: str | object = _UNSET,
    reason: str | None | object = _UNSET,
    warrant: str | None | object = _UNSET,
    qualifier: str | None | object = _UNSET,
    notes: str | None | object = _UNSET,
    origin: ProvenanceOrigin | object = _UNSET,
    source_id: str | None | object = _UNSET,
    verification: ProvenanceVerification | object = _UNSET,
    root: Path | None = None,
) -> tuple[ArgumentLinkEntry, str]:
    """Say how a premise bears on a claim ('Premise -> Claim'): supports or attacks, the reason it belongs to,
    its warrant and qualifier. Only what's given changes."""
    paths = require_project(root)
    sub = load_model(Substrate, paths.conceptual_yaml)
    eid = resolve_target(link, sub)
    e = next((x for x in sub.edges if x.id == eid), None)
    if e is None:
        raise ValueError(f"{link!r} is a factor; a link is written 'Premise -> Claim'")
    el = get_elements(root=paths.root)
    labels = {x.id: x.label for x in sub.entities}
    for end in (e.from_id, e.to_id):
        if el.get(end) not in ("claim", "conclusion"):
            raise ValueError(f"{labels[end]} isn't a claim in the argument map (`latris argument element "
                             f"<factor> claim`)")
    if el.get(e.from_id) == "conclusion":
        raise ValueError(f"{labels[e.from_id]} is the conclusion: it is argued for, not offered for another claim")
    if relation is not _UNSET and relation not in RELATIONS:
        raise ValueError(f"{relation!r} isn't a relation: {' or '.join(RELATIONS)}")
    if qualifier not in (_UNSET, None) and qualifier not in QUALIFIERS:
        raise ValueError(f"{qualifier!r} isn't a qualifier: {', '.join(QUALIFIERS)}")
    store = get_links(root=paths.root)
    current = next((x for x in store.entries if x.target_id == eid), None)
    given = {"relation": relation, "reason": reason, "warrant": warrant, "qualifier": qualifier, "notes": notes,
             "origin": origin, "source_id": source_id, "verification": verification}
    changed = {k: v for k, v in given.items() if v is not _UNSET}
    if not changed:
        raise ValueError("nothing to set: give a relation, reason, warrant, qualifier, notes or source")
    entry = ArgumentLinkEntry.model_validate({**(current.model_dump() if current else {"target_id": eid}), **changed})
    replace_entry(store, entry)
    sha = _store.save(paths, "link", store,
                      subject=f"Argument: {labels[e.from_id]} {entry.relation} {labels[e.to_id]}"
                              + (f" ({', '.join(k for k in changed if k != 'relation')})"
                                 if set(changed) - {"relation"} else ""),
                      body=f"edge: {eid}\n" + "\n".join(f"{k}: {v}" for k, v in changed.items()))
    return entry, sha


def set_claim(
    target: str,
    *,
    assessment: str | None | object = _UNSET,
    rationale: str | None | object = _UNSET,
    origin: ProvenanceOrigin | object = _UNSET,
    source_id: str | None | object = _UNSET,
    verification: ProvenanceVerification | object = _UNSET,
    root: Path | None = None,
) -> tuple[ArgumentClaimEntry, str]:
    """A person's assessment of a claim — accepted or rejected (None: not assessed) — with the rationale."""
    paths = require_project(root)
    tid, label = resolve_factor(paths, target, link_error=f"{target!r} is a link; assess a claim")
    if get_elements(root=paths.root).get(tid) not in ("claim", "conclusion"):
        raise ValueError(f"{label} isn't a claim in the argument map")
    if assessment not in (_UNSET, None, "accepted", "rejected"):
        raise ValueError("an assessment is 'accepted' or 'rejected' (or none, to clear it)")
    store = get_claims(root=paths.root)
    current = next((x for x in store.entries if x.target_id == tid), None)
    given = {"assessment": assessment, "rationale": rationale, "origin": origin, "source_id": source_id,
             "verification": verification}
    changed = {k: v for k, v in given.items() if v is not _UNSET}
    if not changed:
        raise ValueError("nothing to set: give an assessment, rationale or source")
    entry = ArgumentClaimEntry.model_validate({**(current.model_dump() if current else {"target_id": tid}),
                                               **changed})
    replace_entry(store, entry)
    sha = _store.save(paths, "claim", store, subject=f"Argument: {label} {entry.assessment or 'not assessed'}",
                      body=f"target: {tid}\n" + "\n".join(f"{k}: {v}" for k, v in changed.items()))
    return entry, sha


# ── structure ────────────────────────────────────────────────────────


@dataclass
class AMProblem:
    target_id: str | None
    gap_type: str
    message: str


@dataclass
class Link:
    edge: str
    premise: str
    claim: str
    entry: ArgumentLinkEntry

    @property
    def relation(self) -> str:
        return self.entry.relation

    @property
    def reason(self) -> str:
        return self.entry.reason or f"#{self.edge}"


@dataclass
class Map:
    labels: dict[str, str]
    kind: dict[str, str]  # entity → element
    links: list[Link]
    assessment: dict[str, ArgumentClaimEntry]
    challenged: set[str]  # edges with an open challenge
    evidence: dict[str, str]  # claim → checked | cited | contested | none
    conclusion: str | None = None
    question: str | None = None
    problems: list[AMProblem] = field(default_factory=list)

    @property
    def claims(self) -> list[str]:
        return sorted((c for c, k in self.kind.items() if k in ("claim", "conclusion")), key=lambda c: self.labels[c])

    def reasons(self, claim: str) -> dict[str, list[Link]]:
        out: dict[str, list[Link]] = defaultdict(list)
        for ln in self.links:
            if ln.claim == claim and ln.relation == "supports":
                out[ln.reason].append(ln)
        return dict(out)

    def attacks(self, claim: str) -> list[Link]:
        return [ln for ln in self.links if ln.claim == claim and ln.relation == "attacks"]


def _evidence(paths, ids: list[str]) -> dict[str, str]:
    from latris.schema import EvidenceLinkSet

    ev = load_model(EvidenceLinkSet, paths.evidence_links_yaml) if paths.evidence_links_yaml.exists() else None
    out = {}
    for i in ids:
        links = [e for e in (ev.entries if ev else []) if e.target_id == i]
        if any(e.is_against for e in links):
            out[i] = "contested"
        elif any(e.support_verdict == "supports" for e in links):
            out[i] = "checked"
        elif links:
            out[i] = "cited"
        else:
            out[i] = "none"
    return out


def load(*, root: Path | None = None) -> Map:
    from latris.operations.challenges import list_challenges

    paths = require_project(root)
    sub = load_model(Substrate, paths.conceptual_yaml)
    labels = {e.id: e.label for e in sub.entities}
    kind = {k: v for k, v in get_elements(root=paths.root).items() if k in labels}
    entries = {x.target_id: x for x in get_links(root=paths.root).entries}
    links = [Link(e.id, e.from_id, e.to_id, entries.get(e.id) or ArgumentLinkEntry(target_id=e.id))
             for e in sub.edges
             if kind.get(e.from_id) in ("claim", "conclusion") and kind.get(e.to_id) in ("claim", "conclusion")]
    challenged = {c.target_id for c in list_challenges(root=paths.root)
                  if c.state in OPEN_CHALLENGE and c.target_id}
    m = Map(labels=labels, kind=kind, links=links,
            assessment={x.target_id: x for x in get_claims(root=paths.root).entries if x.target_id in kind},
            challenged=challenged, evidence=_evidence(paths, sorted(kind)))
    P = m.problems
    conclusions = sorted((c for c, k in kind.items() if k == "conclusion"), key=lambda c: labels[c])
    questions = sorted((c for c, k in kind.items() if k == "question"), key=lambda c: labels[c])
    if not conclusions:
        P.append(AMProblem(None, "am_no_conclusion", "No conclusion: say what is being argued for "
                                                     "(`latris argument element <factor> conclusion`)."))
    elif len(conclusions) > 1:
        P.append(AMProblem(conclusions[1], "am_many_conclusions",
                           "More than one conclusion; map one argument at a time (make the others claims)."))
    else:
        m.conclusion = conclusions[0]
        if not any(ln.claim == m.conclusion for ln in links):
            P.append(AMProblem(m.conclusion, "am_no_reasons", "Nothing argues for or against the conclusion yet: "
                                                              "link a premise to it."))
        if any(ln.premise == m.conclusion for ln in links):
            P.append(AMProblem(m.conclusion, "am_conclusion_not_top",
                               "The conclusion is offered for another claim; it should be what the argument ends in."))
    if len(questions) > 1:
        P.append(AMProblem(questions[1], "am_many_questions", "More than one question; keep the one the conclusion "
                                                              "answers."))
    m.question = questions[0] if questions else None
    return m


def structure_problems(*, root: Path | None = None) -> list[AMProblem]:
    return load(root=root).problems


# ── evaluation ───────────────────────────────────────────────────────


def _given(m: Map, claim: str) -> bool:
    """A premise the map doesn't argue further: no reason is offered for it."""
    return not m.reasons(claim)


def label(m: Map, rejected: frozenset[str] = frozenset()) -> dict[str, str]:
    """Grounded labelling with support: every claim in, out or undecided (see the module docstring)."""
    lab: dict[str, str | None] = dict.fromkeys(m.claims)

    def decide(c: str) -> str | None:
        a = m.assessment.get(c)
        if c in rejected or (a and a.assessment == "rejected"):
            return OUT
        attacks = [ln for ln in m.attacks(c) if ln.edge not in m.challenged]
        if any(lab[ln.premise] == IN for ln in attacks):
            return OUT
        accepted = bool(a and a.assessment == "accepted")
        groups = m.reasons(c)
        if groups and not accepted:
            ok = [g for g in groups.values()
                  if not any(ln.edge in m.challenged for ln in g) and all(lab[ln.premise] == IN for ln in g)]
            failed = [g for g in groups.values()
                      if any(ln.edge in m.challenged for ln in g) or any(lab[ln.premise] == OUT for ln in g)]
            if len(failed) == len(groups):
                return OUT
            supported = bool(ok)
        else:
            supported = accepted or m.evidence.get(c) != "contested"
        if supported and all(lab[ln.premise] == OUT for ln in attacks):
            return IN
        return None

    changed = True
    while changed:
        changed = False
        for c in m.claims:
            if lab[c] is None:
                new = decide(c)
                if new is not None:
                    lab[c] = new
                    changed = True
    return {c: v or UNDECIDED for c, v in lab.items()}


def _under(m: Map, top: str) -> list[str]:
    """Every claim bearing on ``top``, directly or through others (support or attack), nearest first."""
    seen, order, frontier = {top}, [], [top]
    while frontier:
        nxt = []
        for c in frontier:
            for ln in m.links:
                if ln.claim == c and ln.premise not in seen:
                    seen.add(ln.premise)
                    order.append(ln.premise)
                    nxt.append(ln.premise)
        frontier = nxt
    return order


def _sides(m: Map, top: str) -> dict[str, bool]:
    """Which side of the argument each claim is on: True for the conclusion and claims that help it (what
    supports it, answers to objections), False for objections and what supports them. Nearest link wins."""
    side = {top: True}
    frontier = [top]
    while frontier:
        nxt = []
        for c in frontier:
            for ln in m.links:
                if ln.claim == c and ln.premise not in side:
                    side[ln.premise] = side[c] if ln.relation == "supports" else not side[c]
                    nxt.append(ln.premise)
        frontier = nxt
    return side


def _rests_on(m: Map, lab: dict[str, str], top: str) -> list[str]:
    """The premises taken as given that ``top`` stands on: through reasons that hold, and through the
    answers that keep its objections out (an objection to anything on the way that is defeated by a claim
    that stands: without that answer the objection would stand instead)."""
    out, seen = [], set()

    def walk(c: str) -> None:
        if c in seen:
            return
        seen.add(c)
        groups = m.reasons(c)
        a = m.assessment.get(c)
        if not groups or (a and a.assessment == "accepted"):
            out.append(c)
        else:
            for g in groups.values():
                if all(lab[ln.premise] == IN for ln in g) and not any(ln.edge in m.challenged for ln in g):
                    for ln in g:
                        walk(ln.premise)
        for objection in m.attacks(c):
            if objection.edge in m.challenged or lab[objection.premise] != OUT:
                continue
            for answer in m.attacks(objection.premise):
                if answer.edge not in m.challenged and lab[answer.premise] == IN:
                    walk(answer.premise)

    walk(top)
    return out


def analyse(*, root: Path | None = None) -> dict[str, Any]:
    m = load(root=root)
    lb = m.labels
    payload: dict[str, Any] = {
        "problems": [{"label": lb.get(p.target_id or "", "(map)"), "gap_type": p.gap_type, "message": p.message}
                     for p in m.problems],
    }
    if m.problems:
        return payload
    top = m.conclusion
    lab = label(m)
    under = _under(m, top)  # type: ignore[arg-type]
    scope = [top, *under]

    def basis(c: str) -> str:
        a = m.assessment.get(c)
        if a and a.assessment:
            return a.assessment
        return m.evidence.get(c, "none")

    reasons = []
    for c in scope:
        for name, g in sorted(m.reasons(c).items()):
            challenged = [ln for ln in g if ln.edge in m.challenged]
            status = ("challenged" if challenged else "holds" if all(lab[ln.premise] == IN for ln in g)
                      else "fails" if any(lab[ln.premise] == OUT for ln in g) else "undecided")
            reasons.append({"claim": lb[c], "reason": None if name.startswith("#") else name,
                            "premises": [lb[ln.premise] for ln in g], "status": status,
                            "warrant": next((ln.entry.warrant for ln in g if ln.entry.warrant), None),
                            "qualifier": next((ln.entry.qualifier for ln in g if ln.entry.qualifier), None)})
    side = _sides(m, top)  # type: ignore[arg-type]
    objections, answers = [], []
    for c in scope:
        for ln in m.attacks(c):
            row = {"objection": lb[ln.premise], "against": lb[c], "status": lab[ln.premise],
                   "challenged": ln.edge in m.challenged,
                   "answered": lab[ln.premise] == OUT or ln.edge in m.challenged}
            (objections if side.get(c, True) else answers).append(row)
    rests = _rests_on(m, lab, top) if lab[top] == IN else []  # type: ignore[index]
    linchpins = []
    if lab[top] == IN:  # type: ignore[index]
        for c in rests:
            if c != top and label(m, frozenset({c}))[top] != IN:  # type: ignore[index]
                linchpins.append({"claim": lb[c], "basis": basis(c)})
    by_basis: dict[str, list[str]] = {k: [] for k in ("checked", "cited", "accepted", "none", "contested")}
    for c in rests:
        by_basis.setdefault(basis(c), []).append(lb[c])
    payload.update(
        conclusion=lb[top], question=lb[m.question] if m.question else None,  # type: ignore[index]
        status=lab[top],  # type: ignore[index]
        claims=[{"claim": lb[c], "role": m.kind[c], "status": lab[c], "given": _given(m, c), "basis": basis(c)}
                for c in scope],
        reasons=reasons, objections=objections, answers=answers,
        unanswered=[o for o in objections if not o["answered"] and o["status"] == IN],
        linchpins=linchpins, rests_on=by_basis,
        no_warrant=[f"{r['claim']} ← {' + '.join(r['premises'])}" for r in reasons if not r["warrant"]],
        challenged=[f"{lb[ln.premise]} → {lb[ln.claim]}" for ln in m.links if ln.edge in m.challenged],
        outside=sorted(lb[c] for c in m.claims if c not in scope),
        unverified_links=sum(1 for ln in m.links if ln.entry.verification != "human-verified"),
        ai_links=sum(1 for ln in m.links if ln.entry.origin == "ai-proposed"),
    )
    return payload


_STATUS_WORDS = {IN: "stands", OUT: "is defeated", UNDECIDED: "is undecided"}


def describe(p: dict[str, Any]) -> str:
    if p["problems"]:
        return f"The argument map is incomplete ({len(p['problems'])} structure problem(s))"
    s = f"{p['conclusion']} {_STATUS_WORDS[p['status']]}"
    held = [r for r in p["reasons"] if r["claim"] == p["conclusion"] and r["status"] == "holds"]
    if p["status"] == IN:
        s += f" on {len(held)} reason(s)"
        rests = p["rests_on"]
        weak = len(rests.get("none", [])) + len(rests.get("cited", []))
        if weak:
            s += (f"; {weak} premise(s) it rests on {'has' if weak == 1 else 'have'} no checked source")
        if p["linchpins"]:
            s += f"; {len(p['linchpins'])} linchpin(s): {', '.join(x['claim'] for x in p['linchpins'][:3])}"
        if p["unanswered"]:
            s += "; unanswered objection(s), which defeat other reasons: " + "; ".join(
                f"{o['objection']} (against {o['against']})" for o in p["unanswered"][:3])
    elif p["status"] == OUT:
        top = next(c for c in p["claims"] if c["claim"] == p["conclusion"])
        direct = [o for o in p["unanswered"] if o["against"] == p["conclusion"]]
        if top["basis"] == "rejected":
            s += ": a person rejected it"
        elif direct:
            s += ": an objection to it stands — " + "; ".join(o["objection"] for o in direct[:3])
        else:
            s += ": every reason offered for it fails"
        rest = [o for o in p["unanswered"] if o not in direct]
        if rest:
            s += "; unanswered objection(s): " + "; ".join(f"{o['objection']} (against {o['against']})"
                                                          for o in rest[:3])
    else:
        open_ = [c["claim"] for c in p["claims"] if c["status"] == UNDECIDED and c["claim"] != p["conclusion"]]
        if open_:
            s += f": it depends on unsettled claims ({', '.join(open_[:3])})"
    return s


def record(payload: dict[str, Any], *, root: Path | None = None) -> tuple[str, str]:
    from latris.operations.analysis_results import record_result

    sha, run = record_result(
        kind="argument-analysis",
        key="argument-analysis",
        payload=payload,
        purpose="inference",
        algorithm="grounded labelling with support (Dung 1995; Cayrol & Lagasquie-Schiex 2005); open challenges "
                  "on links as undercutters; leave-one-out linchpins",
        library_version="latris",
        summary=describe(payload),
        model_type=MODEL_TYPE,
        metrics={"status": payload.get("status"), "linchpins": len(payload.get("linchpins", [])),
                 "unanswered": len(payload.get("unanswered", []))},
        commit_subject="Analysis: argument map",
        root=root,
    )
    return sha, run.id
