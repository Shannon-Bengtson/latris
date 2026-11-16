"""Multi-criteria decision analysis — which option, against weighted criteria, and how firm is that?

The additive value model of decision analysis (Keeney & Raiffa 1976; Belton &
Stewart 2002), in the form public-sector options appraisal uses (UK DCLG 2009,
*Multi-criteria analysis: a manual*):

- each option's score on each criterion becomes a **value** from 0 (the
  criterion's worst) to 1 (its best) on a linear scale;
- each criterion has a **swing weight**: how much moving from its worst to
  its best matters compared with the other criteria's swings;
- an option's overall value is the weighted sum (0–100 points).

The analysis ranks the options and shows how much each criterion contributes,
which options are **dominated** (no better anywhere, worse somewhere), and —
because the weights are judgements — how far each weight would have to move
before the top choice changes (scores are linear in any one weight when the
others keep their proportions, so the crossing points are exact). It also
names the scores the winning margin rests on that nobody has verified.

Options and criteria are substrate entities with an ``mcda`` role; the
numbers are stored with provenance (``schema/mcda.py``).
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
from latris.schema.common import ProvenanceOrigin, ProvenanceVerification
from latris.schema.mcda import (
    MCDA_ELEMENTS,
    MCDACriterionEntry,
    MCDACriterionSet,
    MCDAScoreEntry,
    MCDAScoreSet,
)

MODEL_TYPE = "mcda"
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
    return {e.target_id: e.value for e in load_model(RoleSet, p).entries if e.value in MCDA_ELEMENTS}


def get_criteria(*, root: Path | None = None) -> MCDACriterionSet:
    return _load(_path(require_project(root), "criterion"), MCDACriterionSet)


def get_scores(*, root: Path | None = None) -> MCDAScoreSet:
    return _load(_path(require_project(root), "score"), MCDAScoreSet)


# ── writes ───────────────────────────────────────────────────────────


def _require(paths, target: str, element: str) -> tuple[str, str]:
    substrate = load_model(Substrate, paths.conceptual_yaml)
    tid = resolve_target(target, substrate)
    label = next((e.label for e in substrate.entities if e.id == tid), None)
    if label is None:
        raise ValueError(f"{target!r} is a link; MCDA options and criteria are factors")
    got = get_elements(root=paths.root).get(tid)
    if got != element:
        raise ValueError(f"{label} is {('an ' + got) if got else 'not in the MCDA'}, not a {element} "
                         f"(`latris mcda element <factor> {element}`)")
    return tid, label


def set_element(target: str, element: str, *, root: Path | None = None) -> tuple[str, str]:
    from latris.operations.view_roles import set_role

    if element not in MCDA_ELEMENTS:
        raise ValueError(f"{element!r} is not an MCDA element. Elements: {', '.join(MCDA_ELEMENTS)}")
    return set_role(target, MODEL_TYPE, element, root=root)


def set_criterion(
    target: str,
    *,
    weight: float | object = _UNSET,
    direction: str | object = _UNSET,
    worst: float | None | object = _UNSET,
    best: float | None | object = _UNSET,
    units: str | None | object = _UNSET,
    notes: str | None | object = _UNSET,
    origin: ProvenanceOrigin | object = _UNSET,
    source_id: str | None | object = _UNSET,
    verification: ProvenanceVerification | object = _UNSET,
    root: Path | None = None,
) -> tuple[MCDACriterionEntry, str]:
    """Update a criterion's weight, direction, scale or provenance; only the fields given change."""
    paths = require_project(root)
    tid, label = _require(paths, target, "criterion")
    store = get_criteria(root=paths.root)
    current = next((e for e in store.entries if e.target_id == tid), None)
    given = {"weight": weight, "direction": direction, "worst": worst, "best": best, "units": units, "notes": notes,
             "origin": origin, "source_id": source_id, "verification": verification}
    changed = {k: v for k, v in given.items() if v is not _UNSET}
    if not changed:
        raise ValueError("nothing to set: give a weight, direction, scale (worst and best), units, notes or source")
    entry = MCDACriterionEntry.model_validate({**(current.model_dump() if current else {"target_id": tid}), **changed})
    store.entries = [e for e in store.entries if e.target_id != tid] + [entry]
    p = _path(paths, "criterion")
    _dump(p, store)
    sha = auto_commit(paths.root, subject=f"Set MCDA criterion {label}: {', '.join(changed)}",
                      body=f"target: {tid}\n" + "\n".join(f"{k}: {v}" for k, v in changed.items()), paths=[p])
    return entry, sha


