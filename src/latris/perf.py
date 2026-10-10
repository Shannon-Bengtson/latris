"""Base-layer perf primitives shared by every package layer.

Lives at the package root (not under ``server/``) because operations
and ai/ also instrument hot spans, and the layering rule forbids them
from importing from ``server/``. The FastAPI middleware that drives
this is in :mod:`latris.server.perf`; everything else just uses
the :func:`span` context manager and the env-gated :func:`perf_enabled`
predicate.

When :envvar:`LATRIS_PERF` is unset (the default), :func:`span` is a
no-op and the in-request :class:`ContextVar` stays ``None`` — zero
cost in normal operation, zero impact on existing tests.
"""

from __future__ import annotations

import contextlib
import json
import os
import threading
import time
from contextvars import ContextVar
from pathlib import Path
from typing import Any

_PERF_ENV = "LATRIS_PERF"


def perf_enabled() -> bool:
    """Return True when telemetry is enabled via env var."""
    return os.environ.get(_PERF_ENV) == "1"


# Per-request state, populated by the middleware. ``None`` outside of
# a request — :func:`span` checks this and becomes a no-op.
perf_ctx: ContextVar[dict[str, Any] | None] = ContextVar("latris_perf_ctx", default=None)


def log_path() -> Path:
    """Resolve the NDJSON output path.

    Order: explicit :envvar:`LATRIS_PERF_LOG` override →
    ``<repo>/logs/perf-<port>.jsonl`` (matching the dev-server log
    naming).
    """
    explicit = os.environ.get("LATRIS_PERF_LOG")
    if explicit:
        return Path(explicit)
    port = os.environ.get("UVICORN_PORT") or os.environ.get("LATRIS_SERVER_PORT") or "8741"
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / "logs" / f"perf-{port}.jsonl"


_write_lock = threading.Lock()


def write_ndjson(record: dict[str, Any]) -> None:
    """Append one JSON record + newline to the perf log.

    Failures are swallowed: telemetry must never break a request.
    """
    try:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, separators=(",", ":"), default=str) + "\n"
        with _write_lock, path.open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception:  # noqa: BLE001 — telemetry is best-effort
        pass


@contextlib.contextmanager
def span(name: str, **fields: Any):
    """Time an inner block and attach it to the current request record.

    No-op outside an active request, so it's safe to drop into hot
    paths used by the CLI and tests.

    Usage::

        with span("auto_commit", paths=len(paths)):
            ...
    """
    ctx = perf_ctx.get()
    if ctx is None:
        yield
        return
    t0 = time.perf_counter_ns()
    try:
        yield
    finally:
        ctx["spans"].append(
            {
                "name": name,
                "dur_ms": round((time.perf_counter_ns() - t0) / 1e6, 2),
                **{k: v for k, v in fields.items() if v is not None},
            }
        )
