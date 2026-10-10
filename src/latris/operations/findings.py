"""Finding operations — record, query, review, and generate findings.

CRUD operations persist to ``analysis/findings.jsonl`` (append-only JSONL).
Generator functions (``findings_from_*``) are pure — they create Finding
objects from analysis results without touching the filesystem.

NOTE: the ``findings_from_*`` generators + ``supersede_matching`` are
designed-but-unwired — no analyse command/route persists analysis results as
Findings yet. They are kept (and tested) ahead of that wiring; see the
analysis→findings feature note. The live creation path today is
``record_new_finding`` (human/AI-sourced).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from latris.operations.commit import auto_commit
from latris.repo import git
from latris.repo.project import require_project
from latris.repo.yaml_io import atomic_replace, dump_jsonl_append, iter_jsonl, load_model
from latris.schema import (
    Substrate,
)
from latris.schema.common import HumanActor, ProvenanceOrigin, now_utc
from latris.schema.findings import (
    Finding,
    FindingCategory,
    FindingSourceType,
)
from latris.schema.ids import new_id
from latris.schema.maturity import Maturity

# ── CRUD operations ─────────────────────────────────────────────────────


def record_finding(
    finding: Finding,
    *,
    root: Path | None = None,
) -> tuple[Finding, str]:
    """Append a finding to ``analysis/findings.jsonl`` and commit.

    Returns the finding and the commit SHA.
    """
    paths = require_project(root)
    dump_jsonl_append(finding, paths.findings_jsonl)
    sha = auto_commit(
        paths.root,
        subject=f"Finding ({finding.category}): {_truncate(finding.statement)}",
        body=f"id: {finding.id}\nmodel_type: {finding.model_type}",
        paths=[paths.findings_jsonl],
    )
    return finding, sha


def record_new_finding(
    statement: str,
    category: FindingCategory,
    model_type: str,
    *,
    detail: str = "",
    payload: dict | None = None,
    origin: ProvenanceOrigin = "human-direct",
    source_id: str | None = None,
    source_type: FindingSourceType = "human-direct",
    target_ids: list[str] | None = None,
    related_attributes: list[str] | None = None,
    root: Path | None = None,
) -> tuple[Finding, str]:
    """Create and record a new finding in one step.

    Convenience wrapper: builds a :class:`Finding`, appends it, and commits.
    """
    paths = require_project(root)
    finding = Finding(
        id=new_id("finding"),
        category=category,
        model_type=model_type,
        statement=statement,
        detail=detail,
        payload=dict(payload or {}),
        origin=origin,
        source_id=source_id,
        source_type=source_type,
        target_ids=list(target_ids or []),
        related_attributes=list(related_attributes or []),
        model_commit=git.head_sha(paths.root),
    )
    return record_finding(finding, root=paths.root)


def iter_findings(root: Path | None = None) -> Iterable[Finding]:
    """Iterate all findings from ``analysis/findings.jsonl``."""
    paths = require_project(root)
    return iter_jsonl(Finding, paths.findings_jsonl)


def list_findings(
    *,
    category: FindingCategory | None = None,
    model_type: str | None = None,
    maturity: Maturity | None = None,
    target_id: str | None = None,
    limit: int | None = None,
    root: Path | None = None,
) -> list[Finding]:
    """Read findings with optional filters, newest first."""
    records = list(iter_findings(root=root))
    if category is not None:
        records = [r for r in records if r.category == category]
    if model_type is not None:
        records = [r for r in records if r.model_type == model_type]
    if maturity is not None:
        records = [r for r in records if r.maturity == maturity]
    if target_id is not None:
        records = [r for r in records if target_id in r.target_ids]
    records.reverse()  # newest first
    if limit is not None:
        records = records[:limit]
    return records


def get_finding(
    query: str,
    *,
    root: Path | None = None,
) -> Finding:
    """Return the finding whose id matches *query* exactly or by prefix."""
    records = list(iter_findings(root=root))
    exact = [r for r in records if r.id == query]
    if len(exact) == 1:
        return exact[0]
    prefix = [r for r in records if r.id.startswith(query)]
    if len(prefix) == 1:
        return prefix[0]
    if len(prefix) > 1:
        ids = ", ".join(r.id for r in prefix)
        raise ValueError(f"finding prefix {query!r} is ambiguous (matches: {ids})")
    raise ValueError(f"no finding matches {query!r}")


def set_finding_maturity(
    query: str,
    *,
    maturity: Maturity,
    reviewed_by: HumanActor | None = None,
    root: Path | None = None,
) -> tuple[Finding, str]:
    """Update a finding's maturity. Rewrites the whole JSONL atomically.

    Note: setting maturity to ``approved`` does NOT auto-write a Signoff
    here — use ``operations/maturity.py::approve()`` for that. This
    function exists for low-level edits and back-compat with internal
    callers (e.g. supersession).
    """
    paths = require_project(root)
    target = get_finding(query, root=paths.root)
    all_records = list(iter_findings(root=paths.root))
    for r in all_records:
        if r.id == target.id:
            r.maturity = maturity
            if reviewed_by is not None:
                r.reviewed_by = reviewed_by
                r.reviewed_at = now_utc()
            target = r
            break

    _rewrite_jsonl(all_records, paths.findings_jsonl)
    sha = auto_commit(
        paths.root,
        subject=f"Finding {target.id[:20]}…: {maturity}",
        body=f"category: {target.category}",
        paths=[paths.findings_jsonl],
    )
    return target, sha


def supersede_matching(
    *,
    model_type: str,
    category: FindingCategory,
    target_ids: list[str],
    new_finding_id: str | None = None,
    root: Path | None = None,
) -> list[Finding]:
    """Record supersession when new findings are generated for the same
    (model_type, category, target_ids).

    Adds the *new_finding_id* (if given) to each prior finding's
    ``supersedes`` pointer list. Prior findings keep their existing
    maturity — the typed pointer is the supersession signal, not a
    status flag (see docs/design/MATURITY_LADDER.md).

    Returns the list of findings that were marked superseded.
    """
    paths = require_project(root)
    all_records = list(iter_findings(root=paths.root))
    target_set = set(target_ids)
    superseded: list[Finding] = []
    changed = False
    for r in all_records:
        if (
            r.model_type == model_type
            and r.category == category
            and set(r.target_ids) == target_set
        ):
            if new_finding_id and new_finding_id not in r.supersedes:
                r.supersedes.append(new_finding_id)
                changed = True
            superseded.append(r)

    if changed:
        _rewrite_jsonl(all_records, paths.findings_jsonl)
        auto_commit(
            paths.root,
            subject=f"Superseded {len(superseded)} finding(s)",
            body=f"model_type: {model_type}, category: {category}",
            paths=[paths.findings_jsonl],
        )
    return superseded


def check_staleness(
    finding: Finding,
    *,
    root: Path | None = None,
) -> bool:
    """Return True if the finding may be stale.

    A finding is potentially stale when:
    - Its ``model_commit`` differs from current HEAD, AND any of:
      * an entity/edge in ``target_ids`` has been deleted, OR
      * an edge in ``target_ids`` has been reclassified from
        ``causal`` to a non-causal kind. Loop and centrality
        findings rest on the causal-edge subgraph; once an edge
        is no longer causal, the finding's claim no longer holds
        (Phase 3 AI interrogation).
    """
    paths = require_project(root)
    if not finding.model_commit:
        return False
    current_sha = git.head_sha(paths.root)
    if finding.model_commit == current_sha:
        return False
    if not finding.target_ids:
        return False
    substrate = load_model(Substrate, paths.conceptual_yaml)
    current_ids = {e.id for e in substrate.entities} | {e.id for e in substrate.edges}
    # Deletion check.
    if any(tid not in current_ids for tid in finding.target_ids):
        return True
    # Reclassify check: load substrate at finding.model_commit and
    # compare edge kinds for any target edges still present.
    target_edges_now = {e.id: e for e in substrate.edges if e.id in finding.target_ids}
    if not target_edges_now:
        return False
    try:
        rel_path = paths.conceptual_yaml.relative_to(paths.root)
        old_yaml = git.show_file(paths.root, finding.model_commit, str(rel_path))
    except Exception:
        # Old commit no longer accessible; fall back to the deletion-only
        # signal we already evaluated above.
        return False
    try:
        old_substrate = Substrate.model_validate(_yaml_loads(old_yaml))
    except Exception:
        return False
    old_edge_kinds = {e.id: e.kind for e in old_substrate.edges}
    for edge_id, edge in target_edges_now.items():
        old_kind = old_edge_kinds.get(edge_id)
        if old_kind == "causal" and edge.kind != "causal":
            return True
    return False


def _yaml_loads(text: str):
    """Parse YAML text into a python dict using the project's yaml lib."""
    from ruamel.yaml import YAML

    yaml = YAML(typ="safe")
    return yaml.load(text)


