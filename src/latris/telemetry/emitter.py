"""The telemetry emitter.

``emit()`` builds a :class:`TelemetryEvent`, validates its payload against
the registry, appends it to the local JSONL mirror, and — only when the
project config opts in — POSTs it to the hosted telemetry service.

``emit_envelopes()`` is the server relay path: envelopes the GUI built
(client id, client clock, session id), re-validated here so nothing
unvalidated enters the stream, mirrored locally, then uploaded as one
batched POST when configured.

Telemetry is observability, not product logic: every failure mode (no
project, unknown event type, network down, endpoint 500) degrades to a
logged-and-dropped event. Both entry points never raise; ``emit`` returns
the event on success and ``None`` otherwise, ``emit_envelopes`` returns
how many events were accepted.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from pathlib import Path

from pydantic import ValidationError

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
# Bearer token for the hosted ingest, when the deployment sets one. A secret,
# so an env var — never the committed project config. Empty = no header.
TOKEN_ENV_VAR = "LATRIS_TELEMETRY_TOKEN"
# Set by whoever hosts the server for others (on each session), never by an
# end user's own install: where to send
# events, and the session's pseudonymous actor. A project's telemetry.yaml can
# still switch telemetry off (``enabled: false``).
ENDPOINT_ENV_VAR = "LATRIS_TELEMETRY_ENDPOINT"
ACTOR_ENV_VAR = "LATRIS_TELEMETRY_ACTOR"


def upload_endpoint(cfg: telemetry_config.TelemetryConfig) -> str | None:
    """Where events go: the hosted operator's endpoint, else the project's opt-in one, else nowhere."""
    hosted = os.environ.get(ENDPOINT_ENV_VAR, "").strip()
    if hosted:
        return hosted
    if cfg.upload_enabled and cfg.endpoint_url:
        return cfg.endpoint_url
    return None


def _env_actor() -> str | None:
    return os.environ.get(ACTOR_ENV_VAR, "").strip() or None


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
        actor_ref=actor_ref or _env_actor(),
        project_id=project_id,
        session_id=session_id,
        payload=dict(payload),
    )
    dump_jsonl_append(event, paths.telemetry_jsonl)

    endpoint = upload_endpoint(cfg)
    if endpoint:
        # The local mirror is primary; upload is fire-and-forget. A failed
        # upload drops the remote copy, not the event.
        try:  # noqa: SIM105
            _upload(endpoint, event)
        except Exception as exc:  # noqa: BLE001
            log.debug("telemetry upload of %s failed: %s", event.id, exc)
    return event


def emit_envelopes(
    events: list[TelemetryEvent],
    *,
    root: Path | None = None,
) -> int:
    """Persist client-built envelopes (the server's GUI relay path).

    Unlike :func:`emit`, these arrive fully formed — client id, client
    clock, session id — with the surface already stamped by the relay.
    Every payload is validated against the registry again here: nothing
    unvalidated enters the stream, whoever the caller is. The local mirror
    is primary; an opted-in upload forwards the whole batch in one POST.
    Never raises; returns how many events were accepted (zero when the
    project config has telemetry off).
    """
    try:
        return _emit_envelopes(events, root=root)
    except Exception as exc:  # noqa: BLE001 — telemetry must never break the tool
        log.debug("telemetry batch dropped: %s", exc)
        return 0


def _emit_envelopes(events: list[TelemetryEvent], *, root: Path | None) -> int:
    paths = require_project(root)
    cfg = telemetry_config.load(paths)
    if not cfg.enabled:
        return 0
    actor = _env_actor()
    valid: list[TelemetryEvent] = []
    for event in events:
        try:
            validate_payload(event.event_type, event.type_version, event.payload)
        except (KeyError, ValidationError) as exc:
            log.debug("telemetry event %s dropped: %s", event.id, exc)
            continue
        # The GUI doesn't know who it is; the hosted container does.
        valid.append(event if event.actor_ref or not actor else event.model_copy(update={"actor_ref": actor}))
    for event in valid:
        dump_jsonl_append(event, paths.telemetry_jsonl)
    endpoint = upload_endpoint(cfg)
    if valid and endpoint:
        # The local mirror is primary; upload is fire-and-forget, one POST
        # for the whole batch. A failed upload drops the remote copies.
        try:  # noqa: SIM105
            _upload_batch(endpoint, valid)
        except Exception as exc:  # noqa: BLE001
            log.debug("telemetry batch upload failed: %s", exc)
    return len(valid)


def _upload(endpoint_url: str, event: TelemetryEvent) -> None:
    """POST one event to the hosted telemetry service. Best-effort."""
    _post_events(endpoint_url, [event])


def _upload_batch(endpoint_url: str, events: list[TelemetryEvent]) -> None:
    """POST a batch of events in one request (the relay path). Best-effort."""
    _post_events(endpoint_url, events)


def _post_events(endpoint_url: str, events: list[TelemetryEvent]) -> None:
    body = json.dumps({"events": [event.model_dump(mode="json") for event in events]}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    token = os.environ.get(TOKEN_ENV_VAR, "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(endpoint_url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=_UPLOAD_TIMEOUT_S) as resp:  # noqa: S310
        # endpoint_url is operator-configured project config, not user input
        if resp.status >= 400:
            raise RuntimeError(f"telemetry ingest returned {resp.status}")
