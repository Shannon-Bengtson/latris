"""Tests for the telemetry envelope, payload registry, and emitter.

See docs/engineering/TELEMETRY.md. The emitter must never raise, never
write outside the project, and never commit the local mirror to git.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from latris.operations.init import init_project
from latris.repo import git
from latris.repo.project import require_project
from latris.schema.events import (
    EVENT_PAYLOADS,
    AICallCompletedPayload,
    TelemetryEvent,
    register_event_type,
    validate_payload,
)
from latris.telemetry import config as telemetry_config
from latris.telemetry import emitter as emitter_module


@pytest.fixture
def project(tmp_path: Path, git_identity):
    root = tmp_path / "demo"
    init_project(root, statement="Q?")
    return root


def _emit_ai_call(root: Path, **kwargs):
    return emitter_module.emit(
        "ai.call.completed",
        {
            "interaction_id": "interaction_01J0000000000000000000",
            "prompt_name": "ExplainThisElement",
            "model_id": "claude-opus-4-6",
            "adoption": "approved",
        },
        surface="server",
        root=root,
        **kwargs,
    )


# ---------- envelope + registry ----------


def test_envelope_defaults() -> None:
    event = TelemetryEvent(surface="server", event_type="ai.call.completed")
    assert event.id.startswith("telemetry-event_")
    assert event.at is not None
    assert event.type_version == 1
    assert event.actor_ref is None
    assert event.payload == {}


def test_builtin_registry_has_all_v1_types() -> None:
    expected = {
        "ai.call.completed",
        "ai.proposal.outcome",
        "gui.feature",
        "mcp.tool",
        "session.lifecycle",
        "project.lifecycle",
        "error.observed",
        "cli.command",
    }
    assert {name for name, _v in EVENT_PAYLOADS} == expected


def test_validate_payload_round_trip() -> None:
    model = validate_payload(
        "ai.call.completed",
        1,
        {
            "interaction_id": "interaction_x",
            "prompt_name": "ScopeCheck",
            "model_id": "m",
            "adoption": "rejected",
            "rejection_reason": "wrong-scope",
        },
    )
    assert isinstance(model, AICallCompletedPayload)
    assert model.rejection_reason == "wrong-scope"


def test_payload_models_reject_extra_fields() -> None:
    with pytest.raises(ValidationError):
        validate_payload(
            "ai.call.completed",
            1,
            {
                "interaction_id": "i",
                "prompt_name": "p",
                "model_id": "m",
                "adoption": "approved",
                "prompt_text": "must not be accepted",  # extra field
            },
        )


def test_validate_payload_unknown_type_raises() -> None:
    with pytest.raises(KeyError):
        validate_payload("no.such.event", 1, {})


def test_register_event_type_conflict_raises() -> None:
    class Other(AICallCompletedPayload):
        pass

    with pytest.raises(ValueError, match="already registered"):
        register_event_type("ai.call.completed", Other)
    # Re-registering the same model is a no-op.
    register_event_type("ai.call.completed", AICallCompletedPayload)


# ---------- emitter ----------


def _read_events(root: Path) -> list[dict]:
    path = require_project(root).telemetry_jsonl
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_emit_writes_local_jsonl(project: Path) -> None:
    event = _emit_ai_call(project)
    assert event is not None
    rows = _read_events(project)
    assert len(rows) == 1
    assert rows[0]["id"] == event.id
    assert rows[0]["event_type"] == "ai.call.completed"
    assert rows[0]["surface"] == "server"
    assert rows[0]["payload"]["prompt_name"] == "ExplainThisElement"


def test_emit_disabled_writes_nothing(project: Path) -> None:
    paths = require_project(project)
    telemetry_config.save(paths, telemetry_config.TelemetryConfig(enabled=False))
    assert _emit_ai_call(project) is None
    assert _read_events(project) == []


def test_emit_invalid_payload_dropped(project: Path) -> None:
    event = emitter_module.emit(
        "ai.call.completed",
        {"adoption": "approved"},  # missing required fields
        surface="server",
        root=project,
    )
    assert event is None
    assert _read_events(project) == []


def test_emit_outside_project_dropped(tmp_path: Path) -> None:
    event = emitter_module.emit(
        "ai.call.completed",
        {
            "interaction_id": "i",
            "prompt_name": "p",
            "model_id": "m",
            "adoption": "approved",
        },
        surface="cli",
        root=tmp_path,  # never initialised
    )
    assert event is None


def test_local_mirror_is_never_committed(project: Path) -> None:
    assert _emit_ai_call(project) is not None
    status = git.run_git(["status", "--porcelain"], cwd=project).stdout
    assert "telemetry.jsonl" not in status


def test_upload_only_when_opted_in(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, TelemetryEvent]] = []
    monkeypatch.setattr(
        emitter_module, "_upload", lambda url, event: calls.append((url, event))
    )

    # Default config: upload_enabled=False → no upload.
    assert _emit_ai_call(project) is not None
    assert calls == []

    paths = require_project(project)
    telemetry_config.save(
        paths,
        telemetry_config.TelemetryConfig(
            enabled=True, upload_enabled=True, endpoint_url="https://telemetry.example/ingest"
        ),
    )
    assert _emit_ai_call(project) is not None
    assert len(calls) == 1
    assert calls[0][0] == "https://telemetry.example/ingest"


def test_upload_failure_keeps_local_event(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(url, event):
        raise RuntimeError("endpoint down")

    monkeypatch.setattr(emitter_module, "_upload", _boom)
    paths = require_project(project)
    telemetry_config.save(
        paths,
        telemetry_config.TelemetryConfig(
            enabled=True, upload_enabled=True, endpoint_url="https://telemetry.example/ingest"
        ),
    )
    event = _emit_ai_call(project)
    assert event is not None  # local mirror is primary
    assert len(_read_events(project)) == 1