# ── Finding generators (pure — no I/O) ─────────────────────────────────


def findings_from_loops(
    loops: list,
    *,
    model_commit: str = "",
    target_ids: list[str] | None = None,
) -> list[Finding]:
    """Generate structure finding(s) from CLD loop analysis results."""
    if not loops:
        return [
            Finding(
                id=new_id("finding"),
                category="structure",
                model_type="cld",
                maturity="proposed",
                statement="No feedback loops were detected in the model.",
                origin="data-derived",
                source_type="analysis-run",
                model_commit=model_commit,
                target_ids=list(target_ids or []),
            )
        ]

    r_count = sum(1 for loop in loops if loop.classification == "R")
    b_count = sum(1 for loop in loops if loop.classification == "B")
    unknown = sum(1 for loop in loops if loop.classification == "unknown")

    parts = []
    if r_count:
        parts.append(f"{r_count} reinforcing")
    if b_count:
        parts.append(f"{b_count} balancing")
    if unknown:
        parts.append(f"{unknown} unclassified")
    classification_text = ", ".join(parts)

    statement = f"The model contains {len(loops)} feedback loop{'s' if len(loops) != 1 else ''}: {classification_text}."

    # Build detail with individual loop info
    detail_lines = []
    for i, loop in enumerate(loops, 1):
        node_str = " → ".join(loop.node_ids) + f" → {loop.node_ids[0]}"
        detail_lines.append(f"Loop {loop.classification}{i}: {node_str}")
    detail = "\n".join(detail_lines)

    # Collect all node IDs referenced in loops
    loop_node_ids = set()
    for loop in loops:
        loop_node_ids.update(loop.node_ids)

    return [
        Finding(
            id=new_id("finding"),
            category="structure",
            model_type="cld",
            maturity="proposed",
            statement=statement,
            detail=detail,
            payload={
                "loop_count": len(loops),
                "reinforcing_count": r_count,
                "balancing_count": b_count,
                "unknown_count": unknown,
                "loops": [
                    {
                        "node_ids": list(loop.node_ids),
                        "edge_ids": list(loop.edge_ids),
                        "classification": loop.classification,
                    }
                    for loop in loops
                ],
            },
            origin="data-derived",
            source_type="analysis-run",
            model_commit=model_commit,
            target_ids=sorted(loop_node_ids) if not target_ids else list(target_ids),
        )
    ]