def set_score(
    option: str,
    criterion: str,
    value: float,
    *,
    origin: ProvenanceOrigin = "human-direct",
    source_id: str | None = None,
    verification: ProvenanceVerification = "unverified",
    notes: str | None = None,
    root: Path | None = None,
) -> tuple[MCDAScoreEntry, str]:
    """Set an option's score on a criterion, in the criterion's units, with where it came from."""
    paths = require_project(root)
    oid, olabel = _require(paths, option, "option")
    cid, clabel = _require(paths, criterion, "criterion")
    entry = MCDAScoreEntry(target_id=oid, criterion=cid, value=value, origin=origin, source_id=source_id,
                           verification=verification, notes=notes)
    store = get_scores(root=paths.root)
    store.entries = [e for e in store.entries if (e.target_id, e.criterion) != (oid, cid)] + [entry]
    p = _path(paths, "score")
    _dump(p, store)
    sha = auto_commit(paths.root, subject=f"Set MCDA score {olabel} on {clabel} = {value:g}",
                      body=f"option: {oid}\ncriterion: {cid}\nvalue: {value}\norigin: {origin}\nsource_id: {source_id}",
                      paths=[p])
    return entry, sha


# ── structure ────────────────────────────────────────────────────────


@dataclass
class MCDAProblem:
    target_id: str | None
    gap_type: str
    message: str


@dataclass
class Model:
    labels: dict[str, str]
    options: list[str]
    criteria: list[str]
    settings: dict[str, MCDACriterionEntry]
    scores: dict[tuple[str, str], MCDAScoreEntry]
    problems: list[MCDAProblem] = field(default_factory=list)


def load(*, root: Path | None = None) -> Model:
    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    labels = {e.id: e.label for e in substrate.entities}
    el = {k: v for k, v in get_elements(root=paths.root).items() if k in labels}
    options = sorted((k for k, v in el.items() if v == "option"), key=lambda k: labels[k])
    criteria = sorted((k for k, v in el.items() if v == "criterion"), key=lambda k: labels[k])
    settings = {c.target_id: c for c in get_criteria(root=paths.root).entries if c.target_id in criteria}
    scores = {(s.target_id, s.criterion): s for s in get_scores(root=paths.root).entries
              if s.target_id in options and s.criterion in criteria}
    m = Model(labels=labels, options=options, criteria=criteria, settings=settings, scores=scores)
    if len(options) < 2:
        m.problems.append(MCDAProblem(None, "mcda_too_few_options", "A choice needs at least two options."))
    if not criteria:
        m.problems.append(MCDAProblem(None, "mcda_no_criterion", "No criteria: say what the options are judged on."))
    for c in criteria:
        s = settings.get(c)
        if not s or s.weight is None:
            m.problems.append(MCDAProblem(c, "mcda_no_weight", "No weight (`latris mcda criterion <c> --weight`)."))
        if not s or s.direction is None:
            m.problems.append(MCDAProblem(c, "mcda_no_direction",
                                          "Say whether higher or lower is better (--direction)."))
    for o in options:
        for c in criteria:
            if (o, c) not in scores:
                m.problems.append(MCDAProblem(o, "mcda_missing_score", f"No score on {labels[c]}."))
    return m


def structure_problems(*, root: Path | None = None) -> list[MCDAProblem]:
    return load(root=root).problems


# ── analysis kernel ──────────────────────────────────────────────────


