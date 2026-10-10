"""Maturity operations — single chokepoint for the unified maturity ladder.

Sets ``maturity`` on any modelling artifact (Entity, Edge, Finding,
Mapping, LineageNode, Milestone). All callers go through this module
per the five-chokepoints rule (``src/latris/CLAUDE.md``).
``approve()`` atomically writes a ``Signoff`` row as the audit
artifact for the ``approved`` transition.

Derived badges (``compute_badges``) read from EvidenceLink, Challenge,
FloatSet, formalism stores, and Prediction — never persisted. Full
design in ``docs/design/MATURITY_LADDER.md``.
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Author identity
# ---------------------------------------------------------------------------
from latris.operations._actor import author as _author
from latris.operations._resolve import resolve_edge, resolve_entity
from latris.operations.commit import auto_commit
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_model, iter_jsonl, load_model
from latris.schema import (
    EvidenceLinkSet,
    Finding,
    FloatSet,
    HumanActor,
    LineageNode,
    MappingRegistry,
    Maturity,
    MaturityBadges,
    MilestoneLog,
    PredictionLog,
    Signoff,
    SignoffLog,
    Substrate,
    new_id,
)
from latris.schema.ai import ChallengeLog
from latris.schema.common import now_utc

# ---------------------------------------------------------------------------
# Target dispatch
# ---------------------------------------------------------------------------


def _set_maturity_in_substrate(target_id: str, maturity: Maturity, paths) -> Path | None:
    """Find target in substrate (entity or edge) and set its maturity. Returns the path written."""
    substrate = load_model(Substrate, paths.conceptual_yaml)
    for ent in substrate.entities:
        if ent.id == target_id:
            ent.maturity = maturity
            dump_model(substrate, paths.conceptual_yaml)
            return paths.conceptual_yaml
    for edge in substrate.edges:
        if edge.id == target_id:
            edge.maturity = maturity
            dump_model(substrate, paths.conceptual_yaml)
            return paths.conceptual_yaml
    return None


def _set_maturity_in_mappings(target_id: str, maturity: Maturity, paths) -> Path | None:
    """Find a Mapping by l3_id and set its maturity. Returns the path written."""
    if not paths.mappings_yaml.exists():
        return None
    registry = load_model(MappingRegistry, paths.mappings_yaml)
    for m in registry.entries:
        if m.l3_id == target_id:
            m.maturity = maturity
            dump_model(registry, paths.mappings_yaml)
            return paths.mappings_yaml
    return None


def _set_maturity_in_findings(target_id: str, maturity: Maturity, paths) -> Path | None:
    """Find a Finding by id and set its maturity. Returns the path written."""
    if not paths.findings_jsonl.exists():
        return None
    records = list(iter_jsonl(Finding, paths.findings_jsonl))
    found = False
    for r in records:
        if r.id == target_id:
            r.maturity = maturity
            found = True
    if not found:
        return None
    _rewrite_findings(records, paths.findings_jsonl)
    return paths.findings_jsonl


def _set_maturity_in_milestones(target_id: str, maturity: Maturity, paths) -> Path | None:
    """Find a Milestone by id on the current branch and set its maturity."""
    if not paths.milestones_yaml.exists():
        return None
    log = load_model(MilestoneLog, paths.milestones_yaml)
    for m in log.entries:
        if m.id == target_id:
            m.maturity = maturity
            dump_model(log, paths.milestones_yaml)
            return paths.milestones_yaml
    return None


def _set_maturity_in_lineage(target_id: str, maturity: Maturity, paths) -> Path | None:
    """If target_id is the current LineageNode id, set its maturity."""
    if not paths.lineage_node_yaml.exists():
        return None
    node = load_model(LineageNode, paths.lineage_node_yaml)
    if node.id != target_id:
        return None
    node.maturity = maturity
    dump_model(node, paths.lineage_node_yaml)
    return paths.lineage_node_yaml


def _resolve_and_set(target: str, maturity: Maturity, paths) -> tuple[str, Path]:
    """Resolve *target* across substrate / mappings / findings / lineage / milestones,
    set its maturity, and return ``(resolved_id, file_path)``.
    """
    # Try substrate label/prefix resolution first.
    substrate = load_model(Substrate, paths.conceptual_yaml)
    try:
        ent = resolve_entity(target, substrate.entities)
        path = _set_maturity_in_substrate(ent.id, maturity, paths)
        if path is not None:
            return ent.id, path
    except ValueError:
        pass
    try:
        edge = resolve_edge(target, substrate.edges)
        path = _set_maturity_in_substrate(edge.id, maturity, paths)
        if path is not None:
            return edge.id, path
    except ValueError:
        pass

    # Fall back to ID-based dispatch across other artifact stores.
    for resolver in (
        _set_maturity_in_mappings,
        _set_maturity_in_findings,
        _set_maturity_in_milestones,
        _set_maturity_in_lineage,
    ):
        path = resolver(target, maturity, paths)
        if path is not None:
            return target, path

    raise ValueError(f"no entity, edge, mapping, finding, milestone, or lineage node matches {target!r}")


# ---------------------------------------------------------------------------
# Public API — set maturity
# ---------------------------------------------------------------------------


def propose(
    target: str,
    *,
    root: Path | None = None,
) -> tuple[Maturity, str]:
    """Set *target* maturity to ``proposed``. Returns (new_maturity, commit_sha)."""
    paths = require_project(root)
    resolved_id, file_path = _resolve_and_set(target, "proposed", paths)
    sha = auto_commit(
        paths.root,
        subject=f"Maturity → proposed: {resolved_id[:20]}…",
        body=f"target: {resolved_id}",
        paths=[file_path],
    )
    return "proposed", sha


def mark_reviewed(
    target: str,
    *,
    root: Path | None = None,
) -> tuple[Maturity, str]:
    """Set *target* maturity to ``reviewed``. Returns (new_maturity, commit_sha)."""
    paths = require_project(root)
    resolved_id, file_path = _resolve_and_set(target, "reviewed", paths)
    sha = auto_commit(
        paths.root,
        subject=f"Maturity → reviewed: {resolved_id[:20]}…",
        body=f"target: {resolved_id}",
        paths=[file_path],
    )
    return "reviewed", sha


def approve(
    target: str,
    *,
    reviewer: HumanActor | None = None,
    role: str = "Reviewer",
    scope: str = "Model",
    notes: str | None = None,
    root: Path | None = None,
) -> tuple[Maturity, str]:
    """Set *target* maturity to ``approved`` and write a ``Signoff`` row.

    The Signoff is the audit artifact for the approval transition; the
    maturity field is the workflow gate. See
    ``docs/design/MATURITY_LADDER.md``.
    """
    paths = require_project(root)
    resolved_id, file_path = _resolve_and_set(target, "approved", paths)
    actor = reviewer if reviewer is not None else _author(paths.root)

    signoff = Signoff(
        id=new_id("signoff"),
        reviewer=actor,
        role=role,
        scope=scope,
        target_id=resolved_id,
        signed_at=now_utc(),
        notes=notes,
    )
    log = load_model(SignoffLog, paths.signoffs_yaml) if paths.signoffs_yaml.exists() else SignoffLog()
    log.entries.append(signoff)
    dump_model(log, paths.signoffs_yaml)

    sha = auto_commit(
        paths.root,
        subject=f"Maturity → approved: {resolved_id[:20]}…",
        body=f"target: {resolved_id}\nreviewer: {actor.name}",
        paths=[file_path, paths.signoffs_yaml],
    )
    return "approved", sha


# ---------------------------------------------------------------------------
# Derived badges
# ---------------------------------------------------------------------------


def compute_badges(
    target_id: str,
    *,
    model_type: str | None = None,
    root: Path | None = None,
) -> MaturityBadges:
    """Compute the derived badges for *target_id* by reading the related stores.

    Never persisted. The canonical source for each badge is the related
    store; recomputed on every call. Caching belongs in
    ``server/state.py`` with file-watcher invalidation.

    *model_type* is consulted for the ``has_formalism`` and
    ``has_quantification`` checks (per-view stores).
    """
    paths = require_project(root)

    has_evidence = False
    if paths.evidence_links_yaml.exists():
        ev = load_model(EvidenceLinkSet, paths.evidence_links_yaml)
        has_evidence = any(e.target_id == target_id for e in ev.entries)

    has_challenges = False
    if paths.challenges_yaml.exists():
        ch = load_model(ChallengeLog, paths.challenges_yaml)
        has_challenges = any(c.target_id == target_id and c.state == "open" for c in ch.entries)

    has_quantification = False
    if model_type is not None:
        # FloatSet attributes (FCM weights, SD parameters, etc.) live per
        # view at views/parameters/{model_type}-{attr}.yaml. We don't know
        # the attr name here, so do a directory scan when available.
        params_dir = paths.root / "views" / "parameters"
        if params_dir.exists():
            for f in params_dir.glob(f"{model_type}-*.yaml"):
                try:
                    fs = load_model(FloatSet, f)
                except Exception:
                    continue
                if any(e.target_id == target_id for e in fs.entries):
                    has_quantification = True
                    break

    has_formalism = False
    if paths.mappings_yaml.exists():
        registry = load_model(MappingRegistry, paths.mappings_yaml)
        has_formalism = any(
            m.l2_id == target_id and (model_type is None or m.l3_view == model_type)
            for m in registry.entries
        )

    has_confirmed_prediction = False
    if paths.predictions_yaml.exists():
        plog = load_model(PredictionLog, paths.predictions_yaml)
        # Predictions don't carry target_id today; treat any confirmed
        # prediction as a project-level signal (badge surfaces on the
        # project root). When Prediction gains target_id this becomes
        # per-element.
        has_confirmed_prediction = any(p.resolution == "confirmed" for p in plog.entries)

    return MaturityBadges(
        has_evidence=has_evidence,
        has_challenges=has_challenges,
        has_formalism=has_formalism,
        has_quantification=has_quantification,
        has_confirmed_prediction=has_confirmed_prediction,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rewrite_findings(records: list[Finding], path: Path) -> None:
    """Atomically rewrite the findings JSONL file in place."""
    import json

    from ..repo.yaml_io import atomic_replace

    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        for r in records:
            f.write(json.dumps(r.model_dump(mode="json"), ensure_ascii=False) + "\n")
    atomic_replace(tmp, path)


__all__ = [
    "approve",
    "compute_badges",
    "mark_reviewed",
    "propose",
]