def findings_from_centrality(
    results: list,
    *,
    model_commit: str = "",
    target_ids: list[str] | None = None,
    entity_labels: dict[str, str] | None = None,
    has_loops: bool = True,
) -> list[Finding]:
    """Generate sensitivity finding(s) from centrality analysis results.

    When the graph has no loops (``has_loops=False``), the finding is
    framed as identifying *structural mediators* (nodes that lie on many
    causal paths) rather than as identifying *leverage points*. On a
    purely acyclic graph the betweenness ranking is largely a restatement
    of topology — the upstream-source / downstream-sink position — and
    overstating it as a dynamic-leverage insight has been a source of
    capability-run feedback. Callers that know loops exist (e.g. CLD
    callers post loop-detection) can pass ``has_loops=True`` (the default)
    to keep the leverage framing.
    """
    if not results:
        return []

    labels = entity_labels or {}
    sorted_by_betweenness = sorted(results, key=lambda r: r.betweenness, reverse=True)
    top = sorted_by_betweenness[0]
    top_label = labels.get(top.entity_id, top.entity_id)

    if has_loops:
        statement = (
            f"{top_label} is the most central variable "
            f"(betweenness: {top.betweenness:.2f}, degree: {top.degree_total})."
        )
    else:
        statement = (
            f"{top_label} is the top structural mediator on the acyclic "
            f"graph (betweenness: {top.betweenness:.2f}, degree: "
            f"{top.degree_total}). On graphs without feedback loops, "
            "betweenness primarily reflects topology rather than dynamic "
            "leverage."
        )

    detail_lines = []
    for r in sorted_by_betweenness[:5]:
        label = labels.get(r.entity_id, r.entity_id)
        detail_lines.append(
            f"{label}: betweenness={r.betweenness:.2f}, in={r.degree_in}, out={r.degree_out}, total={r.degree_total}"
        )
    detail = "\n".join(detail_lines)

    return [
        Finding(
            id=new_id("finding"),
            category="sensitivity",
            model_type="cld",
            maturity="proposed",
            statement=statement,
            detail=detail,
            payload={
                "ranking": [
                    {
                        "entity_id": r.entity_id,
                        "label": labels.get(r.entity_id, r.entity_id),
                        "betweenness": r.betweenness,
                        "degree_in": r.degree_in,
                        "degree_out": r.degree_out,
                        "degree_total": r.degree_total,
                    }
                    for r in sorted_by_betweenness
                ],
            },
            origin="data-derived",
            source_type="analysis-run",
            model_commit=model_commit,
            target_ids=list(target_ids or [r.entity_id for r in results]),
        )
    ]


