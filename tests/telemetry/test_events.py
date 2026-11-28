"""Tests for the telemetry envelope, payload registry, and emitter.

See docs/engineering/TELEMETRY.md. The emitter must never raise, never
write outside the project, and never commit the local mirror to git.
"""

from __future__ import annotations

import json
from datetime import datetime
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
        "checkpoint.outcome",
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
    monkeypatch.setattr(emitter_module, "_upload", lambda url, event: calls.append((url, event)))

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


# ---------- emit_envelopes (the server relay path) ----------


def _envelope(**overrides) -> TelemetryEvent:
    fields = {
        "surface": "gui",
        "event_type": "gui.feature",
        "session_id": "session_01J0000000000000000002",
        "payload": {"feature": "report", "action": "opened"},
    }
    return TelemetryEvent(**(fields | overrides))


def test_emit_envelopes_preserves_client_fields(project: Path) -> None:
    event = _envelope()
    assert emitter_module.emit_envelopes([event], root=project) == 1
    rows = _read_events(project)
    assert len(rows) == 1
    assert rows[0]["id"] == event.id
    assert datetime.fromisoformat(rows[0]["at"]) == event.at  # client clock kept
    assert rows[0]["session_id"] == "session_01J0000000000000000002"


def test_emit_envelopes_disabled_accepts_nothing(project: Path) -> None:
    paths = require_project(project)
    telemetry_config.save(paths, telemetry_config.TelemetryConfig(enabled=False))
    assert emitter_module.emit_envelopes([_envelope()], root=project) == 0
    assert _read_events(project) == []


def test_emit_envelopes_drops_invalid_payloads(project: Path) -> None:
    good = _envelope()
    bad = _envelope(payload={"feature": "report"})  # missing action
    assert emitter_module.emit_envelopes([bad, good], root=project) == 1
    rows = _read_events(project)
    assert [row["id"] for row in rows] == [good.id]


def test_emit_envelopes_outside_project_dropped(tmp_path: Path) -> None:
    assert emitter_module.emit_envelopes([_envelope()], root=tmp_path) == 0


def test_emit_envelopes_uploads_batch_once(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, list]] = []
    monkeypatch.setattr(emitter_module, "_upload_batch", lambda url, events: calls.append((url, events)))
    paths = require_project(project)
    telemetry_config.save(
        paths,
        telemetry_config.TelemetryConfig(
            enabled=True, upload_enabled=True, endpoint_url="https://telemetry.example/v1/events"
        ),
    )
    accepted = emitter_module.emit_envelopes([_envelope(), _envelope()], root=project)
    assert accepted == 2
    assert len(calls) == 1
    assert len(calls[0][1]) == 2


# ---------- upload transport ----------


class _FakeResponse:
    status = 202

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _capture_urlopen(monkeypatch: pytest.MonkeyPatch) -> list:
    sent: list = []
    monkeypatch.setattr(
        emitter_module.urllib.request, "urlopen", lambda req, timeout: sent.append(req) or _FakeResponse()
    )
    return sent


def test_post_events_sends_bearer_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = _capture_urlopen(monkeypatch)
    monkeypatch.setenv(emitter_module.TOKEN_ENV_VAR, "secret-token")
    event = _envelope()
    emitter_module._post_events("https://telemetry.example/v1/events", [event])
    req = sent[0]
    assert req.get_header("Authorization") == "Bearer secret-token"
    body = json.loads(req.data.decode("utf-8"))
    assert [row["id"] for row in body["events"]] == [event.id]
    assert body["events"][0]["surface"] == "gui"


