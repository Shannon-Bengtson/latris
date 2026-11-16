"""Node (Entity) mutations. Every mutation auto-commits."""

from __future__ import annotations

from pathlib import Path

from latris.operations._cascade import cascade_removed_ids
from latris.operations._resolve import resolve_entity
from latris.operations.commit import auto_commit
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_model, load_model
from latris.schema import Entity, EntityKind, Substrate, new_id
from latris.schema.common import default_origin


def _load(root: Path | None) -> tuple:
    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    return paths, substrate


def _label_key(label: str) -> str:
    return " ".join(label.split()).casefold()


def _ensure_label_free(label: str, substrate: Substrate, *, except_id: str | None = None) -> None:
    """Labels address nodes (CLI, build specs, AI applies), so two nodes can't share one.

    Compared case- and whitespace-insensitively, matching how labels resolve.
    """
    key = _label_key(label)
    for e in substrate.entities:
        if e.id != except_id and _label_key(e.label) == key:
            raise ValueError(f'a node is already called "{e.label}" ({e.id}); labels must be unique')


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
    _ensure_label_free(label, substrate)
    entity = Entity(id=new_id("node"), kind=kind, label=label, origin=default_origin())
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
    _ensure_label_free(new_label, substrate, except_id=entity.id)
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
    """Remove a node, the edges it participates in, and every row about them.

    Descriptions, confidence, citations, parameter values, roles, mappings
    and view membership for the node and its edges are removed in the same
    commit (see ``_cascade``). Audit records — challenges, findings,
    signoffs — are kept as history.

    Returns (removed_entity, removed_edge_ids, commit_sha).
    """
    paths, substrate = _load(root)
    entity = resolve_entity(query, substrate.entities)

    doomed_edge_ids = [e.id for e in substrate.edges if e.from_id == entity.id or e.to_id == entity.id]
    substrate.entities = [e for e in substrate.entities if e.id != entity.id]
    substrate.edges = [e for e in substrate.edges if e.id not in doomed_edge_ids]
    dump_model(substrate, paths.conceptual_yaml)
    changed, rows_removed = cascade_removed_ids(paths, [entity.id, *doomed_edge_ids])

    edge_note = f"\ncascaded {len(doomed_edge_ids)} edge(s): {', '.join(doomed_edge_ids)}" if doomed_edge_ids else ""
    body = f"id: {entity.id}{edge_note}"
    if rows_removed:
        body += f"\nremoved {rows_removed} dependent row(s) from {len(changed)} file(s)"
    if rationale:
        body += f"\nrationale: {rationale}"
    sha = auto_commit(
        paths.root,
        subject=f'Removed node "{entity.label}"',
        body=body,
        paths=[paths.conceptual_yaml, *changed],
    )
    return entity, doomed_edge_ids, sha
