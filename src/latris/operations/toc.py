"""Theory of Change — results chains from activities to impact.

A theory of change (Weiss 1995) states how an intervention is expected to
work: the activities it runs, what they produce, the changes those lead to,
and the long-term impact, with the assumptions behind each step made
explicit. Latris keeps the logic-model levels (W.K. Kellogg Foundation 2004)
as view roles on substrate factors::

    input → activity → output → short_term_outcome → long_term_outcome → impact

Links are ordinary causal edges. The analysis is structural and about
evidence, in the spirit of contribution analysis (Mayne 2012): it lays out
every pathway from an activity to an impact and says, link by link, what
holds it up — sources checked and found to support it, sources cited but not
yet checked, sources against it, and the assumptions stated for it. It does
not estimate effects or attribute an outcome to the intervention.

Three pieces:

- :func:`analyse` — the pure kernel (no I/O);
- :func:`structure_problems` — what the readiness gate reports;
- :func:`check` — loads the project, runs the kernel and records the result
  (``toc-pathways``) so reports show it.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from latris.repo.project import require_project
from latris.repo.yaml_io import load_model

MODEL_TYPE = "theory_of_change"

ToCLevel = Literal["input", "activity", "output", "short_term_outcome", "long_term_outcome", "impact"]
LEVELS: tuple[str, ...] = ("input", "activity", "output", "short_term_outcome", "long_term_outcome", "impact")
LEVEL_NAMES: dict[str, str] = {
    "input": "Input",
    "activity": "Activity",
    "output": "Output",
    "short_term_outcome": "Short-term outcome",
    "long_term_outcome": "Long-term outcome",
    "impact": "Impact",
}
_RANK = {lvl: i for i, lvl in enumerate(LEVELS)}

# A link that skips this many levels or more (e.g. an output straight to the
# impact) is a *leap*: the steps between are left unstated. Flagged, not refused.
LEAP_GAP = 3
# Pathway enumeration is capped; a results chain with more pathways than this
# is summarised by its links instead.
MAX_PATHWAYS = 200

EvidenceStatus = Literal["checked", "cited", "untested", "contested"]
_STATUS_ORDER: tuple[str, ...] = ("contested", "untested", "cited", "checked")  # weakest first


@dataclass
class ToCLink:
    edge_id: str
    from_id: str
    to_id: str
    from_level: str | None
    to_level: str | None
    sources_for: int = 0
    sources_for_checked: int = 0  # checked and found to support the link
    sources_against: int = 0
    assumptions: int = 0
    confidence: str | None = None
    on_pathway: bool = False
    leap: bool = False

    @property
    def status(self) -> EvidenceStatus:
        if self.sources_against:
            return "contested"
        if self.sources_for_checked:
            return "checked"
        if self.sources_for:
            return "cited"
        return "untested"


@dataclass
class ToCPathway:
    node_ids: list[str]
    edge_ids: list[str]
    status: EvidenceStatus  # its weakest link
    weak_edge_ids: list[str] = field(default_factory=list)  # links below "checked"


@dataclass
class ToCProblem:
    target_id: str | None
    gap_type: str
    message: str


@dataclass
class ToCAnalysis:
    levels: dict[str, str]  # entity id → level
    counts: dict[str, int]  # level → number of factors
    links: list[ToCLink]
    pathways: list[ToCPathway]
    pathways_truncated: bool
    dead_ends: list[str]  # factors (not impacts) with no route to an impact
    unreached_impacts: list[str]  # impacts no activity leads to
    problems: list[ToCProblem]

    def link(self, edge_id: str) -> ToCLink:
        return next(lk for lk in self.links if lk.edge_id == edge_id)


def _status_rank(status: str) -> int:
    return _STATUS_ORDER.index(status)


def _reaches(start: set[str], adj: dict[str, list[str]]) -> set[str]:
    seen = set(start)
    stack = list(start)
    while stack:
        for nxt in adj.get(stack.pop(), []):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen


def _links(edges: list[Any], levels: dict[str, str], confidence: dict[str, str],
           assumption_targets: Sequence[str | None], problems: list[ToCProblem]) -> list[ToCLink]:
    """One link per edge, with its levels, assumptions, confidence and whether it leaps; a link that runs
    backwards is a problem."""
    n_assumptions: dict[str, int] = defaultdict(int)
    for t in assumption_targets:
        if t:
            n_assumptions[t] += 1
    links: list[ToCLink] = []
    for e in edges:
        fl, tl = levels.get(e.from_id), levels.get(e.to_id)
        lk = ToCLink(
            edge_id=e.id, from_id=e.from_id, to_id=e.to_id, from_level=fl, to_level=tl,
            assumptions=n_assumptions.get(e.id, 0), confidence=confidence.get(e.id),
        )
        if fl and tl:
            gap = _RANK[tl] - _RANK[fl]
            if gap < 0:
                problems.append(ToCProblem(
                    e.id, "toc_backward_link",
                    f"Runs backwards, from {LEVEL_NAMES[fl].lower()} to {LEVEL_NAMES[tl].lower()}. A results chain "
                    "runs from activities towards the impact; reverse the link or change a level.",
                ))
            lk.leap = gap >= LEAP_GAP
        links.append(lk)
    return links


def _count_sources(evidence: Sequence[Any], by_id: dict[str, ToCLink]) -> None:
    for ev in evidence:
        link = by_id.get(ev.target_id)
        if link is None:
            continue
        if ev.is_against:
            link.sources_against += 1
        else:
            link.sources_for += 1
            if ev.support_verdict == "supports":
                link.sources_for_checked += 1


def _reach_problems(entity_ids: list[str], levels: dict[str, str], activities: list[str], impacts: list[str],
                    edges: list[Any], problems: list[ToCProblem]) -> tuple[list[str], list[str]]:
    """An activity and an impact to start and end at; factors that lead to no impact (dead ends) and impacts
    no activity reaches."""
    fwd: dict[str, list[str]] = defaultdict(list)
    rev: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        fwd[e.from_id].append(e.to_id)
        rev[e.to_id].append(e.from_id)
    if not activities:
        problems.append(ToCProblem(
            None, "toc_no_activity", "No activity: a theory of change starts from what the intervention does."
        ))
    if not impacts:
        problems.append(ToCProblem(
            None, "toc_no_impact", "No impact: say what long-term change the intervention is for."
        ))
    reach_impact = _reaches(set(impacts), rev)
    reached_from_activity = _reaches(set(activities), fwd)
    dead_ends = [
        eid for eid in entity_ids
        if impacts and eid in levels and levels[eid] != "impact" and eid not in reach_impact
    ]
    unreached = [eid for eid in impacts if activities and eid not in reached_from_activity]
    for eid in dead_ends:
        problems.append(ToCProblem(
            eid, "toc_dead_end", "Leads to no impact. Link it on towards the impact, or leave it out."
        ))
    for eid in unreached:
        problems.append(ToCProblem(eid, "toc_unreached_impact", "No activity leads to this impact."))
    return dead_ends, unreached


def _pathways(activities: list[str], impacts: list[str], edges: list[Any], by_id: dict[str, ToCLink]
              ) -> tuple[list[ToCPathway], bool]:
    """Every simple directed path from an activity to an impact (at most MAX_PATHWAYS), each with its weakest
    link; marks the links on one."""
    adj: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for e in edges:
        adj[e.from_id].append((e.to_id, e.id))
    pathways: list[ToCPathway] = []
    truncated = False
    impact_set = set(impacts)

    def dfs(node: str, nodes: list[str], eids: list[str]) -> None:
        nonlocal truncated
        if truncated:
            return
        if node in impact_set and eids:
            if len(pathways) >= MAX_PATHWAYS:
                truncated = True
                return
            statuses = [by_id[x].status for x in eids]
            pathways.append(ToCPathway(
                node_ids=list(nodes), edge_ids=list(eids),
                status=min(statuses, key=_status_rank),
                weak_edge_ids=[x for x in eids if by_id[x].status != "checked"],
            ))
            return
        for nxt, eid in adj.get(node, []):
            if nxt not in nodes:
                nodes.append(nxt)
                eids.append(eid)
                dfs(nxt, nodes, eids)
                nodes.pop()
                eids.pop()

    for a in activities:
        dfs(a, [a], [])
    for pw in pathways:
        for x in pw.edge_ids:
            by_id[x].on_pathway = True
    return pathways, truncated


def analyse(
    entity_ids: list[str],
    edges: list[Any],
    levels: dict[str, str],
    *,
    evidence: Sequence[Any] = (),
    assumption_targets: Sequence[str | None] = (),
    confidence: dict[str, str] | None = None,
) -> ToCAnalysis:
    """Lay out a results chain: its pathways, and what holds each link up.

    ``edges`` are causal substrate edges (anything with ``id``, ``from_id``,
    ``to_id``); ``evidence`` are :class:`EvidenceLink` records (any attribute
    of an edge counts as evidence for that link); ``assumption_targets`` are
    the ``target_id`` of each logged assumption.
    """
    entity_set = set(entity_ids)
    edges = [e for e in edges if e.from_id in entity_set and e.to_id in entity_set]
    problems = [ToCProblem(eid, "toc_no_level", "No theory-of-change level. Give it one with `latris toc level`.")
                for eid in entity_ids if eid not in levels]
    links = _links(edges, levels, confidence or {}, assumption_targets, problems)
    by_id = {lk.edge_id: lk for lk in links}
    _count_sources(evidence, by_id)
    counts = {lvl: 0 for lvl in LEVELS}
    for eid in entity_ids:
        if levels.get(eid) in counts:
            counts[levels[eid]] += 1
    activities = [eid for eid in entity_ids if levels.get(eid) == "activity"]
    impacts = [eid for eid in entity_ids if levels.get(eid) == "impact"]
    dead_ends, unreached = _reach_problems(entity_ids, levels, activities, impacts, edges, problems)
    pathways, truncated = _pathways(activities, impacts, edges, by_id)
    return ToCAnalysis(
        levels=dict(levels), counts=counts, links=links, pathways=pathways, pathways_truncated=truncated,
        dead_ends=dead_ends, unreached_impacts=unreached, problems=problems,
    )


# ── project I/O ──────────────────────────────────────────────────────


def get_levels(*, root: Path | None = None) -> dict[str, str]:
    """Entity id → theory-of-change level."""
    from latris.schema.roles import RoleSet

    paths = require_project(root)
    path = paths.role_path(MODEL_TYPE)
    if not path.exists():
        return {}
    return {e.target_id: e.value for e in load_model(RoleSet, path).entries if e.value in _RANK}


def set_level(target: str, level: str, *, root: Path | None = None) -> tuple[str, str]:
    """Give a factor its theory-of-change level. Returns (target_id, commit_sha)."""
    from latris.operations.view_roles import set_role

    if level not in _RANK:
        raise ValueError(f"{level!r} is not a theory-of-change level. Levels: {', '.join(LEVELS)}")
    return set_role(target, MODEL_TYPE, level, root=root)


def load_analysis(*, root: Path | None = None) -> tuple[ToCAnalysis, Any]:
    """Run :func:`analyse` on the project. Returns (analysis, substrate)."""
    from latris.operations.graph_analysis import causal_edges
    from latris.schema import AssumptionLog, ConfidenceSet, EvidenceLinkSet, Substrate

    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    evidence = load_model(EvidenceLinkSet, paths.evidence_links_yaml) if paths.evidence_links_yaml.exists() else None
    assumptions = load_model(AssumptionLog, paths.assumptions_yaml) if paths.assumptions_yaml.exists() else None
    conf = load_model(ConfidenceSet, paths.confidence_yaml) if paths.confidence_yaml.exists() else None
    result = analyse(
        [e.id for e in substrate.entities],
        causal_edges(substrate.edges),
        get_levels(root=paths.root),
        evidence=evidence.entries if evidence else [],
        assumption_targets=[a.target_id for a in assumptions.entries] if assumptions else [],
        confidence={c.target_id: c.value for c in conf.entries} if conf else {},
    )
    return result, substrate


def structure_problems(*, root: Path | None = None) -> list[ToCProblem]:
    """What stops the theory of change being complete (the readiness gate)."""
    return load_analysis(root=root)[0].problems


def _labels(substrate) -> dict[str, str]:
    labels = {e.id: e.label for e in substrate.entities}
    for e in substrate.edges:
        labels[e.id] = f"{labels.get(e.from_id, e.from_id)} → {labels.get(e.to_id, e.to_id)}"
    return labels


def to_payload(result: ToCAnalysis, substrate) -> dict[str, Any]:
    """JSON-ready form of an analysis, with labels, as recorded and reported."""
    labels = _labels(substrate)
    links = []
    for lk in result.links:
        d = asdict(lk)
        d.update(status=lk.status, label=labels.get(lk.edge_id, lk.edge_id),
                 **{"from": labels.get(lk.from_id, lk.from_id), "to": labels.get(lk.to_id, lk.to_id)})
        links.append(d)
    return {
        "levels": {labels.get(k, k): v for k, v in result.levels.items()},
        "level_of": result.levels,
        "counts": result.counts,
        "links": links,
        "pathways": [
            {**asdict(p), "path": [labels.get(n, n) for n in p.node_ids],
             "weak_links": [labels.get(x, x) for x in p.weak_edge_ids]}
            for p in result.pathways
        ],
        "pathways_truncated": result.pathways_truncated,
        "dead_ends": [labels.get(x, x) for x in result.dead_ends],
        "unreached_impacts": [labels.get(x, x) for x in result.unreached_impacts],
        "problems": [{**asdict(p), "label": labels.get(p.target_id or "", p.target_id or "(model)")}
                     for p in result.problems],
    }


def describe(payload: dict[str, Any]) -> str:
    """One-line summary of a recorded ``toc-pathways`` payload."""
    pws = payload["pathways"]
    if not pws:
        return "No pathway runs from an activity to an impact yet"
    by: defaultdict[str, int] = defaultdict(int)
    for p in pws:
        by[p["status"]] += 1
    n = len(pws)
    more = "+" if payload.get("pathways_truncated") else ""
    parts = [f"{by[s]} {s}" for s in ("checked", "cited", "untested", "contested") if by[s]]
    on = [lk for lk in payload["links"] if lk["on_pathway"]]
    untested = sum(1 for lk in on if lk["status"] == "untested")
    no_assumption = sum(1 for lk in on if not lk["assumptions"])
    return (
        f"{n}{more} pathway(s) from activity to impact, by their weakest link: {', '.join(parts)}; "
        f"{untested} of {len(on)} link(s) on a pathway have no source, {no_assumption} have no stated assumption"
    )


def check(*, record: bool = True, root: Path | None = None) -> tuple[dict[str, Any], str | None]:
    """Analyse the theory of change and (by default) record it for reports.

    Returns (payload, commit_sha); the sha is ``None`` when not recorded.
    """
    from latris.operations.analysis_results import record_result

    paths = require_project(root)
    result, substrate = load_analysis(root=paths.root)
    payload = to_payload(result, substrate)
    if not record:
        return payload, None
    statuses: defaultdict[str, int] = defaultdict(int)
    for p in result.pathways:
        statuses[p.status] += 1
    sha, run = record_result(
        kind="toc-pathways",
        key="toc-pathways",
        payload=payload,
        purpose="validation",
        algorithm="results-chain pathway enumeration; evidence status per link",
        library_version="latris",
        summary=describe(payload),
        model_type=MODEL_TYPE,
        metrics={"pathways": len(result.pathways), **{f"pathways_{k}": v for k, v in statuses.items()},
                 "problems": len(result.problems)},
        affected_target_ids=[lk.edge_id for lk in result.links if lk.on_pathway],
        commit_subject="Analysis: theory of change pathways",
        root=paths.root,
    )
    payload["run_id"] = run.id
    return payload, sha