def test_post_events_without_token_sends_no_header(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = _capture_urlopen(monkeypatch)
    monkeypatch.delenv(emitter_module.TOKEN_ENV_VAR, raising=False)
    emitter_module._post_events("https://telemetry.example/v1/events", [_envelope()])
    assert sent[0].get_header("Authorization") is None


@pytest.mark.parametrize(
    "url",
    [
        "https://telemetry.example/v1/events",
        "HTTPS://telemetry.example/v1/events",
        "http://localhost:8080/ingest",
        "http://127.0.0.1/ingest",
        "http://[::1]:9000/ingest",
    ],
)
def test_post_events_allows_https_and_local_http(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    sent = _capture_urlopen(monkeypatch)
    emitter_module._post_events(url, [_envelope()])
    assert len(sent) == 1


@pytest.mark.parametrize(
    "url",
    [
        "http://telemetry.example/v1/events",  # cleartext to a remote host
        "http://localhost.telemetry.example/ingest",
        "http://localhost@telemetry.example/ingest",  # userinfo, not the host
        "http://127.0.0.2/ingest",
        "file:///etc/passwd",
        "ftp://telemetry.example/events",
        "data:text/plain,hello",
        "gopher://telemetry.example/",
        "https:///no-host",
        "telemetry.example/v1/events",  # no scheme
        "",
    ],
)
def test_post_events_refuses_other_schemes_and_hosts(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    sent = _capture_urlopen(monkeypatch)
    with pytest.raises(ValueError, match="telemetry endpoint refused"):
        emitter_module._post_events(url, [_envelope()])
    assert sent == []  # refused before anything is opened


def test_refused_endpoint_drops_the_upload_but_keeps_the_event(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sent = _capture_urlopen(monkeypatch)
    monkeypatch.setenv(emitter_module.ENDPOINT_ENV_VAR, "file:///tmp/events")
    event = _emit_ai_call(project)
    assert event is not None  # best-effort: the local mirror still has it
    assert len(_read_events(project)) == 1
    assert emitter_module.emit_envelopes([_envelope()], root=project) == 1
    assert sent == []


# ---------- hosted containers: configured by environment ----------


def test_hosted_env_turns_upload_on_with_actor(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """In a hosted session container the broker sets the endpoint, token and actor."""
    sent = _capture_urlopen(monkeypatch)
    monkeypatch.setenv(emitter_module.ENDPOINT_ENV_VAR, "https://telemetry.example/v1/events")
    monkeypatch.setenv(emitter_module.TOKEN_ENV_VAR, "ingest-token")
    monkeypatch.setenv(emitter_module.ACTOR_ENV_VAR, "actor_abc")

    event = _emit_ai_call(project)  # default telemetry.yaml: upload_enabled=False
    assert event is not None and event.actor_ref == "actor_abc"
    [req] = sent
    assert req.full_url == "https://telemetry.example/v1/events"
    assert req.get_header("Authorization") == "Bearer ingest-token"
    assert json.loads(req.data)["events"][0]["actor_ref"] == "actor_abc"

    # The project can still switch telemetry off entirely.
    paths = require_project(project)
    telemetry_config.save(paths, telemetry_config.TelemetryConfig(enabled=False))
    assert _emit_ai_call(project) is None
    assert len(sent) == 1


def test_hosted_env_relays_envelopes_with_actor(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sent = _capture_urlopen(monkeypatch)
    monkeypatch.setenv(emitter_module.ENDPOINT_ENV_VAR, "https://telemetry.example/v1/events")
    monkeypatch.setenv(emitter_module.ACTOR_ENV_VAR, "actor_abc")

    assert emitter_module.emit_envelopes([_envelope(), _envelope()], root=project) == 2
    [req] = sent
    assert [row["actor_ref"] for row in json.loads(req.data)["events"]] == ["actor_abc", "actor_abc"]


def test_no_hosted_env_no_upload(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An end user's own install sets none of the variables: nothing leaves the machine."""
    sent = _capture_urlopen(monkeypatch)
    for var in (emitter_module.ENDPOINT_ENV_VAR, emitter_module.ACTOR_ENV_VAR, emitter_module.TOKEN_ENV_VAR):
        monkeypatch.delenv(var, raising=False)
    event = _emit_ai_call(project)
    assert event is not None and event.actor_ref is None
    assert sent == []


def test_checkpoint_outcome_carries_the_checkpoint_and_outcome_only() -> None:
    model = validate_payload("checkpoint.outcome", 1, {"checkpoint": "values", "outcome": "skipped"})
    assert (model.checkpoint, model.outcome) == ("values", "skipped")
    assert validate_payload("checkpoint.outcome", 1, {"checkpoint": "all", "outcome": "paced"}).checkpoint == "all"
    for bad in (
        {"checkpoint": "made-up", "outcome": "answered"},
        {"checkpoint": "framing", "outcome": "ignored"},
        {"checkpoint": "framing", "outcome": "answered", "answers": "must not be accepted"},
    ):
        with pytest.raises(ValidationError):
            validate_payload("checkpoint.outcome", 1, bad)