def values(scores: dict[tuple[str, str], float], options: list[str], criteria: list[str],
           direction: dict[str, str], scale: dict[str, tuple[float, float] | None]) -> tuple[dict, dict, list[str]]:
    """Partial values in [0, 1] on linear scales; returns (values, scales used, warnings as codes)."""
    v: dict[tuple[str, str], float] = {}
    used: dict[str, dict[str, Any]] = {}
    notes: list[str] = []
    for c in criteria:
        xs = [scores[(o, c)] for o in options]
        if scale.get(c):
            worst, best = scale[c]  # type: ignore[misc]
            local = False
        else:
            lo, hi = min(xs), max(xs)
            worst, best = (lo, hi) if direction[c] == "higher" else (hi, lo)
            local = True
        used[c] = {"worst": worst, "best": best, "local": local}
        if worst == best:
            notes.append(f"flat:{c}")
            for o in options:
                v[(o, c)] = 1.0
            continue
        for o in options:
            raw = (scores[(o, c)] - worst) / (best - worst)
            if raw < 0 or raw > 1:
                notes.append(f"outside:{o}:{c}")
            v[(o, c)] = min(1.0, max(0.0, raw))
    return v, used, notes


def rank_reversal(v: dict[tuple[str, str], float], options: list[str], criteria: list[str],
                  w: dict[str, float]) -> dict[str, dict[str, Any]]:
    """For each criterion: the nearest weights, above and below the current one, at which the top option changes.

    Others keep their relative weights as one moves, so each option's total is linear in that weight.
    """
    out: dict[str, dict[str, Any]] = {}
    total = {o: sum(w[c] * v[(o, c)] for c in criteria) for o in options}
    best = max(options, key=lambda o: (total[o], -options.index(o)))
    for i in criteria:
        if len(criteria) < 2 or w[i] >= 1:
            continue
        rest = {o: sum(w[c] * v[(o, c)] for c in criteria if c != i) / (1 - w[i]) for o in options}
        t0 = w[i]
        up: tuple[float, str] | None = None
        down: tuple[float, str] | None = None
        for a in options:
            if a == best:
                continue
            d0 = rest[a] - rest[best]
            d1 = v[(a, i)] - v[(best, i)]
            slope = d1 - d0
            if slope == 0:
                continue
            t = -d0 / slope
            if not 0 <= t <= 1:
                continue
            if slope > 0 and t > t0 and (up is None or t < up[0]):
                up = (t, a)
            if slope < 0 and t < t0 and (down is None or t > down[0]):
                down = (t, a)
        out[i] = {"weight": t0, "up": {"weight": up[0], "option": up[1]} if up else None,
                  "down": {"weight": down[0], "option": down[1]} if down else None}
    return out


def _weak(entry) -> bool:
    return entry.verification != "human-verified" or entry.contested


