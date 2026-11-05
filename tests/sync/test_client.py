from __future__ import annotations

import httpx
import pytest

from latris.sync.client import SyncClient, SyncClientError


def _client(handler, token=None) -> SyncClient:
    transport = httpx.MockTransport(handler)
    hc = httpx.Client(base_url="https://sync.test", transport=transport)
    return SyncClient("https://sync.test", token, client=hc)


def test_verify_code_posts_and_parses() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/auth/verify-code"
        return httpx.Response(
            200,
            json={
                "account": {"id": "acct_1", "email": "a@x.io", "display_name": "A"},
                "session_token": "s",
                "gitea": {"token": "t", "username": "u", "base_url": "b"},
            },
        )

    data = _client(handler).verify_code("a@x.io", "123456", "dev")
    assert data["session_token"] == "s"
    assert data["gitea"]["username"] == "u"


def test_error_detail_is_surfaced() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"detail": "bad code"})

    with pytest.raises(SyncClientError, match="bad code"):
        _client(handler).verify_code("a@x.io", "000000")


def test_bearer_header_sent_when_token_present() -> None:
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"projects": []})

    _client(handler, token="sess").me()
    assert seen["auth"] == "Bearer sess"


def test_network_error_wrapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    with pytest.raises(SyncClientError):
        _client(handler).me()


def test_create_project_and_members_paths() -> None:
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        return httpx.Response(200, json={"id": "proj_1"})

    c = _client(handler, token="sess")
    c.create_project("Coastal")
    c.add_member("proj_1", "bob@x.io", "collaborator")
    c.update_member("proj_1", "acct_2", "reviewer")
    c.remove_member("proj_1", "acct_2")
    assert ("POST", "/api/projects") in calls
    assert ("POST", "/api/projects/proj_1/members") in calls
    assert ("PATCH", "/api/projects/proj_1/members/acct_2") in calls
    assert ("DELETE", "/api/projects/proj_1/members/acct_2") in calls


def test_report_sharing_and_save_paths() -> None:
    calls: list[tuple[str, str, bytes]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path, request.content))
        return httpx.Response(200, json={"report_url": "https://app.test/r/x", "report_pack": "client"})

    c = _client(handler, token="sess")
    assert c.set_report_sharing("proj_1", True, "review")["report_url"] == "https://app.test/r/x"
    c.save_project("tok")
    assert calls[0][:2] == ("PATCH", "/api/projects/proj_1/report")
    assert b'"pack":"review"' in calls[0][2].replace(b" ", b"")
    assert calls[1][:2] == ("POST", "/api/projects/save")
