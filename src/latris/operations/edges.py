"""Edge mutations. Every mutation auto-commits."""

from __future__ import annotations

from pathlib import Path

from latris.operations._resolve import resolve_edge, resolve_entity
from latris.operations.commit import auto_commit
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_model, load_model
from latris.schema import Edge, EdgeKind, Substrate, new_id


def _load(root: Path | None) -> tuple:
    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    return paths, substrate


def list_edges(root: Path | None = None) -> list[Edge]:
    _, substrate = _load(root)
    return list(substrate.edges)


def add_edge(
    from_query: str,
    to_query: str,
    *,
    kind: EdgeKind = "causal",
    root: Path | None = None,
) -> tuple[Edge, str]:
    paths, substrate = _load(root)
    src = resolve_entity(from_query, substrate.entities)
    dst = resolve_entity(to_query, substrate.entities)
    if src.id == dst.id:
        raise ValueError(f"self-loop: from and to resolve to the same node {src.id}")

    edge = Edge(id=new_id("edge"), from_id=src.id, to_id=dst.id, kind=kind)
    substrate.edges.append(edge)
    dump_model(substrate, paths.conceptual_yaml)
    sha = auto_commit(
        paths.root,
        subject=f'Added edge "{src.label}" → "{dst.label}" ({kind})',
        body=f"id: {edge.id}\nfrom: {src.id}\nto: {dst.id}",
        paths=[paths.conceptual_yaml],
    )
    return edge, sha


def retype_edge(
    query: str,
    new_kind: EdgeKind,
    *,
    root: Path | None = None,
) -> tuple[Edge, str]:
    paths, substrate = _load(root)
    edge = resolve_edge(query, substrate.edges)
    old_kind = edge.kind
    if old_kind == new_kind:
        raise ValueError(f"edge {edge.id} already has kind {new_kind!r}")
    edge.kind = new_kind

    labels = {e.id: e.label for e in substrate.entities}
    src_label = labels.get(edge.from_id, edge.from_id)
    dst_label = labels.get(edge.to_id, edge.to_id)

    dump_model(substrate, paths.conceptual_yaml)
    sha = auto_commit(
        paths.root,
        subject=f'Retyped edge "{src_label}" → "{dst_label}": {old_kind} → {new_kind}',
        body=f"id: {edge.id}",
        paths=[paths.conceptual_yaml],
    )
    return edge, sha


def remove_edge(
    query: str,
    *,
    rationale: str | None = None,
    root: Path | None = None,
) -> tuple[Edge, str]:
    paths, substrate = _load(root)
    edge = resolve_edge(query, substrate.edges)

    labels = {e.id: e.label for e in substrate.entities}
    src_label = labels.get(edge.from_id, edge.from_id)
    dst_label = labels.get(edge.to_id, edge.to_id)

    substrate.edges = [e for e in substrate.edges if e.id != edge.id]
    dump_model(substrate, paths.conceptual_yaml)
    body = f"id: {edge.id}"
    if rationale:
        body += f"\nrationale: {rationale}"
    sha = auto_commit(
        paths.root,
        subject=f'Removed edge "{src_label}" → "{dst_label}"',
        body=body,
        paths=[paths.conceptual_yaml],
    )
    return edge, sha
