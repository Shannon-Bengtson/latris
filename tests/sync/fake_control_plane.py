"""A fake sync control plane, a fake keyring and local bare git remotes — for sync tests.

Hermetic stand-ins for the three things the sync broker (``operations/sync.py``) talks to:

- **the control plane**: an in-memory accounts/projects/members service behind an
  ``httpx.MockTransport``. Every ``SyncClient`` the broker builds is given this transport, so
  the real client code (headers, error mapping) runs; nothing reaches the network.
- **the keyring**: a dict replacing ``keyring.get/set/delete_password``, so the real OS keyring
  is never read or written.
- **the git remote**: each project the plane creates gets its own local bare repository, which
  is its ``clone_url``; pushes and pulls are real git against it.

Failures are injected on the plane: ``fail(...)`` makes matching requests answer with an HTTP
error (401 expired login, 403 refused, 404, 5xx), and ``offline = True`` makes every request a
connection error.

Use it from a test module with a two-line fixture::

    @pytest.fixture
    def world(tmp_path, monkeypatch):
        return SyncWorld.install(tmp_path, monkeypatch)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest

from latris.operations import sync as sync_ops
from latris.repo import git
from latris.sync import credentials
from latris.sync.client import SyncClient

SERVER = "https://sync.test"
GOOD_CODE = "123456"


@dataclass
class _Failure:
    method: str | None
    pattern: str
    status: int
    detail: str | None
    times: int | None  # None = every matching request


@dataclass
class FakeControlPlane:
    """In-memory control plane. Its ``handler`` serves the routes ``SyncClient`` calls."""

    remotes_dir: Path
    accounts: dict[str, dict[str, Any]] = field(default_factory=dict)  # email -> account
    sessions: dict[str, str] = field(default_factory=dict)  # session token -> account id
    projects: dict[str, dict[str, Any]] = field(default_factory=dict)
    requests: list[tuple[str, str]] = field(default_factory=list)
    offline: bool = False
    _failures: list[_Failure] = field(default_factory=list)
    _n: int = 0

    # -- failure injection --
    def fail(
        self,
        pattern: str = "",
        status: int = 500,
        *,
        method: str | None = None,
        detail: str | None = None,
        times: int | None = None,
    ) -> None:
        """Answer requests whose path matches *pattern* (a regex, searched) with *status*."""
        self._failures.append(_Failure(method, pattern, status, detail, times))

    def expire_sessions(self) -> None:
        """Forget every session token: the next authed call gets a 401."""
        self.sessions.clear()

    # -- helpers --
    def _next(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}_{self._n}"

    def account(self, email: str, display_name: str | None = None) -> dict[str, Any]:
        if email not in self.accounts:
            self.accounts[email] = {
                "id": self._next("acct"),
                "email": email,
                "display_name": display_name or email.split("@")[0].title(),
            }
        return self.accounts[email]

    def _by_id(self, account_id: str) -> dict[str, Any] | None:
        return next((a for a in self.accounts.values() if a["id"] == account_id), None)

    def _caller(self, request: httpx.Request) -> dict[str, Any] | None:
        auth = request.headers.get("authorization", "")
        token = auth.removeprefix("Bearer ").strip()
        acct_id = self.sessions.get(token)
        return self._by_id(acct_id) if acct_id else None

    def _role(self, proj: dict[str, Any], acct: dict[str, Any]) -> str | None:
        return next((m["role"] for m in proj["members"] if m["account_id"] == acct["id"]), None)

    # -- transport --
    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)

    def handler(self, request: httpx.Request) -> httpx.Response:
        path, method = request.url.path, request.method
        self.requests.append((method, path))
        if self.offline:
            raise httpx.ConnectError("connection refused", request=request)
        for f in list(self._failures):
            if (f.method is None or f.method == method) and re.search(f.pattern, path):
                if f.times is not None:
                    f.times -= 1
                    if f.times <= 0:
                        self._failures.remove(f)
                body = {"detail": f.detail} if f.detail else {"error": "x"}
                return httpx.Response(f.status, json=body)
        body = json.loads(request.content) if request.content else {}
        return self._route(method, path, body, request)

    def _route(self, method: str, path: str, body: dict, request: httpx.Request) -> httpx.Response:
        if path == "/api/auth/request-code":
            return httpx.Response(200, json={"ok": True})
        if path == "/api/auth/verify-code":
            return self._verify(body)
        acct = self._caller(request)
        if acct is None:
            return httpx.Response(401, json={"detail": "session expired"})
        if path == "/api/auth/validate":
            return httpx.Response(200, json=acct)
        if path == "/api/auth/logout":
            token = request.headers["authorization"].removeprefix("Bearer ")
            self.sessions.pop(token, None)
            return httpx.Response(200, json={"ok": True})
        if path == "/api/auth/profile":
            for k in ("first_name", "last_name", "organisation"):
                if body.get(k) is not None:
                    acct[k] = body[k]
            if body.get("first_name"):
                acct["display_name"] = f"{body['first_name']} {body.get('last_name') or ''}".strip()
            return httpx.Response(200, json=acct)
        if path == "/api/me":
            mine = [p for p in self.projects.values() if self._role(p, acct)]
            return httpx.Response(200, json={**acct, "projects": [{"id": p["id"], "name": p["name"]} for p in mine]})
        if path == "/api/projects" and method == "POST":
            return self._create(body, acct)
        m = re.fullmatch(r"/api/projects/([^/]+)(/.*)?", path)
        if m:
            return self._project(method, m.group(1), m.group(2) or "", body, acct)
        return httpx.Response(404, json={"detail": "no such route"})

    def _verify(self, body: dict) -> httpx.Response:
        if body.get("code") != GOOD_CODE:
            return httpx.Response(400, json={"detail": "invalid or expired code"})
        acct = self.account(body["email"])
        token = self._next("sess")
        self.sessions[token] = acct["id"]
        return httpx.Response(
            200,
            json={
                "account": acct,
                "session_token": token,
                "gitea": {"token": f"gt-{acct['id']}", "username": acct["id"], "base_url": SERVER},
            },
        )

    def _create(self, body: dict, acct: dict) -> httpx.Response:
        pid = self._next("proj")
        bare = self.remotes_dir / f"{pid}.git"
        git.init_bare(bare)
        self.projects[pid] = {
            "id": pid,
            "name": body["name"],
            "clone_url": str(bare),
            "report_url": None,
            "report_pack": None,
            "members": [_member(acct, "owner")],
        }
        return httpx.Response(200, json=self._public(self.projects[pid]))

    def _public(self, proj: dict) -> dict:
        return {k: v for k, v in proj.items() if k != "members"} | {"members": [dict(m) for m in proj["members"]]}

    def _project(self, method: str, pid: str, rest: str, body: dict, acct: dict) -> httpx.Response:
        proj = self.projects.get(pid)
        role = self._role(proj, acct) if proj else None
        if proj is None or role is None:
            return httpx.Response(404, json={"detail": "project not found"})
        if rest == "" and method == "GET":
            return httpx.Response(200, json=self._public(proj))
        if role != "owner":
            return httpx.Response(403, json={"detail": "only the owner can do that"})
        if rest == "/report":
            proj["report_url"] = f"{SERVER}/r/{self._next('rep')}" if body["enabled"] else None
            proj["report_pack"] = body.get("pack") or "client"
            return httpx.Response(200, json={"report_url": proj["report_url"], "report_pack": proj["report_pack"]})
        if rest == "/members" and method == "POST":
            member = _member(self.account(body["email"]), body["role"])
            proj["members"].append(member)
            return httpx.Response(200, json=member)
        m = re.fullmatch(r"/members/([^/]+)", rest)
        if m:
            target = next((x for x in proj["members"] if x["account_id"] == m.group(1)), None)
            if target is None:
                return httpx.Response(404, json={"detail": "not a member"})
            if method == "PATCH":
                target["role"] = body["role"]
                return httpx.Response(200, json=target)
            proj["members"].remove(target)
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(404, json={"detail": "no such route"})


def _member(acct: dict, role: str) -> dict[str, Any]:
    return {"account_id": acct["id"], "email": acct["email"], "display_name": acct["display_name"], "role": role}


class FakeKeyring:
    """A dict standing in for the OS keyring (``keyring.get/set/delete_password``)."""

    def __init__(self) -> None:
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, key: str) -> str | None:
        return self.store.get((service, key))

    def set_password(self, service: str, key: str, value: str) -> None:
        self.store[(service, key)] = value

    def delete_password(self, service: str, key: str) -> None:
        del self.store[(service, key)]  # KeyError for a missing key, like the real backends

    def keys(self) -> set[str]:
        return {k for _, k in self.store}


@dataclass
class SyncWorld:
    plane: FakeControlPlane
    keyring: FakeKeyring
    tmp_path: Path

    @classmethod
    def install(cls, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SyncWorld:
        remotes = tmp_path / "remotes"
        remotes.mkdir()
        plane = FakeControlPlane(remotes_dir=remotes)
        kr = FakeKeyring()
        for name in ("get_password", "set_password", "delete_password"):
            monkeypatch.setattr(credentials.keyring, name, getattr(kr, name))

        def make_client(server_url: str, session_token: str | None = None, *, timeout: float = 30.0, client=None):
            hc = httpx.Client(base_url=server_url.rstrip("/"), transport=plane.transport, timeout=timeout)
            return SyncClient(server_url, session_token, client=hc)

        monkeypatch.setattr(sync_ops, "SyncClient", make_client)
        return cls(plane=plane, keyring=kr, tmp_path=tmp_path)

    def sign_in(self, email: str = "alice@example.org") -> dict:
        """Sign in through the real login flow (request a code, verify it)."""
        sync_ops.login_request_code(SERVER, email)
        return sync_ops.login_verify(SERVER, email, GOOD_CODE, "laptop")

    def bare(self, pid: str) -> Path:
        return Path(self.plane.projects[pid]["clone_url"])

    def collaborator_clone(self, pid: str, name: str = "bob") -> Path:
        """A plain (unauthed) clone of the project's remote: someone else's machine."""
        dest = self.tmp_path / name
        git.clone(str(self.bare(pid)), dest)
        return dest
