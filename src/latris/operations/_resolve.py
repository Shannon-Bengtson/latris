"""Shared ID resolution helpers used by node and edge operations.

Users rarely type full 26-char ULIDs. These helpers accept:

1. A full stable ID (exact match).
2. An unambiguous ID prefix (minimum 4 chars after the underscore).
3. A node label (exact, case-insensitive) — nodes only.
"""

from __future__ import annotations

from latris.schema import Edge, Entity


class ResolveError(ValueError):
    """Raised when a reference cannot be resolved uniquely."""


_MIN_PREFIX = 4


def _by_id_exact(query: str, candidates: list) -> list:
    return [c for c in candidates if c.id == query]


def _by_id_prefix(query: str, candidates: list) -> list:
    # Only honour a prefix if the user included the kind separator or enough chars.
    if "_" not in query and len(query) < _MIN_PREFIX:
        return []
    return [c for c in candidates if c.id.startswith(query)]


def resolve_entity(query: str, entities: list[Entity]) -> Entity:
    exact = _by_id_exact(query, entities)
    if len(exact) == 1:
        return exact[0]

    by_label = [e for e in entities if e.label.casefold() == query.casefold()]
    if len(by_label) == 1:
        return by_label[0]
    if len(by_label) > 1:
        ids = ", ".join(e.id for e in by_label)
        raise ResolveError(f"label {query!r} is ambiguous (matches: {ids})")

    prefix = _by_id_prefix(query, entities)
    if len(prefix) == 1:
        return prefix[0]
    if len(prefix) > 1:
        ids = ", ".join(e.id for e in prefix)
        raise ResolveError(f"prefix {query!r} is ambiguous (matches: {ids})")

    raise ResolveError(f"no node matches {query!r}")


def resolve_edge(query: str, edges: list[Edge]) -> Edge:
    exact = _by_id_exact(query, edges)
    if len(exact) == 1:
        return exact[0]

    prefix = _by_id_prefix(query, edges)
    if len(prefix) == 1:
        return prefix[0]
    if len(prefix) > 1:
        ids = ", ".join(e.id for e in prefix)
        raise ResolveError(f"edge prefix {query!r} is ambiguous (matches: {ids})")

    raise ResolveError(f"no edge matches {query!r}")


def resolve_edge_by_name(query: str, substrate) -> Edge | None:
    """``"Workload -> Burnout"`` (or ``→``): the link between two factors named by label, or None."""
    from latris.schema.build_spec import LINK_ARROWS

    arrow = next((a for a in LINK_ARROWS if a in query), None)
    if arrow is None:
        return None
    a, b = (part.strip() for part in query.split(arrow, 1))
    src, dst = resolve_entity(a, substrate.entities), resolve_entity(b, substrate.entities)
    found = [e for e in substrate.edges if e.from_id == src.id and e.to_id == dst.id]
    if len(found) > 1:
        raise ResolveError(f"{query!r} matches {len(found)} links; use an edge ID ({', '.join(e.id for e in found)})")
    if not found:
        raise ResolveError(f"no link from {src.label!r} to {dst.label!r}")
    return found[0]


def resolve_target(query: str, substrate) -> str:
    """Return the stable ID of whichever Entity or Edge *query* points at."""
    try:
        return resolve_entity(query, substrate.entities).id
    except ValueError:
        named = resolve_edge_by_name(query, substrate)  # "A -> B", after labels (a label may hold "->")
        if named is not None:
            return named.id
        return resolve_edge(query, substrate.edges).id
