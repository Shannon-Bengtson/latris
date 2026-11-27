"""GUI telemetry relay — the server's telemetry ingest.

The GUI beacons batched event envelopes here (docs/engineering/TELEMETRY.md).
The relay stamps ``surface="gui"`` — a client never names its own
surface through this route — validates every payload against the registry
(atomically: one bad payload 422s the whole batch), then persists through
the emitter: the project's local JSONL mirror is primary, and an opted-in
upload forwards the batch to the hosted telemetry service. Self-hosted
deployments keep their events in their own project; older backends have no
such route and answer 404, which is the GUI beacon's cue to stay silent.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import Field, ValidationError

from latris.schema._base import SchemaModel
from latris.schema.events import TelemetryEvent, validate_payload
from latris.server.deps import Root
from latris.telemetry import emit_envelopes

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])

# Where each route sits in the workflow (schema/workflow.py; rules in docs/engineering/WORKFLOW_STRUCTURE.md).
PLACE = "project"

_MAX_BATCH = 500  # same cap as the hosted service's ingest


class TelemetryBatch(SchemaModel):
    """A beacon flush: envelopes the client built (id, clock, session id)."""

    events: list[TelemetryEvent] = Field(max_length=_MAX_BATCH)


@router.post("/events")
def post_events(body: TelemetryBatch, root: Root) -> dict[str, Any]:
    """Ingest a batch of GUI telemetry envelopes.

    Strict on purpose: a malformed envelope or unknown (type, version) is a
    programming error that tests should catch, so the batch fails loudly
    rather than persisting a stream the read models can't trust. Accepted
    events are then best-effort — persistence follows the project's
    telemetry config, and ``accepted`` is how many entered the stream.
    """
    stamped = [event.model_copy(update={"surface": "gui"}) for event in body.events]
    errors: list[dict[str, Any]] = []
    for index, event in enumerate(stamped):
        try:
            validate_payload(event.event_type, event.type_version, event.payload)
        except (KeyError, ValidationError) as exc:
            errors.append({"index": index, "msg": f"{event.event_type} v{event.type_version}: {exc}"})
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    return {"accepted": emit_envelopes(stamped, root=root)}
