"""Analysis of competing hypotheses — which explanation does the evidence fail to rule out?

Heuer's method (Heuer 1999, *Psychology of Intelligence Analysis*, ch. 8;
Heuer & Pherson 2015) for keeping several explanations in play and judging
them against all the evidence at once:

- list the **hypotheses** and the **evidence** (facts, reports, arguments,
  absences);
- rate each piece of evidence against each hypothesis — very consistent (CC),
  consistent (C), neutral or not applicable (N), inconsistent (I), very
  inconsistent (II);
- weigh each piece by its **credibility** and **relevance**;
- favour the hypothesis with the **least evidence against it**, not the most
  evidence for it: evidence consistent with every hypothesis proves nothing,
  and one solid inconsistency can rule a hypothesis out.

The analysis ranks hypotheses by weighted inconsistency, flags evidence that
doesn't discriminate (rated the same against every hypothesis), and finds the
**linchpins** — items without which the lead would change or be tied —
then says whether each linchpin's own sources have been checked (the item's
citations, ``latris evidence``). Ratings are judgements; each keeps its
reasoning and provenance.

The weights are this module's stated convention, not Heuer's: credibility and
relevance high 1.0, medium 0.7, low 0.4, multiplied; an inconsistency counts
1, a strong one 2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from latris.operations._resolve import resolve_target
from latris.operations.commit import auto_commit
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_model, load_model
from latris.schema import Substrate
from latris.schema.ach import ACH_ELEMENTS, RATINGS, ACHItemEntry, ACHItemSet, ACHRatingEntry, ACHRatingSet
from latris.schema.common import ProvenanceOrigin, ProvenanceVerification

MODEL_TYPE = "ach"
LEVEL_WEIGHT = {"high": 1.0, "medium": 0.7, "low": 0.4}
INCONSISTENCY = {"CC": 0, "C": 0, "N": 0, "I": 1, "II": 2}
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
    return {e.target_id: e.value for e in load_model(RoleSet, p).entries if e.value in ACH_ELEMENTS}


def get_ratings(*, root: Path | None = None) -> ACHRatingSet:
    return _load(_path(require_project(root), "rating"), ACHRatingSet)


def get_items(*, root: Path | None = None) -> ACHItemSet:
    return _load(_path(require_project(root), "item"), ACHItemSet)


# ── writes ───────────────────────────────────────────────────────────


def _require(paths, target: str, element: str) -> tuple[str, str]:
    substrate = load_model(Substrate, paths.conceptual_yaml)
    tid = resolve_target(target, substrate)
    label = next((e.label for e in substrate.entities if e.id == tid), None)
    if label is None:
        raise ValueError(f"{target!r} is a link; ACH hypotheses and evidence items are factors")
    got = get_elements(root=paths.root).get(tid)
    if got != element:
        raise ValueError(f"{label} is {('a ' + got.replace('_', ' ')) if got else 'not in the ACH'}, not a "
                         f"{element.replace('_', ' ')} (`latris ach element <factor> {element}`)")
    return tid, label


def set_element(target: str, element: str, *, root: Path | None = None) -> tuple[str, str]:
    from latris.operations.view_roles import set_role

    if element not in ACH_ELEMENTS:
        raise ValueError(f"{element!r} is not an ACH element. Elements: {', '.join(ACH_ELEMENTS)}")
    return set_role(target, MODEL_TYPE, element, root=root)


def set_item(
    target: str,
    *,
    credibility: str | object = _UNSET,
    relevance: str | object = _UNSET,
    notes: str | None | object = _UNSET,
    origin: ProvenanceOrigin | object = _UNSET,
    source_id: str | None | object = _UNSET,
    verification: ProvenanceVerification | object = _UNSET,
    root: Path | None = None,
) -> tuple[ACHItemEntry, str]:
    """Set an evidence item's credibility and relevance; only the fields given change."""
    paths = require_project(root)
    tid, label = _require(paths, target, "evidence_item")
    store = get_items(root=paths.root)
    current = next((e for e in store.entries if e.target_id == tid), None)
    given = {"credibility": credibility, "relevance": relevance, "notes": notes, "origin": origin,
             "source_id": source_id, "verification": verification}
    changed = {k: v for k, v in given.items() if v is not _UNSET}
    if not changed:
        raise ValueError("nothing to set: give a credibility, relevance, notes or source")
    entry = ACHItemEntry.model_validate({**(current.model_dump() if current else {"target_id": tid}), **changed})
    store.entries = [e for e in store.entries if e.target_id != tid] + [entry]
    p = _path(paths, "item")
    _dump(p, store)
    sha = auto_commit(paths.root, subject=f"Set ACH evidence item {label}: {', '.join(changed)}",
                      body=f"target: {tid}\n" + "\n".join(f"{k}: {v}" for k, v in changed.items()), paths=[p])
    return entry, sha


