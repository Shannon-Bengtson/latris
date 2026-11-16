"""Server trust boundary: CORS, access token, error bodies."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from latris.server.access import warn_if_exposed
from latris.server.app import create_app

TOKEN = "s3cret-token"


@pytest.fixture
def project(empty_project_root: Path) -> Path:
    return empty_project_root


# ── CORS ─────────────────────────────────────────────────────────────


def test_null_origin_is_not_allowed(project: Path) -> None:
    client = TestClient(create_app(project_root=project))
    resp = client.get("/api/health", headers={"Origin": "null"})
    assert resp.headers.get("access-control-allow-origin") is None


def test_vite_dev_origin_still_allowed(project: Path) -> None:
    client = TestClient(create_app(project_root=project))
    resp = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"


# ── Access token ─────────────────────────────────────────────────────


def test_no_token_configured_means_open(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LATRIS_SERVER_TOKEN", raising=False)
    client = TestClient(create_app(project_root=project))
    assert client.get("/api/state").status_code == 200


@pytest.fixture
def gated(project: Path) -> TestClient:
    return TestClient(create_app(project_root=project, access_token=TOKEN))


def test_token_required_for_api(gated: TestClient) -> None:
    assert gated.get("/api/state").status_code == 401
    assert gated.get("/api/state", headers={"X-Latris-Token": "wrong"}).status_code == 401
    assert gated.get("/api/state", headers={"X-Latris-Token": TOKEN}).status_code == 200
    assert gated.get("/api/state", headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 200


def test_health_and_preflight_stay_open(gated: TestClient) -> None:
    assert gated.get("/api/health").status_code == 200
    resp = gated.options(
        "/api/state",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert resp.status_code == 200


def test_token_from_env(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LATRIS_SERVER_TOKEN", TOKEN)
    client = TestClient(create_app(project_root=project))
    assert client.get("/api/state").status_code == 401
    assert client.get("/api/state", headers={"X-Latris-Token": TOKEN}).status_code == 200


def test_websocket_requires_token(gated: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect), gated.websocket_connect("/ws") as ws:
        ws.receive_text()
    with gated.websocket_connect("/ws", headers={"X-Latris-Token": TOKEN}):
        pass


def test_warn_if_exposed(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.delenv("LATRIS_SERVER_TOKEN", raising=False)
    warn_if_exposed("127.0.0.1")
    assert capsys.readouterr().err == ""
    warn_if_exposed("0.0.0.0")
    assert "no access token" in capsys.readouterr().err
    monkeypatch.setenv("LATRIS_SERVER_TOKEN", TOKEN)
    warn_if_exposed("0.0.0.0")
    assert capsys.readouterr().err == ""


# ── Error bodies ─────────────────────────────────────────────────────


def test_unhandled_error_has_no_traceback(project: Path) -> None:
    app = create_app(project_root=project)
    router = APIRouter()

    class BoomError(Exception):
        pass

    @router.get("/api/_boom")
    def boom() -> None:
        raise BoomError("secret-detail")

    app.include_router(router)
    resp = TestClient(app, raise_server_exceptions=False).get("/api/_boom")
    assert resp.status_code == 500
    body = resp.json()
    assert "Traceback" not in body["detail"]
    assert "File \"" not in body["detail"]
    assert body["error_id"]
