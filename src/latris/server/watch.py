"""File watcher + WebSocket push for CLI/GUI coexistence.

Monitors the project tree for changes to YAML/JSONL files and broadcasts
notifications to connected WebSocket clients.  The watcher uses
``watchfiles.awatch`` which already ignores ``.git/``, ``__pycache__/``,
etc. and debounces rapid changes.

Own-commit suppression: when the server itself mutates files via an API
endpoint, the response already carries the updated state.  To avoid a
redundant WebSocket push, the server sets a short suppression window
after each mutation.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from starlette.websockets import WebSocket

from latris._mutation_signal import (
    is_suppressed as _is_suppressed,
)
from latris._mutation_signal import (
    mark_own_mutation as mark_own_mutation,  # re-exported for callers that already imported it from here
)


class ConnectionManager:
    """Track active WebSocket connections and broadcast messages."""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self._connections:
            self._connections.remove(ws)

    async def broadcast(self, message: dict[str, Any]) -> None:
        payload = json.dumps(message)
        dead: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_text(payload)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    @property
    def active_count(self) -> int:
        return len(self._connections)


manager = ConnectionManager()


def _classify_scope(path_str: str) -> str | None:
    """Map a changed file path to a state scope for the push message.

    Returns ``None`` for files we don't care about (layout, reports/exports).
    """
    p = path_str.replace("\\", "/")
    if "/layout/" in p:
        return None
    if "/reports/exports/" in p:
        return None
    if "/substrate/" in p:
        if "/attributes/" in p:
            return "attributes"
        if "mappings" in p:
            return "mappings"
        return "substrate"
    if "/provenance/" in p:
        if "/elicitations/" in p:
            return "elicitations"
        return "provenance"
    if "/ai/" in p:
        if "challenges" in p:
            return "challenges"
        return "ai_interactions"
    if "/analysis/" in p:
        if "interpretation" in p:
            return "interpretation"
        return "findings"
    if "/data/" in p:
        return "datasets"
    if "/research-base/" in p:
        return "references"
    if "/views/" in p:
        if "completeness-report.yaml" in p:
            return "completeness"
        return "views"
    if "lineage-node.yaml" in p or "milestones.yaml" in p:
        return "lineage"
    if "project.yaml" in p:
        return "project"
    return "unknown"


async def watch_project(root: Path, stop_event: asyncio.Event) -> None:
    """Watch the project directory and broadcast changes via WebSocket.

    Runs as a background task; cancelled via ``stop_event``.
    """
    try:
        from watchfiles import awatch
    except ImportError:
        return  # watchfiles not installed; watcher disabled

    async for changes in awatch(root, stop_event=stop_event, debounce=1600):
        if _is_suppressed():
            continue

        scopes: set[str] = set()
        for _change_type, path_str in changes:
            scope = _classify_scope(path_str)
            if scope is not None:
                scopes.add(scope)

        if scopes and manager.active_count > 0:
            await manager.broadcast(
                {
                    "type": "state_changed",
                    "scopes": sorted(scopes),
                }
            )
