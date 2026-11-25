"""Telemetry event envelope + versioned payload registry.

One envelope, many event types: extensibility comes from registering new
payload models, never from schema churn — the same pattern the AI layer
uses for prompts (``ai.registry.register_prompt``). See
``docs/engineering/TELEMETRY.md`` for the design.

The envelope carries only metadata and join keys (``actor_ref`` is
pseudonymous, never an email); event payloads carry outcome statistics,
never prompt text, model content, or project payloads.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from latris.schema._base import SchemaModel
from latris.schema.common import now_utc
from latris.schema.ids import new_id

Surface = Literal["cli", "gui", "mcp", "server", "broker", "ci"]


class TelemetryEvent(SchemaModel):
    """One row in the telemetry stream. Same envelope on both tiers (local
    JSONL in the project, hosted telemetry service)."""

    id: str = Field(default_factory=lambda: new_id("telemetry-event"))
    at: datetime = Field(default_factory=now_utc)  # client clock; the hosted
    # service stamps receipt_ts separately on ingest
    surface: Surface
    event_type: str
    type_version: int = 1  # payload schema version for this event_type
    actor_ref: str | None = None  # pseudonymous; None for anonymous local use
    project_id: str | None = None  # None for pre-project events
    session_id: str | None = None  # per-surface session (GUI tab, broker session)
    payload: dict = Field(default_factory=dict)


# ---------- payload models (v1) ----------


class AICallCompletedPayload(SchemaModel):
    """One AI call, terminal state. Emitted alongside the AIInteraction
    record; ``interaction_id`` is the join key to ``ai/interactions.jsonl``."""

    interaction_id: str
    prompt_name: str
    model_id: str
    adoption: Literal["pending", "approved", "rejected", "failed"]
    latency_ms: int | None = None
    token_usage: dict = Field(default_factory=dict)
    cost_usd: float | None = None
    rejection_reason: str | None = None
    error_class: str | None = None


class AIProposalOutcomePayload(SchemaModel):
    """Post-hoc outcome of an approved proposal, computed by the hosted
    sweeper from the project's git history — never by clients."""

    interaction_id: str
    outcome: Literal["survived-unedited", "edited", "reverted"]
    window_days: int


class GuiFeaturePayload(SchemaModel):
    feature: str  # panel / prompt / chain-step key
    action: Literal["opened", "started", "completed", "abandoned"]
    dwell_ms: int | None = None


class McpToolPayload(SchemaModel):
    tool_name: str
    outcome: Literal["success", "error"]
    latency_ms: int | None = None
    client_family: str | None = None


class SessionLifecyclePayload(SchemaModel):
    action: Literal["start", "end"]
    duration_s: float | None = None
    event_count: int | None = None


class ProjectLifecyclePayload(SchemaModel):
    action: Literal["created", "saved", "shared", "archived"]


class ErrorObservedPayload(SchemaModel):
    error_class: str
    context: str | None = None  # route/command key, never a traceback


class CliCommandPayload(SchemaModel):
    """Deferred with T3 (CLI telemetry excluded for now); specified so the
    envelope and registry are ready when the decision is revisited."""

    command: str  # command path only ("mcda score") — no arguments, no values
    exit_class: Literal["success", "error"]
    duration_ms: int | None = None
    latris_version: str | None = None
    formalisms: list[str] = Field(default_factory=list)


# ---------- registry ----------


EVENT_PAYLOADS: dict[tuple[str, int], type[SchemaModel]] = {}


def register_event_type(
    name: str,
    model: type[SchemaModel],
    *,
    version: int = 1,
) -> None:
    """Register a payload model for ``name`` at ``version``.

    Registering the same (name, version) twice with a different model is a
    programming error, not a conflict to resolve — raise.
    """
    key = (name, version)
    existing = EVENT_PAYLOADS.get(key)
    if existing is not None and existing is not model:
        raise ValueError(
            f"event type {name!r} v{version} already registered to {existing.__name__}"
        )
    EVENT_PAYLOADS[key] = model


def validate_payload(
    event_type: str,
    type_version: int,
    payload: dict,
) -> SchemaModel:
    """Validate ``payload`` against the registered model.

    Unknown (type, version) pairs raise KeyError — emitters treat that as a
    programming error caught by tests; the hosted ingest rejects them.
    """
    key = (event_type, type_version)
    if key not in EVENT_PAYLOADS:
        known = ", ".join(sorted(f"{n} v{v}" for n, v in EVENT_PAYLOADS))
        raise KeyError(f"unknown event type {event_type!r} v{type_version}. Known: {known}")
    return EVENT_PAYLOADS[key].model_validate(payload)


def _register_builtins() -> None:
    register_event_type("ai.call.completed", AICallCompletedPayload)
    register_event_type("ai.proposal.outcome", AIProposalOutcomePayload)
    register_event_type("gui.feature", GuiFeaturePayload)
    register_event_type("mcp.tool", McpToolPayload)
    register_event_type("session.lifecycle", SessionLifecyclePayload)
    register_event_type("project.lifecycle", ProjectLifecyclePayload)
    register_event_type("error.observed", ErrorObservedPayload)
    register_event_type("cli.command", CliCommandPayload)  # deferred with T3


_register_builtins()


__all__ = [
    "AICallCompletedPayload",
    "AIProposalOutcomePayload",
    "CliCommandPayload",
    "EVENT_PAYLOADS",
    "ErrorObservedPayload",
    "GuiFeaturePayload",
    "McpToolPayload",
    "ProjectLifecyclePayload",
    "SessionLifecyclePayload",
    "Surface",
    "TelemetryEvent",
    "register_event_type",
    "validate_payload",
]
