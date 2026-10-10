"""Node (Entity) mutations. Every mutation auto-commits."""

from __future__ import annotations

from pathlib import Path

from latris.operations._resolve import resolve_entity
from latris.operations.commit import auto_commit
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_model, load_model
from latris.schema import Entity, EntityKind, Substrate, new_id


def _load(root: Path | None) -> tuple:
    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    return paths, substrate


def list_nodes(root: Path | None = None) -> list[Entity]:
    _, substrate = _load(root)
    return list(substrate.entities)


def get_node(query: str, root: Path | None = None) -> Entity:
    _, substrate = _load(root)
    return resolve_entity(query, substrate.entities)


def add_node(
    label: str,
    *,
    kind: EntityKind = "concept",
    root: Path | None = None,
) -> tuple[Entity, str]:
    paths, substrate = _load(root)
    entity = Entity(id=new_id("node"), kind=kind, label=label)
    substrate.entities.append(entity)
    dump_model(substrate, paths.conceptual_yaml)
    sha = auto_commit(
        paths.root,
        subject=f'Added node "{label}" ({kind})',
        body=f"id: {entity.id}",
        paths=[paths.conceptual_yaml],
    )
    return entity, sha


def rename_node(
    query: str,
    new_label: str,
    *,
    root: Path | None = None,
) -> tuple[Entity, str]:
    paths, substrate = _load(root)
    entity = resolve_entity(query, substrate.entities)
    old_label = entity.label
    if old_label == new_label:
        raise ValueError(f"node {entity.id} already has label {new_label!r}")
    entity.label = new_label
    dump_model(substrate, paths.conceptual_yaml)
    sha = auto_commit(
        paths.root,
        subject=f'Renamed node {entity.id[:10]}… "{old_label}" → "{new_label}"',
        body=f"id: {entity.id}",
        paths=[paths.conceptual_yaml],
    )
    return entity, sha


def retype_node(
    query: str,
    new_kind: EntityKind,
    *,
    root: Path | None = None,
) -> tuple[Entity, str]:
    paths, substrate = _load(root)
    entity = resolve_entity(query, substrate.entities)
    old_kind = entity.kind
    if old_kind == new_kind:
        raise ValueError(f"node {entity.id} already has kind {new_kind!r}")
    entity.kind = new_kind
    dump_model(substrate, paths.conceptual_yaml)
    sha = auto_commit(
        paths.root,
        subject=f'Retyped node "{entity.label}": {old_kind} → {new_kind}',
        body=f"id: {entity.id}",
        paths=[paths.conceptual_yaml],
    )
    return entity, sha


def remove_node(
    query: str,
    *,
    rationale: str | None = None,
    root: Path | None = None,
) -> tuple[Entity, list[str], str]:
    """Remove a node and cascade-delete any edges it participates in.

    Returns (removed_entity, removed_edge_ids, commit_sha).
    """
    paths, substrate = _load(root)
    entity = resolve_entity(query, substrate.entities)

    doomed_edge_ids = [e.id for e in substrate.edges if e.from_id == entity.id or e.to_id == entity.id]
    substrate.entities = [e for e in substrate.entities if e.id != entity.id]
    substrate.edges = [e for e in substrate.edges if e.id not in doomed_edge_ids]
    dump_model(substrate, paths.conceptual_yaml)

    edge_note = f"\ncascaded {len(doomed_edge_ids)} edge(s): {', '.join(doomed_edge_ids)}" if doomed_edge_ids else ""
    body = f"id: {entity.id}{edge_note}"
    if rationale:
        body += f"\nrationale: {rationale}"
    sha = auto_commit(
        paths.root,
        subject=f'Removed node "{entity.label}"',
        body=body,
        paths=[paths.conceptual_yaml],
    )
    return entity, doomed_edge_ids, sha
