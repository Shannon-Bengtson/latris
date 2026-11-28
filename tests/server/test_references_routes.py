"""Server route tests for /api/references/{bibkey}/fetch: fetching a source's full text (no network)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from latris import _net_guard
from latris.operations import references as ref_ops
from latris.repo import git
from latris.repo.project import require_project
from latris.server.app import create_app
from tests.operations.test_fetch_reference import FakeResponse


@pytest.fixture
def project(empty_project_root: Path) -> Path:
    ref_ops.add_reference("smith2023", title="Emissions", url="https://example.org/p", root=empty_project_root)
    return empty_project_root


@pytest.fixture
def client(project: Path) -> TestClient:
    return TestClient(create_app(project_root=project))


def _fetcher(monkeypatch: pytest.MonkeyPatch, respond) -> list[str]:
    asked: list[str] = []

    def fake_get(url: str, **_kw):
        asked.append(url)
        return respond(url)

    monkeypatch.setattr(_net_guard, "safe_get", fake_get)
    return asked


def test_fetch(client: TestClient, project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    asked = _fetcher(monkeypatch, lambda url: FakeResponse("<p>Vehicle emissions drive decline.</p>", url=url))
    r = client.post("/api/references/smith2023/fetch", json={})
    assert r.status_code == 200, r.text
    snap = r.json()["result"]["source_snapshot"]
    assert asked == ["https://example.org/p"]  # the reference's own URL
    assert snap["kind"] == "full_text_excerpt" and "Vehicle emissions drive decline." in snap["extract"]
    assert r.json()["commit_sha"] == git.head_sha(project)
    assert ref_ops.get_reference("smith2023", root=project).source_snapshot.content_hash == snap["content_hash"]
    artefact = require_project(project).references_extract_path("smith2023")
    assert "Vehicle emissions" in artefact.read_text(encoding="utf-8")

    # A URL in the body overrides the reference's.
    r = client.post("/api/references/smith2023/fetch", json={"url": "https://example.org/other"})
    assert r.status_code == 200 and asked[-1] == "https://example.org/other"
    assert r.json()["result"]["source_snapshot"]["retrieval_url"] == "https://example.org/other"


def _status_error(url: str):
    request = httpx.Request("GET", url)
    raise httpx.HTTPStatusError("not found", request=request, response=httpx.Response(404, request=request))


def _connect_error(url: str):
    raise httpx.ConnectError("connection refused", request=httpx.Request("GET", url))


def _timeout(url: str):
    raise httpx.ReadTimeout("slow", request=httpx.Request("GET", url))


@pytest.mark.parametrize(("respond", "detail"), [
    # An unreachable or failing source is the request's to report, never a 500.
    (_status_error, "answered with an error (404)"),
    (_connect_error, "could not reach"),
    (_timeout, "timed out"),
    (lambda url: FakeResponse("", url=url), "extracted empty text"),
])
def test_fetch_failures(client: TestClient, project: Path, monkeypatch: pytest.MonkeyPatch, respond,
                        detail: str) -> None:
    _fetcher(monkeypatch, respond)
    head = git.head_sha(project)
    r = client.post("/api/references/smith2023/fetch", json={})
    assert r.status_code == 422 and detail in r.json()["detail"]
    assert git.head_sha(project) == head
    assert ref_ops.get_reference("smith2023", root=project).source_snapshot is None


def test_fetch_bad_requests(client: TestClient, project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    asked = _fetcher(monkeypatch, lambda url: FakeResponse("text", url=url))
    r = client.post("/api/references/smith2023/fetch", json={"url": "file:///etc/passwd"})
    assert r.status_code == 422 and "only http(s)" in r.json()["detail"]
    missing = client.post("/api/references/nope2020/fetch", json={})
    assert missing.status_code == 422 and "no reference matching" in missing.json()["detail"]
    assert client.post("/api/references/smith2023/fetch").status_code == 422  # a body is required
    assert asked == []
