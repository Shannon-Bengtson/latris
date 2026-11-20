"""Which factors and links are in which model type's view: add every one not left out (when a type is
opened), put one in (or back), or leave one out and keep it out."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from latris.operations import mappings as map_ops
from latris.operations import views as view_ops
from latris.server.deps import Root

router = APIRouter(prefix="/api/views", tags=["views"])


class MapRequest(BaseModel):
    l2_query: str
    view_kind: str


class LeaveOutRequest(MapRequest):
    reason: str | None = None


@router.post("/{view_kind}/auto-project")
def auto_project(view_kind: str, root: Root) -> dict[str, Any]:
    """Put every factor and link not yet in the view in it — except what's been left out."""
    mappings = view_ops.auto_project(view_kind, root=root)
    return {"mappings": [m.model_dump(mode="json") for m in mappings]}


@router.post("/mappings", status_code=201)
def map_to_view(body: MapRequest, root: Root) -> dict[str, Any]:
    """Put a factor or link in a model type's view (back in, if it was left out), and re-project it."""
    mapping, _ = map_ops.map_to_view(body.l2_query, body.view_kind, root=root)
    view_ops.project_view(body.view_kind, root=root)
    return {"result": mapping.model_dump(mode="json")}


@router.post("/mappings/leave-out")
def leave_out(body: LeaveOutRequest, root: Root) -> dict[str, Any]:
    """Leave a factor or link out of a model type's view and keep it out; re-project the view."""
    entry, _ = map_ops.leave_out(body.l2_query, body.view_kind, reason=body.reason, root=root)
    view_ops.project_view(body.view_kind, root=root)
    return {"result": entry.model_dump(mode="json")}
