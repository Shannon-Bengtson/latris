"""Optional shared-secret gate for the API server.

The server has no user accounts: on a desktop it trusts whoever can reach
``127.0.0.1``. That is not enough when it runs somewhere else can reach
it — e.g. one container per user behind a session broker, where other
containers on the same network could otherwise call it directly.

Set ``LATRIS_SERVER_TOKEN`` (or pass ``access_token`` to ``create_app``)
and every HTTP and WebSocket request must then carry the token, as either
``X-Latris-Token: <token>`` or ``Authorization: Bearer <token>``.
``/api/health`` and CORS preflights stay open so liveness probes and
browsers keep working. With no token configured the gate is off (the
local desktop/dev default).
"""

from __future__ import annotations

import hmac
import ipaddress
import json
import os
import sys

TOKEN_ENV = "LATRIS_SERVER_TOKEN"
TOKEN_HEADER = "x-latris-token"
_OPEN_PATHS = frozenset({"/api/health"})


def configured_token() -> str | None:
    token = os.environ.get(TOKEN_ENV, "").strip()
    return token or None


def _presented_token(headers: list[tuple[bytes, bytes]]) -> str | None:
    for raw_name, raw_value in headers:
        name = raw_name.decode("latin-1").lower()
        value = raw_value.decode("latin-1").strip()
        if name == TOKEN_HEADER:
            return value
        if name == "authorization" and value.lower().startswith("bearer "):
            return value[7:].strip()
    return None


class AccessTokenMiddleware:
    """Pure ASGI middleware so it covers WebSockets as well as HTTP."""

    def __init__(self, app, *, token: str) -> None:
        self.app = app
        self._token = token.encode("utf-8")

    def _allowed(self, scope) -> bool:
        if scope.get("path") in _OPEN_PATHS:
            return True
        if scope["type"] == "http" and scope.get("method") == "OPTIONS":
            return True  # CORS preflight carries no custom headers
        presented = _presented_token(scope.get("headers") or [])
        return presented is not None and hmac.compare_digest(presented.encode("utf-8"), self._token)

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] not in ("http", "websocket") or self._allowed(scope):
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 4401})
            return
        body = json.dumps({"error": "unauthorized", "detail": "missing or invalid server token"}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
            }
        )
        await send({"type": "http.response.body", "body": body})


def warn_if_exposed(host: str) -> None:
    """Warn loudly when binding beyond loopback with no token configured."""
    try:
        loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = host == "localhost"
    if not loopback and configured_token() is None:
        print(
            f"WARNING: latris server is listening on {host} with no access token. Anyone who can "
            f"reach this address can read and change the project and run AI calls. Set "
            f"{TOKEN_ENV} or bind to 127.0.0.1.",
            file=sys.stderr,
        )
