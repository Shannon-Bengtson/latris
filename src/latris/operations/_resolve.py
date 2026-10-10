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


def resolve_target(query: str, substrate) -> str:
    """Return the stable ID of whichever Entity or Edge *query* points at."""
    try:
        return resolve_entity(query, substrate.entities).id
    except ValueError:
        return resolve_edge(query, substrate.edges).id