def findings_from_propagation(
    source_id: str,
    effects: list,
    *,
    model_commit: str = "",
    source_label: str | None = None,
    entity_labels: dict[str, str] | None = None,
) -> list[Finding]:
    """Generate inference finding(s) from polarity propagation results."""
    if not effects:
        return []

    labels = entity_labels or {}
    src_label = source_label or labels.get(source_id, source_id)

    positive = [e for e in effects if e.effect == "+"]
    negative = [e for e in effects if e.effect == "-"]
    ambiguous = [e for e in effects if e.effect == "ambiguous"]

    parts = []
    if positive:
        parts.append(f"{len(positive)} increase")
    if negative:
        parts.append(f"{len(negative)} decrease")
    if ambiguous:
        parts.append(f"{len(ambiguous)} have ambiguous effects")

    statement = (
        f"An increase in {src_label} causes {', '.join(parts)} "
        f"across {len(effects)} reachable variable{'s' if len(effects) != 1 else ''}."
    )

    return [
        Finding(
            id=new_id("finding"),
            category="inference",
            model_type="cld",
            maturity="proposed",
            statement=statement,
            payload={
                "source_id": source_id,
                "effects": [
                    {
                        "entity_id": e.entity_id,
                        "label": labels.get(e.entity_id, e.entity_id),
                        "effect": e.effect,
                        "paths_positive": e.paths_positive,
                        "paths_negative": e.paths_negative,
                    }
                    for e in effects
                ],
            },
            origin="data-derived",
            source_type="analysis-run",
            model_commit=model_commit,
            target_ids=[source_id] + [e.entity_id for e in effects],
        )
    ]


def findings_from_dseparation(
    x: list[str],
    y: list[str],
    given: list[str],
    d_separated: bool,
    *,
    model_commit: str = "",
    entity_labels: dict[str, str] | None = None,
) -> list[Finding]:
    """Generate inference finding from a d-separation test."""
    labels = entity_labels or {}

    def _label_list(ids: list[str]) -> str:
        return ", ".join(labels.get(i, i) for i in ids)

    x_str = _label_list(x)
    y_str = _label_list(y)

    if d_separated:
        if given:
            statement = f"{x_str} and {y_str} are conditionally independent given {{{_label_list(given)}}}."
        else:
            statement = f"{x_str} and {y_str} are marginally independent."
    else:
        if given:
            statement = f"{x_str} and {y_str} are NOT conditionally independent given {{{_label_list(given)}}}."
        else:
            statement = f"{x_str} and {y_str} are marginally dependent."

    return [
        Finding(
            id=new_id("finding"),
            category="inference",
            model_type="dag",
            maturity="proposed",
            statement=statement,
            payload={
                "x": x,
                "y": y,
                "given": given,
                "d_separated": d_separated,
            },
            origin="data-derived",
            source_type="analysis-run",
            model_commit=model_commit,
            target_ids=x + y + given,
        )
    ]


