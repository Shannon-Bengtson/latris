"""Tests for post-hoc URL validation of AI-proposed references.

Network is never touched: DNS is faked and HTTP goes to an ``httpx.MockTransport``
for ``check_url`` unit tests, and ``check_url`` itself is patched for the parallel
``validate_reference_urls`` orchestration tests.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest

from latris.ai.validate_urls import check_url, validate_reference_urls

_DNS = {"metadata.example": "169.254.169.254", "intranet.example": "10.0.0.7"}
_REAL_CLIENT = httpx.Client


@pytest.fixture(autouse=True)
def _public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hermetic DNS: every host resolves to a public address but the two private ones above (the SSRF
    guard resolves before fetching). Guard behaviour is in test_net_guard."""
    monkeypatch.setattr(
        "latris._net_guard.socket.getaddrinfo",
        lambda host, port, **_: [(2, 1, 6, "", (_DNS.get(host, "93.184.216.34"), port))],
    )
    monkeypatch.delenv("LATRIS_ALLOW_PRIVATE_FETCH", raising=False)


def _serve(monkeypatch: pytest.MonkeyPatch, *answers) -> list[httpx.Request]:  # noqa: ANN002
    """Answer requests in turn: a status, a (status, headers) pair, or an exception to raise.
    Returns the requests made."""
    seen: list[httpx.Request] = []
    queue = list(answers)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        answer = queue.pop(0)
        if isinstance(answer, Exception):
            raise answer
        status, headers = answer if isinstance(answer, tuple) else (answer, {})
        return httpx.Response(status, headers=headers)

    monkeypatch.setattr(httpx, "Client", lambda **kw: _REAL_CLIENT(transport=httpx.MockTransport(handler), **kw))
    return seen


# ── check_url ────────────────────────────────────────────────────────


def test_check_url_blocks_non_http_and_private(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _serve(monkeypatch)
    assert check_url("file:///etc/passwd") is False
    assert check_url("http://metadata.example/latest/meta-data") is False
    assert seen == []  # refused before any request


def test_check_url_refuses_a_redirect_to_a_private_address(monkeypatch: pytest.MonkeyPatch) -> None:
    """A public URL that redirects inward is refused at the redirect, and the inner address never asked."""
    seen = _serve(monkeypatch, (302, {"location": "http://metadata.example/latest/meta-data"}))
    assert check_url("http://public.example/paper") is False
    assert [str(r.url) for r in seen] == ["http://public.example/paper"]

    seen = _serve(monkeypatch, (301, {"location": "/moved"}), (307, {"location": "http://intranet.example/"}))
    assert check_url("http://public.example/paper") is False
    assert [r.url.host for r in seen] == ["public.example", "public.example"]


def test_check_url_follows_public_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _serve(monkeypatch, (301, {"location": "https://doi.example/landing"}), 200)
    assert check_url("https://doi.org/10.1/abc") is True
    assert [str(r.url) for r in seen] == ["https://doi.org/10.1/abc", "https://doi.example/landing"]
    assert all(r.method == "HEAD" and r.headers["user-agent"].endswith("(Latris reference checker)") for r in seen)


def test_check_url_too_many_redirects_is_false(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch, *[(302, {"location": "/again"})] * 10)
    assert check_url("http://public.example/loop") is False


def test_check_url_head_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch, 200)
    assert check_url("http://example.com") is True


def test_check_url_head_error_status_is_false(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch, 404)
    assert check_url("http://example.com") is False


def test_check_url_405_retries_with_get_and_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    # HEAD blocked (405) → GET-with-range succeeds.
    seen = _serve(monkeypatch, 405, 206)
    assert check_url("http://example.com") is True
    assert [r.method for r in seen] == ["HEAD", "GET"] and seen[1].headers["range"] == "bytes=0-0"


def test_check_url_403_retries_with_get_and_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch, 403, 200)
    assert check_url("http://example.com") is True


def test_check_url_403_then_get_fails_treats_as_existing(monkeypatch: pytest.MonkeyPatch) -> None:
    # 403 often means access control, not a missing page → treat as valid.
    _serve(monkeypatch, 403, httpx.ConnectError("blocked"))
    assert check_url("http://example.com") is True
    _serve(monkeypatch, 403, 403)
    assert check_url("http://example.com") is True


def test_check_url_405_then_get_fails_is_false(monkeypatch: pytest.MonkeyPatch) -> None:
    # 405 with a failing GET retry is not a 403, so it is rejected.
    _serve(monkeypatch, 405, httpx.ConnectError("nope"))
    assert check_url("http://example.com") is False
    _serve(monkeypatch, 405, 404)
    assert check_url("http://example.com") is False


def test_check_url_other_http_error_is_false(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _serve(monkeypatch, 500)
    assert check_url("http://example.com") is False
    assert len(seen) == 1  # no retry


def test_check_url_network_error_is_false(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch, httpx.ConnectError("dns"))
    assert check_url("http://nonexistent.invalid") is False
    _serve(monkeypatch, httpx.ReadTimeout("slow"))
    assert check_url("http://example.com") is False


def test_check_url_malformed_is_false(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _serve(monkeypatch)
    assert check_url("not-a-url") is False
    assert check_url("http://example.com:notaport/") is False
    assert seen == []


# ── validate_reference_urls ──────────────────────────────────────────


def test_validate_reference_urls_empty_list() -> None:
    assert validate_reference_urls([]) == []


def test_validate_reference_urls_no_urls_marks_all_invalid() -> None:
    refs = [SimpleNamespace(url=None, doi=None), SimpleNamespace(url="", doi="")]
    results = validate_reference_urls(refs)
    assert results == [
        {"index": 0, "url": None, "valid": False},
        {"index": 1, "url": None, "valid": False},
    ]


def test_validate_reference_urls_uses_doi_fallback() -> None:
    refs = [SimpleNamespace(url=None, doi="10.1/abc")]
    with patch("latris.ai.validate_urls.check_url", return_value=True) as m:
        results = validate_reference_urls(refs)
    m.assert_called_once_with("https://doi.org/10.1/abc")
    assert results == [{"index": 0, "url": "https://doi.org/10.1/abc", "valid": True}]


def test_validate_reference_urls_checks_urls_and_preserves_order() -> None:
    refs = [
        SimpleNamespace(url="http://a.com", doi=None),  # valid
        SimpleNamespace(url=None, doi=None),  # no url → invalid, not checked
        SimpleNamespace(url="http://c.com", doi=None),  # invalid
    ]

    def fake_check(url: str) -> bool:
        return url == "http://a.com"

    with patch("latris.ai.validate_urls.check_url", side_effect=fake_check):
        results = validate_reference_urls(refs)

    # Sorted back into original reference order regardless of completion order.
    assert [r["index"] for r in results] == [0, 1, 2]
    assert results[0] == {"index": 0, "url": "http://a.com", "valid": True}
    assert results[1] == {"index": 1, "url": None, "valid": False}
    assert results[2] == {"index": 2, "url": "http://c.com", "valid": False}


def test_validate_reference_urls_swallows_checker_exceptions() -> None:
    refs = [SimpleNamespace(url="http://boom.com", doi=None)]
    with patch("latris.ai.validate_urls.check_url", side_effect=RuntimeError("worker died")):
        results = validate_reference_urls(refs)
    assert results == [{"index": 0, "url": "http://boom.com", "valid": False}]
