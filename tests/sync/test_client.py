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


def test_error_without_a_json_body_names_the_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="<html>Bad gateway</html>")

    with pytest.raises(SyncClientError, match="HTTP 502") as exc:
        _client(handler, token="sess").refresh()
    assert exc.value.status_code == 502


def test_non_string_detail_falls_back_to_the_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"detail": [{"loc": ["body"], "msg": "bad"}]})

    with pytest.raises(SyncClientError, match="HTTP 422"):
        _client(handler, token="sess").regenerate_gitea_token()


def test_network_error_has_no_status_code() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out")

    with pytest.raises(SyncClientError) as exc:
        _client(handler).validate()
    assert exc.value.status_code is None


def test_empty_success_body_is_an_empty_dict() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(204)

    assert _client(handler, token="sess").logout() == {}
    assert seen == ["/api/auth/logout"]


def test_owned_client_uses_the_server_url_and_closes() -> None:
    c = SyncClient("https://sync.test/", "sess", timeout=3.0)
    assert str(c._client.base_url) == "https://sync.test"
    assert c._client.timeout.connect == 3.0
    c.close()
    assert c._client.is_closed


def test_injected_client_is_not_closed() -> None:
    hc = httpx.Client(base_url="https://sync.test", transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    SyncClient("https://sync.test", client=hc).close()
    assert not hc.is_closed
