"""Unit tests for the file watcher + WebSocket push (server/watch.py).

Covers scope classification paths not tested by the existing
test_websocket.py, the ConnectionManager, and suppression window.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock

from latris.server.watch import (
    ConnectionManager,
    _classify_scope,
    _is_suppressed,
    mark_own_mutation,
)

# ── _classify_scope — paths not covered by test_websocket.py ────────


def test_classify_data_datasets() -> None:
    assert _classify_scope("/project/data/datasets.yaml") == "datasets"


def test_classify_analysis_interpretation() -> None:
    assert _classify_scope("/project/analysis/interpretation.yaml") == "interpretation"


def test_classify_analysis_findings() -> None:
    assert _classify_scope("/project/analysis/findings.jsonl") == "findings"


def test_classify_lineage_node() -> None:
    assert _classify_scope("/project/lineage-node.yaml") == "lineage"


def test_classify_milestones() -> None:
    assert _classify_scope("/project/milestones.yaml") == "lineage"


def test_classify_unknown() -> None:
    assert _classify_scope("/project/something/random.txt") == "unknown"


def test_classify_windows_backslashes() -> None:
    assert _classify_scope("C:\\project\\substrate\\conceptual.yaml") == "substrate"


def test_classify_windows_provenance() -> None:
    assert _classify_scope("C:\\project\\provenance\\assumptions.yaml") == "provenance"


# ── ConnectionManager ───────────────────────────────────────────────


def _run(coro):
    """Helper to run an async coroutine synchronously."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_connect_and_count() -> None:
    mgr = ConnectionManager()
    ws = AsyncMock()
    _run(mgr.connect(ws))
    assert mgr.active_count == 1
    ws.accept.assert_awaited_once()


def test_disconnect() -> None:
    mgr = ConnectionManager()
    ws = AsyncMock()
    _run(mgr.connect(ws))
    mgr.disconnect(ws)
    assert mgr.active_count == 0


def test_disconnect_nonexistent_is_noop() -> None:
    mgr = ConnectionManager()
    ws = AsyncMock()
    mgr.disconnect(ws)  # should not raise
    assert mgr.active_count == 0


def test_broadcast_sends_to_all() -> None:
    mgr = ConnectionManager()
    ws1 = AsyncMock()
    ws2 = AsyncMock()
    _run(mgr.connect(ws1))
    _run(mgr.connect(ws2))
    _run(mgr.broadcast({"type": "test"}))
    ws1.send_text.assert_awaited_once()
    ws2.send_text.assert_awaited_once()


def test_broadcast_removes_dead_connections() -> None:
    mgr = ConnectionManager()
    live_ws = AsyncMock()
    dead_ws = AsyncMock()
    dead_ws.send_text.side_effect = RuntimeError("connection closed")
    _run(mgr.connect(live_ws))
    _run(mgr.connect(dead_ws))
    assert mgr.active_count == 2

    _run(mgr.broadcast({"type": "test"}))
    assert mgr.active_count == 1  # dead one removed
    live_ws.send_text.assert_awaited_once()


# ── Suppression window ──────────────────────────────────────────────


def test_mark_own_mutation_suppresses() -> None:
    mark_own_mutation()
    assert _is_suppressed() is True


def test_suppression_expires() -> None:
    """After the suppression window, _is_suppressed should return False."""
    import latris._mutation_signal as sig

    # Simulate a mutation that happened well in the past
    sig._last_own_mutation = time.monotonic() - 10.0
    assert _is_suppressed() is False
