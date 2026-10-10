"""Local-backend sync routes — a thin GUI-facing wrapper over operations.sync.

These broker login + git transport for the currently-open project. SyncError
and GitError are RuntimeErrors (which the app's global handler would turn into
a 502), so each handler converts them to a clean 400.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from latris.operations import sync as ops
from latris.repo.git import GitError
from latris.server.deps import get_project_root

router = APIRouter(prefix="/api/sync", tags=["sync"])
Root = Annotated[Path, Depends(get_project_root)]


def _guard(fn: Callable[[], Any]) -> Any:
    try:
        return fn()
    except ops.SyncError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except GitError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


class LoginRequestBody(BaseModel):
    server_url: str
    email: str
    intent: str = "auto"


class LoginVerifyBody(BaseModel):
    server_url: str
    email: str
    code: str
    device_name: str | None = None
    intent: str = "auto"
    first_name: str | None = None
    last_name: str | None = None
    organisation: str | None = None
    country: str | None = None
    role: str | None = None
    industry: str | None = None


class ProfileBody(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    organisation: str | None = None
    country: str | None = None
    role: str | None = None
    industry: str | None = None


class RemoteBody(BaseModel):
    url: str


class ShareBody(BaseModel):
    name: str


class AddMemberBody(BaseModel):
    email: str
    role: str = "collaborator"


class UpdateMemberBody(BaseModel):
    role: str


class ResolveBody(BaseModel):
    strategy: str  # "ours" | "theirs"


class CloneBody(BaseModel):
    project_id: str
    dest: str


@router.get("/status")
def status(root: Root) -> dict[str, Any]:
    return _guard(lambda: ops.sync_status(root=root))


@router.get("/account")
def account() -> dict[str, Any]:
    return {"account": ops.current_account()}


@router.post("/validate")
def validate() -> dict[str, Any]:
    """Re-validate access against the control plane (with offline grace).

    Returns ``{state, allowed, account}`` — ``allowed`` is True for ``valid``
    and ``offline_ok``; the GUI routes to the workspace when allowed, else to
    the login screen. Never raises (validate_access resolves all cases)."""
    result = ops.validate_access()
    allowed = result["state"] in ("valid", "offline_ok")
    return {"state": result["state"], "allowed": allowed, "account": result["account"]}


@router.post("/login/request")
def login_request(body: LoginRequestBody) -> dict[str, bool]:
    _guard(lambda: ops.login_request_code(body.server_url, body.email, body.intent))
    return {"ok": True}


@router.post("/login/verify")
def login_verify(body: LoginVerifyBody) -> dict[str, Any]:
    acct = _guard(
        lambda: ops.login_verify(
            body.server_url,
            body.email,
            body.code,
            body.device_name,
            intent=body.intent,
            first_name=body.first_name,
            last_name=body.last_name,
            organisation=body.organisation,
            country=body.country,
            role=body.role,
            industry=body.industry,
        )
    )
    return {"account": acct}


@router.patch("/profile")
def update_profile(body: ProfileBody) -> dict[str, Any]:
    acct = _guard(
        lambda: ops.update_profile(
            body.first_name,
            body.last_name,
            body.organisation,
            body.country,
            body.role,
            body.industry,
        )
    )
    return {"account": acct}


@router.post("/logout")
def logout() -> dict[str, bool]:
    ops.logout()
    return {"ok": True}


@router.get("/projects")
def projects() -> dict[str, Any]:
    return {"projects": _guard(ops.list_remote_projects)}


@router.post("/remote")
def set_remote(body: RemoteBody, root: Root) -> dict[str, bool]:
    _guard(lambda: ops.set_remote(body.url, root=root))
    return {"ok": True}


@router.post("/share")
def share(body: ShareBody, root: Root) -> dict[str, Any]:
    return {"project": _guard(lambda: ops.share(body.name, root=root))}


@router.post("/push")
def push(root: Root) -> dict[str, str]:
    return {"head": _guard(lambda: ops.authed_push(root=root))}


@router.post("/pull")
def pull(root: Root) -> dict[str, Any]:
    return _guard(lambda: ops.authed_pull(root=root))


@router.post("/resolve")
def resolve(body: ResolveBody, root: Root) -> dict[str, str]:
    return {"head": _guard(lambda: ops.resolve_conflict(body.strategy, root=root))}


@router.post("/abort")
def abort(root: Root) -> dict[str, bool]:
    _guard(lambda: ops.abort_conflict(root=root))
    return {"ok": True}


@router.get("/members")
def members(root: Root) -> dict[str, Any]:
    records = _guard(lambda: ops.read_members(root=root))
    return {"members": [r.model_dump(mode="json") for r in records]}


@router.post("/members")
def add_member(body: AddMemberBody, root: Root) -> dict[str, Any]:
    return {"member": _guard(lambda: ops.add_member(body.email, body.role, root=root))}


@router.patch("/members/{account_id}")
def update_member(account_id: str, body: UpdateMemberBody, root: Root) -> dict[str, Any]:
    return {"member": _guard(lambda: ops.update_member(account_id, body.role, root=root))}


@router.delete("/members/{account_id}")
def remove_member(account_id: str, root: Root) -> dict[str, Any]:
    return _guard(lambda: ops.remove_member(account_id, root=root))


@router.post("/clone")
def clone(body: CloneBody) -> dict[str, str]:
    path = _guard(lambda: ops.clone_project(body.project_id, Path(body.dest)))
    return {"path": str(path)}
