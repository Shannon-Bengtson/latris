"""Edge mutations. Every mutation auto-commits."""

from __future__ import annotations

from pathlib import Path

from latris.operations._cascade import cascade_removed_ids
from latris.operations._resolve import resolve_edge, resolve_edge_by_name, resolve_entity
from latris.operations._words import a_or_an
from latris.operations.commit import auto_commit
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_model, load_model
from latris.schema import Edge, EdgeKind, Substrate, new_id
from latris.schema.common import default_origin


def _load(root: Path | None) -> tuple:
    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    return paths, substrate


def list_edges(root: Path | None = None) -> list[Edge]:
    _, substrate = _load(root)
    return list(substrate.edges)


class DuplicateEdgeError(ValueError):
    """An edge of the same kind already joins these two nodes."""

    def __init__(self, existing: Edge, from_label: str, to_label: str) -> None:
        self.existing = existing
        super().__init__(
            f'{a_or_an(existing.kind)} link "{from_label}" → "{to_label}" already exists ({existing.id}); '
            "edit that one instead of adding a second"
        )


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
    for existing in substrate.edges:
        if existing.from_id == src.id and existing.to_id == dst.id and existing.kind == kind:
            raise DuplicateEdgeError(existing, src.label, dst.label)

    edge = Edge(id=new_id("edge"), from_id=src.id, to_id=dst.id, kind=kind, origin=default_origin())
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
    edge = resolve_edge_by_name(query, substrate) or resolve_edge(query, substrate.edges)  # "A -> B" or an id
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
    edge = resolve_edge_by_name(query, substrate) or resolve_edge(query, substrate.edges)  # "A -> B" or an id

    labels = {e.id: e.label for e in substrate.entities}
    src_label = labels.get(edge.from_id, edge.from_id)
    dst_label = labels.get(edge.to_id, edge.to_id)

    substrate.edges = [e for e in substrate.edges if e.id != edge.id]
    dump_model(substrate, paths.conceptual_yaml)
    changed, rows_removed = cascade_removed_ids(paths, [edge.id])
    body = f"id: {edge.id}"
    if rows_removed:
        body += f"\nremoved {rows_removed} dependent row(s) from {len(changed)} file(s)"
    if rationale:
        body += f"\nrationale: {rationale}"
    sha = auto_commit(
        paths.root,
        subject=f'Removed edge "{src_label}" → "{dst_label}"',
        body=body,
        paths=[paths.conceptual_yaml, *changed],
    )
    return edge, sha
