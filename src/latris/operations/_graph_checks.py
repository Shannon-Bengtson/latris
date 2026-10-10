"""Shared graph-structure checks (pure functions, no I/O)."""

from __future__ import annotations

from collections import defaultdict
from typing import Protocol


class _HasDirection(Protocol):
    from_id: str
    to_id: str


def find_cycle(edges: list[_HasDirection]) -> tuple[bool, str | None]:
    """DFS cycle detection. Returns ``(True, first_cyclic_node_id)`` or ``(False, None)``."""
    adj: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        adj[e.from_id].append(e.to_id)

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = defaultdict(int)

    def dfs(node: str) -> bool:
        color[node] = GRAY
        for neighbour in adj.get(node, []):
            if color[neighbour] == GRAY:
                return True
            if color[neighbour] == WHITE and dfs(neighbour):
                return True
        color[node] = BLACK
        return False

    all_nodes: set[str] = set()
    for e in edges:
        all_nodes.add(e.from_id)
        all_nodes.add(e.to_id)

    for node in all_nodes:
        if color[node] == WHITE and dfs(node):
            return True, node
    return False, None
