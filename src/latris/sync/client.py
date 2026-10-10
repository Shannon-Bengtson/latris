"""HTTP client for the Latris sync control plane.

Used by the local backend (server-to-server), so credentials are handled
here, not in the browser. Accepts an injected ``httpx.Client`` for testing.
"""

from __future__ import annotations

from typing import Any

import httpx


class SyncClientError(RuntimeError):
    """Raised when a control-plane call fails (network or HTTP error).

    ``status_code`` is the HTTP status when the server responded with an error,
    or ``None`` for a transport/network failure (couldn't reach the server) —
    callers use this to distinguish "revoked" (401/403) from "offline".
    """

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class SyncClient:
    def __init__(
        self,
        server_url: str,
        session_token: str | None = None,
        *,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._token = session_token
        if client is not None:
            self._client = client
            self._owns_client = False
        else:
            self._client = httpx.Client(base_url=server_url.rstrip("/"), timeout=timeout)
            self._owns_client = True

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"} if self._token else {}

    def _request(self, method: str, path: str, **kwargs: Any) -> dict:
        try:
            resp = self._client.request(method, path, headers=self._headers(), **kwargs)
        except httpx.HTTPError as exc:
            raise SyncClientError(f"could not reach the sync server: {exc}") from exc
        if resp.status_code >= 400:
            detail = None
            try:
                body = resp.json()
                detail = body.get("detail") if isinstance(body, dict) else None
            except Exception:  # noqa: BLE001
                detail = None
            raise SyncClientError(
                detail if isinstance(detail, str) else f"sync server error (HTTP {resp.status_code})",
                status_code=resp.status_code,
            )
        return resp.json() if resp.content else {}

    # -- auth --
    def request_code(self, email: str, intent: str = "auto") -> dict:
        return self._request("POST", "/api/auth/request-code", json={"email": email, "intent": intent})

    def verify_code(
        self,
        email: str,
        code: str,
        device: str | None = None,
        *,
        intent: str = "auto",
        first_name: str | None = None,
        last_name: str | None = None,
        organisation: str | None = None,
        country: str | None = None,
        role: str | None = None,
        industry: str | None = None,
    ) -> dict:
        return self._request(
            "POST",
            "/api/auth/verify-code",
            json={
                "email": email,
                "code": code,
                "device_name": device,
                "intent": intent,
                "first_name": first_name,
                "last_name": last_name,
                "organisation": organisation,
                "country": country,
                "role": role,
                "industry": industry,
            },
        )

    def update_profile(
        self,
        first_name: str | None,
        last_name: str | None,
        organisation: str | None,
        country: str | None = None,
        role: str | None = None,
        industry: str | None = None,
    ) -> dict:
        return self._request(
            "PATCH",
            "/api/auth/profile",
            json={
                "first_name": first_name,
                "last_name": last_name,
                "organisation": organisation,
                "country": country,
                "role": role,
                "industry": industry,
            },
        )

    def validate(self) -> dict:
        """Re-check the current session/account. 200 → account dict; 401/403 → revoked."""
        return self._request("GET", "/api/auth/validate")

    def refresh(self) -> dict:
        return self._request("POST", "/api/auth/refresh")

    def logout(self) -> dict:
        return self._request("POST", "/api/auth/logout")

    def regenerate_gitea_token(self) -> dict:
        return self._request("POST", "/api/gitea/token")

    def me(self) -> dict:
        return self._request("GET", "/api/me")

    # -- projects + members --
    def create_project(self, name: str) -> dict:
        return self._request("POST", "/api/projects", json={"name": name})

    def get_project(self, project_id: str) -> dict:
        return self._request("GET", f"/api/projects/{project_id}")

    def add_member(self, project_id: str, email: str, role: str) -> dict:
        return self._request("POST", f"/api/projects/{project_id}/members", json={"email": email, "role": role})

    def update_member(self, project_id: str, account_id: str, role: str) -> dict:
        return self._request("PATCH", f"/api/projects/{project_id}/members/{account_id}", json={"role": role})

    def remove_member(self, project_id: str, account_id: str) -> dict:
        return self._request("DELETE", f"/api/projects/{project_id}/members/{account_id}")