def set_rating(
    item: str,
    hypothesis: str,
    rating: str,
    *,
    rationale: str | None = None,
    origin: ProvenanceOrigin = "human-direct",
    verification: ProvenanceVerification = "unverified",
    root: Path | None = None,
) -> tuple[ACHRatingEntry, str]:
    """Rate how an evidence item bears on a hypothesis: CC, C, N, I or II."""
    paths = require_project(root)
    rating = rating.upper()
    if rating not in RATINGS:
        raise ValueError(f"{rating!r} isn't a rating: CC (very consistent), C, N (neutral / not applicable), I, "
                         "II (very inconsistent)")
    iid, ilabel = _require(paths, item, "evidence_item")
    hid, hlabel = _require(paths, hypothesis, "hypothesis")
    entry = ACHRatingEntry(target_id=iid, hypothesis=hid, rating=rating, rationale=rationale,  # type: ignore[arg-type]
                           origin=origin, verification=verification)
    store = get_ratings(root=paths.root)
    store.entries = [e for e in store.entries if (e.target_id, e.hypothesis) != (iid, hid)] + [entry]
    p = _path(paths, "rating")
    _dump(p, store)
    sha = auto_commit(paths.root, subject=f"Rated ACH {ilabel} against {hlabel}: {rating}",
                      body=f"item: {iid}\nhypothesis: {hid}\nrating: {rating}\norigin: {origin}\n"
                           f"rationale: {rationale or ''}", paths=[p])
    return entry, sha


# ── structure ────────────────────────────────────────────────────────


@dataclass
class ACHProblem:
    target_id: str | None
    gap_type: str
    message: str


@dataclass
class Matrix:
    labels: dict[str, str]
    hypotheses: list[str]
    items: list[str]
    ratings: dict[tuple[str, str], ACHRatingEntry]
    weights: dict[str, ACHItemEntry]
    problems: list[ACHProblem] = field(default_factory=list)


def load(*, root: Path | None = None) -> Matrix:
    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    labels = {e.id: e.label for e in substrate.entities}
    el = {k: v for k, v in get_elements(root=paths.root).items() if k in labels}
    hyps = sorted((k for k, v in el.items() if v == "hypothesis"), key=lambda k: labels[k])
    items = sorted((k for k, v in el.items() if v == "evidence_item"), key=lambda k: labels[k])
    ratings = {(r.target_id, r.hypothesis): r for r in get_ratings(root=paths.root).entries
               if r.target_id in items and r.hypothesis in hyps}
    weights = {i.target_id: i for i in get_items(root=paths.root).entries if i.target_id in items}
    m = Matrix(labels=labels, hypotheses=hyps, items=items, ratings=ratings, weights=weights)
    if len(hyps) < 2:
        m.problems.append(ACHProblem(None, "ach_too_few_hypotheses", "ACH weighs at least two competing hypotheses."))
    if not items:
        m.problems.append(ACHProblem(None, "ach_no_items", "No evidence items: list what you know (facts, reports, "
                                                           "arguments, absences)."))
    for i in items:
        missing = [labels[h] for h in hyps if (i, h) not in ratings]
        if missing:
            m.problems.append(ACHProblem(i, "ach_missing_rating", f"Not rated against {', '.join(missing)}."))
    return m


def structure_problems(*, root: Path | None = None) -> list[ACHProblem]:
    return load(root=root).problems


# ── analysis ─────────────────────────────────────────────────────────


def item_weight(entry: ACHItemEntry | None) -> float:
    e = entry or ACHItemEntry(target_id="-")
    return LEVEL_WEIGHT[e.credibility] * LEVEL_WEIGHT[e.relevance]


def scores(hyps: list[str], items: list[str], rating: dict[tuple[str, str], str],
           weight: dict[str, float]) -> dict[str, float]:
    """Weighted inconsistency per hypothesis (lower: less evidence against it)."""
    return {h: sum(INCONSISTENCY[rating[(i, h)]] * weight[i] for i in items) for h in hyps}


def leaders(score: dict[str, float]) -> list[str]:
    low = min(score.values())
    return sorted(h for h, s in score.items() if abs(s - low) < 1e-9)


