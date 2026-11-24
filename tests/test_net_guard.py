"""SSRF guard for fetched URLs — hermetic (DNS and HTTP are faked)."""

from __future__ import annotations

import httpx
import pytest

from latris import _net_guard
from latris._net_guard import BlockedURLError, check_public_url, safe_get, safe_status

_DNS = {
    "public.example": "93.184.216.34",
    "loopback.example": "127.0.0.1",
    "metadata.example": "169.254.169.254",
    "private.example": "10.1.2.3",
    "docker.example": "172.18.0.3",
    "v6local.example": "::1",
    "mapped.example": "::ffff:127.0.0.1",
}


@pytest.fixture(autouse=True)
def fake_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    def getaddrinfo(host, port, **_):
        if host in _DNS:
            return [(2, 1, 6, "", (_DNS[host], port))]
        try:  # literal IPs resolve to themselves
            import ipaddress

            ipaddress.ip_address(host)
            return [(2, 1, 6, "", (host, port))]
        except ValueError:
            import socket

            raise socket.gaierror("unknown host") from None

    monkeypatch.setattr(_net_guard.socket, "getaddrinfo", getaddrinfo)
    monkeypatch.delenv("LATRIS_ALLOW_PRIVATE_FETCH", raising=False)


def test_public_https_allowed() -> None:
    check_public_url("https://public.example/paper")


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://public.example/x",
        "gopher://public.example/",
        "http://loopback.example/",
        "http://metadata.example/metadata/instance",
        "http://private.example/",
        "http://docker.example:8741/api/state",
        "http://v6local.example/",
        "http://mapped.example/",
        "http://127.0.0.1:8741/api/state",
        "http://169.254.169.254/",
        "http://[::1]/",
        "http://unknown.example/",
        "http:///nohost",
    ],
)
def test_blocked_urls(url: str) -> None:
    with pytest.raises(BlockedURLError):
        check_public_url(url)


def test_opt_out_for_local_installs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LATRIS_ALLOW_PRIVATE_FETCH", "1")
    check_public_url("http://private.example/")
    with pytest.raises(BlockedURLError):  # scheme is still enforced
        check_public_url("file:///etc/passwd")


def _patch_transport(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    real_client = httpx.Client

    def client(**kwargs):
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "Client", client)


def test_safe_get_follows_public_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/final"})
        return httpx.Response(200, text="hello", headers={"content-type": "text/plain"})

    _patch_transport(monkeypatch, handler)
    response = safe_get("https://public.example/start")
    assert response.text == "hello"


def test_safe_get_blocks_redirect_to_private(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://metadata.example/latest"})

    _patch_transport(monkeypatch, handler)
    with pytest.raises(BlockedURLError):
        safe_get("https://public.example/start")


def test_safe_get_caps_size(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 2048)

    _patch_transport(monkeypatch, handler)
    with pytest.raises(ValueError, match="too large"):
        safe_get("https://public.example/big", max_bytes=1024)


def test_safe_get_redirect_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "/again"})

    _patch_transport(monkeypatch, handler)
    with pytest.raises(ValueError, match="redirects"):
        safe_get("https://public.example/loop")


def test_safe_status_checks_every_hop_and_reads_no_body(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/final"})
        if request.url.path == "/inward":
            return httpx.Response(302, headers={"location": "http://loopback.example/admin"})
        return httpx.Response(204)

    _patch_transport(monkeypatch, handler)
    assert safe_status("https://public.example/start") == 204
    assert [r.method for r in seen] == ["HEAD", "HEAD"]
    seen.clear()
    with pytest.raises(BlockedURLError):
        safe_status("https://public.example/inward", method="GET")
    assert [r.url.host for r in seen] == ["public.example"]


def test_safe_status_redirect_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_transport(monkeypatch, lambda request: httpx.Response(302, headers={"location": "/again"}))
    with pytest.raises(ValueError, match="redirects"):
        safe_status("https://public.example/loop")