def findings_from_adjustment_sets(
    exposure_id: str,
    outcome_id: str,
    adjustment_sets: list[list[str]],
    *,
    model_commit: str = "",
    entity_labels: dict[str, str] | None = None,
) -> list[Finding]:
    """Generate inference finding from adjustment set computation."""
    labels = entity_labels or {}
    exp_label = labels.get(exposure_id, exposure_id)
    out_label = labels.get(outcome_id, outcome_id)

    if not adjustment_sets:
        statement = f"No valid adjustment set exists for estimating the causal effect of {exp_label} on {out_label}."
    elif len(adjustment_sets) == 1 and not adjustment_sets[0]:
        statement = (
            f"The causal effect of {exp_label} on {out_label} is "
            f"identifiable without conditioning on any variable (empty adjustment set)."
        )
    else:
        set_strs = []
        for s in adjustment_sets:
            if not s:
                set_strs.append("∅ (empty set)")
            else:
                names = ", ".join(labels.get(i, i) for i in s)
                set_strs.append(f"{{{names}}}")
        statement = (
            f"{len(adjustment_sets)} valid adjustment set{'s' if len(adjustment_sets) != 1 else ''} "
            f"found for the causal effect of {exp_label} on {out_label}: "
            f"{'; '.join(set_strs)}."
        )

    all_ids = {exposure_id, outcome_id}
    for s in adjustment_sets:
        all_ids.update(s)

    return [
        Finding(
            id=new_id("finding"),
            category="inference",
            model_type="dag",
            maturity="proposed",
            statement=statement,
            payload={
                "exposure_id": exposure_id,
                "outcome_id": outcome_id,
                "adjustment_sets": adjustment_sets,
                "count": len(adjustment_sets),
            },
            origin="data-derived",
            source_type="analysis-run",
            model_commit=model_commit,
            target_ids=sorted(all_ids),
        )
    ]


def findings_from_fcm_inference(
    result,
    *,
    model_commit: str = "",
    target_ids: list[str] | None = None,
    entity_labels: dict[str, str] | None = None,
    scenario_label: str | None = None,
) -> list[Finding]:
    """Generate dynamics finding(s) from FCM inference results."""
    labels = entity_labels or {}

    if result.converged:
        convergence_text = f"converged after {result.iterations} iterations"
    else:
        convergence_text = f"did not converge after {result.iterations} iterations"

    # Find highest and lowest activation variables
    sorted_activations = sorted(
        result.activations.items(),
        key=lambda kv: kv[1],
        reverse=True,
    )
    high = sorted_activations[:3]
    high_parts = ", ".join(f"{labels.get(eid, eid)} ({val:.2f})" for eid, val in high)

    scenario_prefix = f"Scenario '{scenario_label}': " if scenario_label else ""

    statement = f"{scenario_prefix}FCM inference {convergence_text}. Highest activations: {high_parts}."

    return [
        Finding(
            id=new_id("finding"),
            category="dynamics",
            model_type="fcm",
            maturity="proposed",
            statement=statement,
            payload={
                "activations": result.activations,
                "converged": result.converged,
                "iterations": result.iterations,
                "scenario_label": scenario_label,
            },
            origin="data-derived",
            source_type="analysis-run",
            model_commit=model_commit,
            target_ids=list(target_ids or list(result.activations.keys())),
        )
    ]


# ── Helpers ─────────────────────────────────────────────────────────────


def _truncate(text: str, length: int = 50) -> str:
    """Truncate text for commit messages."""
    if len(text) <= length:
        return text
    return text[: length - 1] + "…"


def _rewrite_jsonl(records: list[Finding], path: Path) -> None:
    """Atomically rewrite the entire JSONL file."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        for r in records:
            f.write(json.dumps(r.model_dump(mode="json"), ensure_ascii=False) + "\n")
    atomic_replace(tmp, path)