def _sources(paths, items: list[str]) -> dict[str, str]:
    """Each item's evidence status from its own citations: checked, cited, contested or none."""
    from latris.schema import EvidenceLinkSet

    ev = load_model(EvidenceLinkSet, paths.evidence_links_yaml) if paths.evidence_links_yaml.exists() else None
    out = {}
    for i in items:
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


def analyse(*, root: Path | None = None) -> dict[str, Any]:
    paths = require_project(root)
    m = load(root=paths.root)
    lab = m.labels
    payload: dict[str, Any] = {
        "hypotheses": [lab[h] for h in m.hypotheses], "items": [lab[i] for i in m.items],
        "problems": [{"label": lab.get(p.target_id or "", "(matrix)"), "gap_type": p.gap_type, "message": p.message}
                     for p in m.problems],
    }
    if m.problems:
        return payload
    rating = {k: r.rating for k, r in m.ratings.items()}
    weight = {i: item_weight(m.weights.get(i)) for i in m.items}
    score = scores(m.hypotheses, m.items, rating, weight)
    lead = leaders(score)
    srcs = _sources(paths, m.items)
    linchpins = []
    for i in m.items:
        rest = [x for x in m.items if x != i]
        if not rest:
            continue
        if leaders(scores(m.hypotheses, rest, rating, weight)) != lead:
            linchpins.append(i)
    non_diagnostic = [i for i in m.items if len({rating[(i, h)] for h in m.hypotheses}) == 1]
    diag = {i: max(INCONSISTENCY[rating[(i, h)]] for h in m.hypotheses)
            - min(INCONSISTENCY[rating[(i, h)]] for h in m.hypotheses) for i in m.items}
    payload.update(
        ranking=[{"hypothesis": lab[h], "inconsistency": score[h],
                  "against": [lab[i] for i in m.items if INCONSISTENCY[rating[(i, h)]] > 0],
                  "consistent": sum(1 for i in m.items if rating[(i, h)] in ("C", "CC"))}
                 for h in sorted(m.hypotheses, key=lambda h: (score[h], lab[h]))],
        leading=[lab[h] for h in lead],
        matrix=[{"item": lab[i], "weight": weight[i],
                 "credibility": (m.weights.get(i) or ACHItemEntry(target_id="-")).credibility,
                 "relevance": (m.weights.get(i) or ACHItemEntry(target_id="-")).relevance,
                 "sources": srcs[i], "diagnosticity": diag[i],
                 "ratings": {lab[h]: rating[(i, h)] for h in m.hypotheses}} for i in m.items],
        non_diagnostic=[lab[i] for i in non_diagnostic],
        linchpins=[{"item": lab[i], "sources": srcs[i], "credibility":
                    (m.weights.get(i) or ACHItemEntry(target_id="-")).credibility} for i in linchpins],
        unverified_ratings=sum(1 for r in m.ratings.values() if r.verification != "human-verified"),
        ai_ratings=sum(1 for r in m.ratings.values() if r.origin == "ai-proposed"),
    )
    return payload


def describe(p: dict[str, Any]) -> str:
    if p["problems"]:
        return f"The ACH matrix is incomplete ({len(p['problems'])} structure problem(s))"
    r = p["ranking"]
    lead = p["leading"]
    head = (f"{lead[0]} has the least evidence against it ({r[0]['inconsistency']:.2f})" if len(lead) == 1
            else f"{' and '.join(lead)} tie with the least evidence against them ({r[0]['inconsistency']:.2f})")
    parts = [head, "then " + ", ".join(f"{x['hypothesis']} ({x['inconsistency']:.2f})" for x in r[len(lead):])
             if len(r) > len(lead) else ""]
    if p["linchpins"]:
        parts.append(f"{len(p['linchpins'])} linchpin item(s)")
    if p["non_diagnostic"]:
        parts.append(f"{len(p['non_diagnostic'])} item(s) that don't discriminate")
    return "; ".join(x for x in parts if x)


def record(payload: dict[str, Any], *, root: Path | None = None) -> tuple[str, str]:
    from latris.operations.analysis_results import record_result

    sha, run = record_result(
        kind="ach-analysis",
        key="ach-analysis",
        payload=payload,
        purpose="inference",
        algorithm="analysis of competing hypotheses: weighted inconsistency (credibility x relevance; I=1, II=2), "
                  "diagnosticity, leave-one-out linchpins",
        library_version="latris",
        summary=describe(payload),
        model_type=MODEL_TYPE,
        metrics={"hypotheses": len(payload["hypotheses"]), "items": len(payload["items"]),
                 "leading": payload.get("leading"), "linchpins": len(payload.get("linchpins", []))},
        commit_subject="Analysis: competing hypotheses",
        root=root,
    )
    return sha, run.id
