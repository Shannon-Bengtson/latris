"""Tests for the GUI telemetry relay (POST /api/telemetry/events).

See docs/engineering/TELEMETRY.md. The relay stamps the surface,
validates atomically against the registry, and persists best-effort through
the emitter — the local JSONL mirror is primary, upload is opt-in.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.operations.init import init_project
from latris.repo.project import require_project
from latris.server.app import create_app
from latris.telemetry import config as telemetry_config
from latris.telemetry import emitter as emitter_module

PATH = "/api/telemetry/events"


@pytest.fixture
def project(tmp_path: Path, git_identity) -> Path:
    root = tmp_path / "demo"
    init_project(root, statement="Test Q?")
    return root


@pytest.fixture
def client(project: Path) -> TestClient:
    app = create_app(project_root=project)
    return TestClient(app)


def _event(**overrides: object) -> dict:
    event = {
        "id": "telemetry-event_01J0000000000000000001",
        "at": "2026-11-25T10:00:00Z",
        "surface": "gui",
        "event_type": "gui.feature",
        "type_version": 1,
        "actor_ref": None,
        "project_id": None,
        "session_id": "session_01J0000000000000000002",
        "payload": {"feature": "report", "action": "opened"},
    }
    return event | overrides


def _read_events(root: Path) -> list[dict]:
    path = require_project(root).telemetry_jsonl
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_post_events_writes_local_mirror(client: TestClient, project: Path) -> None:
    resp = client.post(PATH, json={"events": [_event(), _event(id="telemetry-event_01J0000000000000000003")]})
    assert resp.status_code == 200
    assert resp.json() == {"accepted": 2}
    rows = _read_events(project)
    assert [row["id"] for row in rows] == [
        "telemetry-event_01J0000000000000000001",
        "telemetry-event_01J0000000000000000003",
    ]
    assert rows[0]["surface"] == "gui"
    assert rows[0]["session_id"] == "session_01J0000000000000000002"
    assert rows[0]["at"].startswith("2026-11-25T10:00:00")  # client clock kept
    assert rows[0]["payload"] == {"feature": "report", "action": "opened"}


def test_surface_is_stamped_not_chosen(client: TestClient, project: Path) -> None:
    resp = client.post(PATH, json={"events": [_event(surface="mcp")]})
    assert resp.status_code == 200
    assert _read_events(project)[0]["surface"] == "gui"


def test_unknown_event_type_422(client: TestClient, project: Path) -> None:
    resp = client.post(PATH, json={"events": [_event(event_type="no.such.event")]})
    assert resp.status_code == 422
    assert "no.such.event" in str(resp.json()["detail"])
    assert _read_events(project) == []


def test_invalid_payload_fails_whole_batch(client: TestClient, project: Path) -> None:
    bad = _event(id="telemetry-event_01J0000000000000000004", payload={"feature": "report"})  # no action
    resp = client.post(PATH, json={"events": [_event(), bad]})
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail[0]["index"] == 1
    assert _read_events(project) == []  # atomic: the valid one is not persisted either


def test_envelope_extra_field_rejected(client: TestClient, project: Path) -> None:
    resp = client.post(PATH, json={"events": [_event(prompt_text="must not be accepted")]})
    assert resp.status_code == 422
    assert _read_events(project) == []


def test_batch_over_cap_rejected(client: TestClient) -> None:
    resp = client.post(PATH, json={"events": [_event() for _ in range(501)]})
    assert resp.status_code == 422


def test_empty_batch_accepted(client: TestClient) -> None:
    resp = client.post(PATH, json={"events": []})
    assert resp.status_code == 200
    assert resp.json() == {"accepted": 0}


def test_disabled_config_accepts_nothing(client: TestClient, project: Path) -> None:
    paths = require_project(project)
    telemetry_config.save(paths, telemetry_config.TelemetryConfig(enabled=False))
    resp = client.post(PATH, json={"events": [_event()]})
    assert resp.status_code == 200
    assert resp.json() == {"accepted": 0}
    assert _read_events(project) == []


def test_upload_forwards_whole_batch(client: TestClient, project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, list]] = []
    monkeypatch.setattr(
        emitter_module, "_upload_batch", lambda url, events: calls.append((url, events))
    )
    paths = require_project(project)
    telemetry_config.save(
        paths,
        telemetry_config.TelemetryConfig(
            enabled=True, upload_enabled=True, endpoint_url="https://telemetry.example/v1/events"
        ),
    )
    resp = client.post(PATH, json={"events": [_event(), _event(id="telemetry-event_01J0000000000000000005")]})
    assert resp.status_code == 200
    assert len(calls) == 1
    url, events = calls[0]
    assert url == "https://telemetry.example/v1/events"
    assert [event.id for event in events] == [
        "telemetry-event_01J0000000000000000001",
        "telemetry-event_01J0000000000000000005",
    ]
    assert all(event.surface == "gui" for event in events)


def test_upload_failure_keeps_local_events(
    client: TestClient, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(url: str, events: list) -> None:
        raise RuntimeError("endpoint down")

    monkeypatch.setattr(emitter_module, "_upload_batch", _boom)
    paths = require_project(project)
    telemetry_config.save(
        paths,
        telemetry_config.TelemetryConfig(
            enabled=True, upload_enabled=True, endpoint_url="https://telemetry.example/v1/events"
        ),
    )
    resp = client.post(PATH, json={"events": [_event()]})
    assert resp.status_code == 200
    assert len(_read_events(project)) == 1
