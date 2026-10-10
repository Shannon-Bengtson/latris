"""View projection and mapping endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from latris.operations import mappings as map_ops
from latris.operations import views as view_ops
from latris.server.deps import get_project_root

router = APIRouter(prefix="/api/views", tags=["views"])
Root = Annotated[Path, Depends(get_project_root)]


class MapRequest(BaseModel):
    l2_query: str
    view_kind: str
    l3_id: str | None = None
    ai_proposed: bool = False


@router.post("/{view_kind}/project")
def project_view(view_kind: str, root: Root) -> dict[str, Any]:
    view = view_ops.project_view(view_kind, root=root)
    return {"result": view.model_dump(mode="json")}


@router.post("/{view_kind}/auto-project")
def auto_project(view_kind: str, root: Root) -> dict[str, Any]:
    mappings = view_ops.auto_project(view_kind, root=root)
    return {"mappings": [m.model_dump(mode="json") for m in mappings]}


@router.get("/mappings")
def list_mappings(root: Root, view_kind: str | None = None) -> list[dict[str, Any]]:
    return [m.model_dump(mode="json") for m in map_ops.list_mappings(view_kind, root=root)]


@router.post("/mappings", status_code=201)
def map_to_view(body: MapRequest, root: Root) -> dict[str, Any]:
    mapping, sha = map_ops.map_to_view(
        body.l2_query,
        body.view_kind,
        l3_id=body.l3_id,
        ai_proposed=body.ai_proposed,
        root=root,
    )
    return {"result": mapping.model_dump(mode="json"), "commit_sha": sha}


@router.delete("/mappings/{l2_query}/{view_kind}")
def unmap_from_view(l2_query: str, view_kind: str, root: Root) -> dict[str, Any]:
    mapping, sha = map_ops.unmap_from_view(l2_query, view_kind, root=root)
    return {"result": mapping.model_dump(mode="json"), "commit_sha": sha}


@router.post("/mappings/{l2_query}/{view_kind}/approve")
def approve_mapping(l2_query: str, view_kind: str, root: Root) -> dict[str, Any]:
    mapping, sha = map_ops.approve_mapping(l2_query, view_kind, root=root)
    return {"result": mapping.model_dump(mode="json"), "commit_sha": sha}
