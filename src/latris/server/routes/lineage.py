"""Lineage endpoints — version tree, milestones, alternatives."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from latris.operations import lineage as lineage_ops
from latris.operations import sync as sync_ops
from latris.repo.git import GitError
from latris.schema import Maturity
from latris.server.deps import get_project_root
from latris.server.watch import mark_own_mutation

router = APIRouter(prefix="/api/lineage", tags=["lineage"])
Root = Annotated[Path, Depends(get_project_root)]


def _guard_sync(fn: Any) -> Any:
    """Convert sync/git transport failures into clean 400s (as routes/sync does)."""
    try:
        return fn()
    except (sync_ops.SyncError, GitError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


# -- Request bodies -----------------------------------------------------------


class MilestoneRequest(BaseModel):
    name: str
    maturity: Maturity = "proposed"
    notes: str | None = None


class AlternativeRequest(BaseModel):
    name: str
    from_milestone: str | None = None
    notes: str | None = None


class RestoreRequest(BaseModel):
    milestone_query: str
    name: str
    notes: str | None = None


class SwitchRequest(BaseModel):
    version_query: str


class PreferredRequest(BaseModel):
    version_query: str


class VersionUpdateRequest(BaseModel):
    name: str | None = None
    maturity: Maturity | None = None
    notes: str | None = None


class VersionQueryRequest(BaseModel):
    version_query: str


class AddToWorkspaceRequest(BaseModel):
    branch: str


class ReconcileRequest(BaseModel):
    version_query: str
    keep: str  # "mine" | "theirs"


# -- Endpoints ----------------------------------------------------------------


@router.get("/tree")
def get_tree(root: Root, include_archived: bool = False) -> dict[str, Any]:
    return lineage_ops.get_lineage_tree(root, include_archived=include_archived)


@router.get("/current")
def get_current(root: Root) -> dict[str, Any]:
    node = lineage_ops.ensure_root_lineage(root)
    return node.model_dump(mode="json")


@router.post("/milestone", status_code=201)
def create_milestone(body: MilestoneRequest, root: Root) -> dict[str, Any]:
    milestone, sha = lineage_ops.create_milestone(
        body.name,
        maturity=body.maturity,
        notes=body.notes,
        root=root,
    )
    mark_own_mutation()
    return {"result": milestone.model_dump(mode="json"), "commit_sha": sha}


@router.post("/alternative", status_code=201)
def create_alternative(body: AlternativeRequest, root: Root) -> dict[str, Any]:
    node, branch = lineage_ops.create_alternative(
        body.name,
        from_milestone=body.from_milestone,
        notes=body.notes,
        root=root,
    )
    mark_own_mutation()
    return {"result": node.model_dump(mode="json"), "branch": branch}


@router.post("/restore", status_code=201)
def restore_from_milestone(body: RestoreRequest, root: Root) -> dict[str, Any]:
    node, branch = lineage_ops.restore_milestone(
        body.milestone_query,
        body.name,
        notes=body.notes,
        root=root,
    )
    mark_own_mutation()
    return {"result": node.model_dump(mode="json"), "branch": branch}


@router.post("/switch")
def switch_version(body: SwitchRequest, root: Root) -> dict[str, Any]:
    result = lineage_ops.switch_version(body.version_query, root=root)
    mark_own_mutation()
    # Result may be a dict or LineageNode depending on resolution path.
    if isinstance(result, dict):
        return {"result": result}
    return {"result": result.model_dump(mode="json")}


@router.patch("/version")
def update_version(body: VersionUpdateRequest, root: Root) -> dict[str, Any]:
    node, sha = lineage_ops.update_version(
        name=body.name,
        maturity=body.maturity,
        notes=body.notes,
        root=root,
    )
    mark_own_mutation()
    return {"result": node.model_dump(mode="json"), "commit_sha": sha}


@router.post("/preferred")
def set_preferred(body: PreferredRequest, root: Root) -> dict[str, Any]:
    version_id, sha = lineage_ops.set_preferred(body.version_query, root=root)
    mark_own_mutation()
    return {"version_id": version_id, "commit_sha": sha}


@router.get("/compare")
def compare_versions(
    root: Root,
    a: str = Query(..., description="Version A (ID, name, or branch)"),
    b: str = Query(..., description="Version B (ID, name, or branch)"),
) -> list[dict[str, Any]]:
    return lineage_ops.compare_versions(a, b, root=root)


# -- Per-version sync (Publish / Get latest / Add to my workspace) ------------


@router.post("/sync/refresh")
def sync_refresh(root: Root) -> dict[str, Any]:
    """Fetch remote refs (network) and return fresh per-version sync state."""
    return _guard_sync(lambda: sync_ops.authed_refresh_sync(root=root))


@router.post("/publish")
def publish(body: VersionQueryRequest, root: Root) -> dict[str, Any]:
    result = _guard_sync(lambda: sync_ops.authed_publish_version(body.version_query, root=root))
    mark_own_mutation()
    return result


@router.post("/get-latest")
def get_latest(body: VersionQueryRequest, root: Root) -> dict[str, Any]:
    result = _guard_sync(lambda: sync_ops.authed_get_latest(body.version_query, root=root))
    mark_own_mutation()
    return result


@router.post("/add-to-workspace")
def add_to_workspace(body: AddToWorkspaceRequest, root: Root) -> dict[str, Any]:
    result = _guard_sync(lambda: sync_ops.authed_add_to_workspace(body.branch, root=root))
    mark_own_mutation()
    return result


@router.post("/reconcile/preview")
def reconcile_preview(body: VersionQueryRequest, root: Root) -> list[dict[str, Any]]:
    return _guard_sync(lambda: lineage_ops.reconcile_preview(body.version_query, root=root))


@router.post("/reconcile")
def reconcile(body: ReconcileRequest, root: Root) -> dict[str, Any]:
    result = _guard_sync(lambda: sync_ops.authed_reconcile(body.version_query, body.keep, root=root))
    mark_own_mutation()
    return result
