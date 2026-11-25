"""The telemetry emitter.

``emit()`` builds a :class:`TelemetryEvent`, validates its payload against
the registry, appends it to the local JSONL mirror, and — only when the
project config opts in — POSTs it to the hosted telemetry service.

Telemetry is observability, not product logic: every failure mode (no
project, unknown event type, network down, endpoint 500) degrades to a
logged-and-dropped event. ``emit`` returns the event on success and ``None``
otherwise, and never raises.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from pathlib import Path

from latris.repo.project import require_project
from latris.repo.yaml_io import dump_jsonl_append
from latris.schema.events import (
    Surface,
    TelemetryEvent,
    validate_payload,
)
from latris.telemetry import config as telemetry_config

log = logging.getLogger(__name__)

_UPLOAD_TIMEOUT_S = 5


def emit(
    event_type: str,
    payload: dict,
    *,
    surface: Surface,
    root: Path | None = None,
    type_version: int = 1,
    actor_ref: str | None = None,
    project_id: str | None = None,
    session_id: str | None = None,
) -> TelemetryEvent | None:
    """Record one telemetry event. Never raises; returns None on any failure."""
    try:
        return _emit(
            event_type,
            payload,
            surface=surface,
            root=root,
            type_version=type_version,
            actor_ref=actor_ref,
            project_id=project_id,
            session_id=session_id,
        )
    except Exception as exc:  # noqa: BLE001 — telemetry must never break the tool
        log.debug("telemetry event %s dropped: %s", event_type, exc)
        return None


def _emit(
    event_type: str,
    payload: dict,
    *,
    surface: Surface,
    root: Path | None,
    type_version: int,
    actor_ref: str | None,
    project_id: str | None,
    session_id: str | None,
) -> TelemetryEvent | None:
    paths = require_project(root)
    cfg = telemetry_config.load(paths)
    if not cfg.enabled:
        return None

    # Payload validation is strict: an unknown (type, version) or a malformed
    # payload is a programming error caught by tests, so it raises here and is
    # swallowed by the emit() wrapper rather than written to the stream.
    validate_payload(event_type, type_version, payload)

    event = TelemetryEvent(
        surface=surface,
        event_type=event_type,
        type_version=type_version,
        actor_ref=actor_ref,
        project_id=project_id,
        session_id=session_id,
        payload=dict(payload),
    )
    dump_jsonl_append(event, paths.telemetry_jsonl)

    if cfg.upload_enabled and cfg.endpoint_url:
        # The local mirror is primary; upload is fire-and-forget. A failed
        # upload drops the remote copy, not the event.
        try:  # noqa: SIM105
            _upload(cfg.endpoint_url, event)
        except Exception as exc:  # noqa: BLE001
            log.debug("telemetry upload of %s failed: %s", event.id, exc)
    return event


def _upload(endpoint_url: str, event: TelemetryEvent) -> None:
    """POST one event to the hosted telemetry service. Best-effort."""
    body = json.dumps({"events": [event.model_dump(mode="json")]}).encode("utf-8")
    req = urllib.request.Request(
        endpoint_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=_UPLOAD_TIMEOUT_S) as resp:  # noqa: S310
        # endpoint_url is operator-configured project config, not user input
        if resp.status >= 400:
            raise RuntimeError(f"telemetry ingest returned {resp.status}")
