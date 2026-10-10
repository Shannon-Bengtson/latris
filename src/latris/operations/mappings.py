"""Mapping registry operations — link Layer-2 substrate elements to Layer-3 views.

Every mutation auto-commits.
"""

from __future__ import annotations

from pathlib import Path

from latris.operations._resolve import resolve_target as _resolve_l2_id
from latris.operations.commit import auto_commit
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_model, load_model
from latris.schema import Mapping, MappingRegistry, Substrate


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
    """Map a substrate element to a view. Returns (Mapping, commit_sha).

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
    dump_model(registry, paths.mappings_yaml)
    sha = auto_commit(
        paths.root,
        subject=f"Map {l2_id[:20]} to {view_kind}",
        body=None,
        provenance="human-authored",
        paths=[paths.mappings_yaml],
    )
    return mapping, sha


def unmap_from_view(
    l2_query: str,
    view_kind: str,
    *,
    root: Path | None = None,
) -> tuple[Mapping, str]:
    """Remove a mapping from a view. Returns (removed_mapping, commit_sha)."""
    paths, registry, substrate = _load(root)
    l2_id = _resolve_l2_id(l2_query, substrate)

    found = None
    for i, m in enumerate(registry.entries):
        if m.l2_id == l2_id and m.l3_view == view_kind:
            found = registry.entries.pop(i)
            break

    if found is None:
        raise ValueError(f"{l2_id} is not mapped to {view_kind}")

    dump_model(registry, paths.mappings_yaml)
    sha = auto_commit(
        paths.root,
        subject=f"Unmap {l2_id[:20]} from {view_kind}",
        body=None,
        provenance="human-authored",
        paths=[paths.mappings_yaml],
    )
    return found, sha


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
