"""Outbound-request guard for user- or AI-supplied URLs (SSRF defence).

Lives at the package root (beside :mod:`latris._mutation_signal`) because
both ``operations/`` and ``ai/`` fetch URLs they did not choose.

When the server runs as a hosted session (one container per user), an
unguarded "fetch this source" would let a user read anything the
container can reach: other sessions' unauthenticated APIs, cloud
metadata services, loopback admin ports. So every such URL must be
``http(s)``, and every address its host resolves to — on the first
request *and* after every redirect — must be a public (globally
routable) address. Responses are size-capped.

Set ``LATRIS_ALLOW_PRIVATE_FETCH=1`` to lift the address check for a
local install that genuinely needs an intranet source.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urljoin, urlsplit

MAX_FETCH_BYTES = 25 * 1024 * 1024
MAX_REDIRECTS = 5

_ALLOWED_SCHEMES = {"http", "https"}


class BlockedURLError(ValueError):
    """The URL is not allowed to be fetched (scheme or address)."""


def _private_fetch_allowed() -> bool:
    return os.environ.get("LATRIS_ALLOW_PRIVATE_FETCH", "").strip().lower() in {"1", "true", "yes"}


def _is_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def check_public_url(url: str) -> None:
    """Raise :class:`BlockedURLError` unless *url* is http(s) to a public host."""
    parts = urlsplit(url)
    if parts.scheme.lower() not in _ALLOWED_SCHEMES:
        raise BlockedURLError(f"only http(s) URLs can be fetched, not {parts.scheme or 'no scheme'!r}")
    host = parts.hostname
    if not host:
        raise BlockedURLError(f"URL {url!r} has no host")
    if _private_fetch_allowed():
        return
    try:
        port = parts.port or (443 if parts.scheme.lower() == "https" else 80)
    except ValueError as exc:
        raise BlockedURLError(f"URL {url!r} has an invalid port") from exc
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise BlockedURLError(f"could not resolve host {host!r}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%", 1)[0])
        if not _is_public_ip(ip):
            raise BlockedURLError(f"refusing to fetch {host!r}: it resolves to a non-public address ({ip})")


def safe_get(
    url: str,
    *,
    timeout: float = 20,
    headers: dict[str, str] | None = None,
    max_bytes: int = MAX_FETCH_BYTES,
    max_redirects: int = MAX_REDIRECTS,
):
    """GET *url* with the guard applied to every hop; returns an ``httpx.Response``.

    The body is read in full (up to *max_bytes*, else ``ValueError``) so
    callers can use ``.text`` / ``.content`` as with ``httpx.get``.
    """
    import httpx

    current = url
    with httpx.Client(timeout=timeout, follow_redirects=False, headers=headers) as client:
        for _ in range(max_redirects + 1):
            check_public_url(current)
            with client.stream("GET", current) as response:
                if response.is_redirect and "location" in response.headers:
                    current = urljoin(str(response.url), response.headers["location"])
                    continue
                declared = response.headers.get("content-length")
                if declared and declared.isdigit() and int(declared) > max_bytes:
                    raise ValueError(f"response is too large ({declared} bytes; limit {max_bytes})")
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        raise ValueError(f"response is too large (over {max_bytes} bytes)")
                    chunks.append(chunk)
                response._content = b"".join(chunks)  # noqa: SLF001 — make .text/.content usable after close
                return response
    raise ValueError(f"too many redirects (more than {max_redirects})")
