"""View-specific attribute endpoints (e.g. CLD polarity)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from latris.operations import view_attributes as view_attr_ops
from latris.server.deps import Root

router = APIRouter(prefix="/api/views", tags=["view-attributes"])

# Where each route sits in the workflow (schema/workflow.py; rules in docs/engineering/WORKFLOW_STRUCTURE.md).
PLACE = "build.structure"


class SetViewAttributeRequest(BaseModel):
    value: str
    # The reason for the value (a polarity's causal story). Omitted: the stored reason is kept. Blank: removed.
    rationale: str | None = None


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
        rationale=body.rationale,
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


