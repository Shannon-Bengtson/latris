"""Account-first: the backend runs in 'no-project' mode at launch so the auth
routes are available before any project is open."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from latris.server.app import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(project_root=None))


def test_health_works_without_project(client: TestClient) -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["project_root"] is None


def test_account_route_works_without_project(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from latris.operations import sync as ops

    monkeypatch.setattr(ops, "current_account", lambda: {"id": "acct_1", "email": "a@x.io", "display_name": "A"})
    resp = client.get("/api/sync/account")
    assert resp.status_code == 200
    assert resp.json()["account"]["email"] == "a@x.io"


def test_login_request_reachable_without_project(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from latris.operations import sync as ops

    monkeypatch.setattr(ops, "login_request_code", lambda server_url, email, intent="auto": None)
    resp = client.post("/api/sync/login/request", json={"server_url": "http://x", "email": "a@x.io"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_project_bound_route_404s_without_project(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # No project bound and discovery finds none → project routes are unavailable.
    monkeypatch.setattr("latris.server.deps.find_project_root", lambda: None)
    resp = client.get("/api/sync/status")
    assert resp.status_code == 404
