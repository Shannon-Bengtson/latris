"""View-specific attribute endpoints (e.g. CLD polarity)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from latris.operations import view_attributes as view_attr_ops
from latris.server.deps import get_project_root

router = APIRouter(prefix="/api/views", tags=["view-attributes"])
Root = Annotated[Path, Depends(get_project_root)]


class SetViewAttributeRequest(BaseModel):
    value: str


@router.put("/{view_kind}/attributes/{target}/{attribute}")
def set_view_attribute(
    view_kind: str,
    target: str,
    attribute: str,
    body: SetViewAttributeRequest,
    root: Root,
) -> dict[str, Any]:
    target_id, sha = view_attr_ops.set_view_attribute(
        target,
        view_kind,
        attribute,
        body.value,
        root=root,
    )
    return {"target_id": target_id, "commit_sha": sha}


@router.get("/{view_kind}/attributes/{attribute}")
def get_view_attributes(
    view_kind: str,
    attribute: str,
    root: Root,
) -> dict[str, Any]:
    store = view_attr_ops.get_view_attributes(view_kind, attribute, root=root)
    return store.model_dump(mode="json")


