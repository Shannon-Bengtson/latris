"""Mapping registry operations — which factors and links are in which model type's view.

Every factor and link is in every chosen model type unless a person leaves it out: opening a type adds
whatever isn't mapped yet (``views.auto_project``), except what's been left out, which is recorded so it
stays out. Mapping an element again puts it back. Every mutation auto-commits.
"""

from __future__ import annotations

from pathlib import Path

from latris.operations._resolve import resolve_target as _resolve_l2_id
from latris.operations.commit import auto_commit
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_model, load_model
from latris.schema import LeftOut, Mapping, MappingRegistry, Substrate


def _load(root: Path | None):
    paths = require_project(root)
    registry = load_model(MappingRegistry, paths.mappings_yaml)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    return paths, registry, substrate


def map_to_view(
    l2_query: str,
    view_kind: str,
    *,
    l3_id: str | None = None,
    ai_proposed: bool = False,
    root: Path | None = None,
) -> tuple[Mapping, str]:
    """Map a substrate element to a view (putting it back if it was left out). Returns (Mapping, commit_sha).

    AI-proposed mappings land at ``maturity="proposed"`` and
    ``origin="ai-proposed"``; human-direct mappings auto-approve.
    """
    paths, registry, substrate = _load(root)
    l2_id = _resolve_l2_id(l2_query, substrate)
    effective_l3_id = l3_id or l2_id

    # Check for duplicate
    for m in registry.entries:
        if m.l2_id == l2_id and m.l3_view == view_kind:
            raise ValueError(f"{l2_id} is already mapped to {view_kind}")

    mapping = Mapping(
        l2_id=l2_id,
        l3_view=view_kind,
        l3_id=effective_l3_id,
        origin="ai-proposed" if ai_proposed else "human-direct",
        maturity="proposed" if ai_proposed else "approved",
    )
    registry.entries.append(mapping)
    registry.left_out = [x for x in registry.left_out if not (x.l2_id == l2_id and x.l3_view == view_kind)]
    dump_model(registry, paths.mappings_yaml)
    sha = auto_commit(
        paths.root,
        subject=f"Map {l2_id[:20]} to {view_kind}",
        body=None,
        provenance="human-authored",
        paths=[paths.mappings_yaml],
    )
    return mapping, sha


def leave_out(
    l2_query: str,
    view_kind: str,
    *,
    reason: str | None = None,
    root: Path | None = None,
) -> tuple[LeftOut, str]:
    """Leave a factor or link out of a model type's view, and keep it out (mapping it again puts it back).
    Returns (LeftOut, commit_sha)."""
    paths, registry, substrate = _load(root)
    l2_id = _resolve_l2_id(l2_query, substrate)
    if registry.is_left_out(l2_id, view_kind):
        raise ValueError(f"{l2_id} is already left out of {view_kind}")

    registry.entries = [m for m in registry.entries if not (m.l2_id == l2_id and m.l3_view == view_kind)]
    entry = LeftOut(l2_id=l2_id, l3_view=view_kind, reason=reason)
    registry.left_out.append(entry)
    dump_model(registry, paths.mappings_yaml)
    sha = auto_commit(
        paths.root,
        subject=f"Leave {l2_id[:20]} out of {view_kind}",
        body=reason,
        provenance="human-authored",
        paths=[paths.mappings_yaml],
    )
    return entry, sha


def list_mappings(
    view_kind: str | None = None,
    *,
    root: Path | None = None,
) -> list[Mapping]:
    """List mappings, optionally filtered by view_kind."""
    _, registry, _ = _load(root)
    if view_kind is None:
        return list(registry.entries)
    return [m for m in registry.entries if m.l3_view == view_kind]


def list_left_out(view_kind: str | None = None, *, root: Path | None = None) -> list[LeftOut]:
    """What's been left out of a view (of ``view_kind``, or every view)."""
    _, registry, _ = _load(root)
    return [x for x in registry.left_out if view_kind is None or x.l3_view == view_kind]


def approve_mapping(
    l2_query: str,
    view_kind: str,
    *,
    root: Path | None = None,
) -> tuple[Mapping, str]:
    """Mark an existing mapping as approved (``maturity="approved"``)."""
    paths, registry, substrate = _load(root)
    l2_id = _resolve_l2_id(l2_query, substrate)

    for m in registry.entries:
        if m.l2_id == l2_id and m.l3_view == view_kind:
            m.maturity = "approved"
            dump_model(registry, paths.mappings_yaml)
            sha = auto_commit(
                paths.root,
                subject=f"Approve mapping {l2_id[:20]} ↔ {view_kind}",
                body=None,
                provenance="human-authored",
                paths=[paths.mappings_yaml],
            )
            return m, sha

    raise ValueError(f"No mapping found for {l2_id} → {view_kind}")
