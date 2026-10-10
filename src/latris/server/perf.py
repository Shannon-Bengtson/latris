"""FastAPI middleware that drives the perf telemetry layer.

The primitives (``span``, ``perf_ctx``, ``write_ndjson``) live in
:mod:`latris.perf` so that operations/ and ai/ can instrument
hot paths without violating the package layering rule
(``server/`` is at the same layer as ``cli/`` — neither can be
imported by ``operations/``).

Enabled by setting :envvar:`LATRIS_PERF=1`. When disabled (the
default), the middleware short-circuits so there is zero cost in
normal operation and existing tests are unaffected.

When enabled, every request gets:

- A correlation id (``x-request-id`` header, generated if absent).
- An end-to-end duration logged as a ``request`` record.
- Nested ``span(...)`` blocks for inner work (auto_commit,
  load_full_state, build_context, adapter.chat) recorded in the
  same record.
- A ``server-timing`` response header so the GUI can show total
  server time without a second round-trip.

Output is NDJSON appended to ``logs/perf-<port>.jsonl`` and is
queryable with ``jq``.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware

from latris.perf import perf_ctx, perf_enabled, write_ndjson


class PerfMiddleware(BaseHTTPMiddleware):
    """Times every request when ``LATRIS_PERF=1``; no-op otherwise.

    The env check happens per request, not per install, so operators
    can flip telemetry on without restarting the worker pool.
    """

    async def dispatch(self, request, call_next):  # type: ignore[override]
        if not perf_enabled():
            return await call_next(request)

        rid = request.headers.get("x-request-id") or uuid4().hex
        ctx: dict[str, Any] = {"rid": rid, "spans": []}
        token = perf_ctx.set(ctx)
        t0 = time.perf_counter_ns()
        response = None
        status = 0
        try:
            response = await call_next(request)
            status = getattr(response, "status_code", 0)
            return response
        finally:
            dur_ms = round((time.perf_counter_ns() - t0) / 1e6, 2)
            write_ndjson(
                {
                    "t": datetime.now(UTC).isoformat(),
                    "rid": rid,
                    "kind": "request",
                    "method": request.method,
                    "path": str(request.url.path),
                    "status": status,
                    "dur_ms": dur_ms,
                    "spans": ctx["spans"],
                }
            )
            if response is not None:
                try:
                    response.headers["x-request-id"] = rid
                    response.headers["server-timing"] = f"total;dur={dur_ms}"
                except AttributeError:
                    pass
            perf_ctx.reset(token)