def analyse(*, root: Path | None = None) -> dict[str, Any]:
    m = load(root=root)
    lab = m.labels
    payload: dict[str, Any] = {
        "options": [lab[o] for o in m.options], "criteria": [lab[c] for c in m.criteria],
        "problems": [{"label": lab.get(p.target_id or "", "(model)"), "gap_type": p.gap_type, "message": p.message}
                     for p in m.problems],
    }
    if m.problems:
        return payload
    raw_w = {c: m.settings[c].weight for c in m.criteria}
    tot = sum(raw_w.values())
    w = {c: raw_w[c] / tot for c in m.criteria}  # type: ignore[operator]
    direction = {c: m.settings[c].direction for c in m.criteria}
    scale = {c: (m.settings[c].worst, m.settings[c].best) if m.settings[c].worst is not None else None
             for c in m.criteria}
    x = {k: s.value for k, s in m.scores.items()}
    v, used, notes = values(x, m.options, m.criteria, direction, scale)  # type: ignore[arg-type]
    total = {o: sum(w[c] * v[(o, c)] for c in m.criteria) for o in m.options}
    order = sorted(m.options, key=lambda o: (-total[o], lab[o]))
    dominated = []
    for a in m.options:
        for b in m.options:
            if a != b and all(v[(b, c)] >= v[(a, c)] for c in m.criteria) and any(
                    v[(b, c)] > v[(a, c)] for c in m.criteria):
                dominated.append({"option": lab[a], "by": lab[b]})
                break
    rr = rank_reversal(v, m.options, m.criteria, w)
    margin: dict[str, Any] | None = None
    if len(order) >= 2:
        first, second = order[0], order[1]
        diffs = sorted(((c, w[c] * (v[(first, c)] - v[(second, c)])) for c in m.criteria), key=lambda t: -abs(t[1]))
        weak = [f"{lab[o]} on {lab[c]}" for c, d in diffs if d > 0 for o in (first, second)
                if _weak(m.scores[(o, c)])]
        margin = {"first": lab[first], "second": lab[second], "points": 100 * (total[first] - total[second]),
                  "by_criterion": [{"criterion": lab[c], "points": 100 * d} for c, d in diffs],
                  "unverified_scores": sorted(set(weak))}
    payload.update(
        weights=[{"criterion": lab[c], "weight": w[c], "raw": raw_w[c], "direction": direction[c],
                  "worst": used[c]["worst"], "best": used[c]["best"], "local_scale": used[c]["local"],
                  "units": m.settings[c].units, "source": m.settings[c].source_id,
                  "weak": _weak(m.settings[c])} for c in m.criteria],
        ranking=[{"option": lab[o], "total": 100 * total[o],
                  "contributions": {lab[c]: 100 * w[c] * v[(o, c)] for c in m.criteria},
                  "scores": {lab[c]: x[(o, c)] for c in m.criteria}} for o in order],
        dominated=dominated,
        rank_reversal=[{"criterion": lab[c], "weight": r["weight"],
                        "up": {"weight": r["up"]["weight"], "option": lab[r["up"]["option"]]} if r["up"] else None,
                        "down": {"weight": r["down"]["weight"], "option": lab[r["down"]["option"]]}
                        if r["down"] else None} for c, r in rr.items()],
        margin=margin,
        flat=[lab[n.split(":")[1]] for n in notes if n.startswith("flat:")],
        outside=[f"{lab[n.split(':')[1]]} on {lab[n.split(':')[2]]}" for n in notes if n.startswith("outside:")],
        unverified_scores=sum(1 for s in m.scores.values() if _weak(s)),
    )
    return payload


def closest_reversal(payload: dict[str, Any]) -> dict[str, Any] | None:
    """The smallest weight change, over all criteria, that changes the top option."""
    best = None
    for r in payload.get("rank_reversal", []):
        for side in ("up", "down"):
            if r[side]:
                gap = abs(r[side]["weight"] - r["weight"])
                if best is None or gap < best["gap"]:
                    best = {"criterion": r["criterion"], "from": r["weight"], "to": r[side]["weight"],
                            "option": r[side]["option"], "gap": gap}
    return best


def describe(p: dict[str, Any]) -> str:
    if p["problems"]:
        return f"The MCDA is incomplete ({len(p['problems'])} structure problem(s))"
    r = p["ranking"]
    parts = [f"{r[0]['option']} ranks first ({r[0]['total']:.0f} of 100)"]
    if len(r) > 1:
        parts.append(f"{r[1]['option']} second ({r[1]['total']:.0f})")
    near = closest_reversal(p)
    if near:
        parts.append(f"the top choice changes if the weight on {near['criterion']} moves from "
                     f"{near['from']:.0%} to {near['to']:.0%} ({near['option']} first)")
    else:
        parts.append("no single weight change reverses the top choice")
    if p["dominated"]:
        parts.append(f"{len(p['dominated'])} option(s) dominated")
    return "; ".join(parts)


def record(payload: dict[str, Any], *, root: Path | None = None) -> tuple[str, str]:
    from latris.operations.analysis_results import record_result

    sha, run = record_result(
        kind="mcda-analysis",
        key="mcda-analysis",
        payload=payload,
        purpose="sensitivity-analysis",
        algorithm="additive value model, linear partial values, normalised swing weights; one-way weight "
                  "rank-reversal thresholds",
        library_version="latris",
        summary=describe(payload),
        model_type=MODEL_TYPE,
        metrics={"options": len(payload["options"]), "criteria": len(payload["criteria"]),
                 "top": payload["ranking"][0]["option"] if payload.get("ranking") else None},
        commit_subject="Analysis: MCDA",
        root=root,
    )
    return sha, run.id

