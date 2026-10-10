"""Tests for post-hoc URL validation of AI-proposed references.

Network is never touched: ``urlopen`` is patched for ``check_url`` unit
tests, and ``check_url`` itself is patched for the parallel
``validate_reference_urls`` orchestration tests.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from latris.ai.validate_urls import check_url, validate_reference_urls


def _http_error(code: int) -> HTTPError:
    return HTTPError("http://example.com", code, f"status {code}", {}, None)  # type: ignore[arg-type]


def _resp(status: int) -> MagicMock:
    return MagicMock(status=status)


# ── check_url ────────────────────────────────────────────────────────


def test_check_url_head_success() -> None:
    with patch("latris.ai.validate_urls.urlopen", return_value=_resp(200)):
        assert check_url("http://example.com") is True


def test_check_url_head_error_status_is_false() -> None:
    # A response object reporting a 4xx status (no exception) is rejected.
    with patch("latris.ai.validate_urls.urlopen", return_value=_resp(404)):
        assert check_url("http://example.com") is False


def test_check_url_405_retries_with_get_and_succeeds() -> None:
    # HEAD blocked (405) → GET-with-range succeeds.
    with patch(
        "latris.ai.validate_urls.urlopen",
        side_effect=[_http_error(405), _resp(206)],
    ):
        assert check_url("http://example.com") is True


def test_check_url_403_retries_with_get_and_succeeds() -> None:
    with patch(
        "latris.ai.validate_urls.urlopen",
        side_effect=[_http_error(403), _resp(200)],
    ):
        assert check_url("http://example.com") is True


def test_check_url_403_then_get_fails_treats_as_existing() -> None:
    # 403 often means access control, not a missing page → treat as valid.
    with patch(
        "latris.ai.validate_urls.urlopen",
        side_effect=[_http_error(403), URLError("blocked")],
    ):
        assert check_url("http://example.com") is True


def test_check_url_405_then_get_fails_is_false() -> None:
    # 405 with a failing GET retry is not a 403, so it is rejected.
    with patch(
        "latris.ai.validate_urls.urlopen",
        side_effect=[_http_error(405), URLError("nope")],
    ):
        assert check_url("http://example.com") is False


def test_check_url_other_http_error_is_false() -> None:
    with patch("latris.ai.validate_urls.urlopen", side_effect=_http_error(500)):
        assert check_url("http://example.com") is False


def test_check_url_url_error_is_false() -> None:
    with patch("latris.ai.validate_urls.urlopen", side_effect=URLError("dns")):
        assert check_url("http://nonexistent.invalid") is False


def test_check_url_value_error_is_false() -> None:
    # e.g. a malformed/unsupported URL.
    with patch("latris.ai.validate_urls.urlopen", side_effect=ValueError("bad url")):
        assert check_url("not-a-url") is False


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
