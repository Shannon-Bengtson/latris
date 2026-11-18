"""Configure endpoints — batch-apply model-specific attributes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from latris.operations import configure as configure_ops
from latris.server.deps import Root

router = APIRouter(prefix="/api/configure", tags=["configure"])


# ---------------------------------------------------------------------------
# Request / response bodies
# ---------------------------------------------------------------------------


class AttributeEntryDef(BaseModel):
    target_id: str
    value: str
    origin: str = "human-direct"
    source_detail: str = ""


class ApplyAttributesRequest(BaseModel):
    model_type: str
    attribute: str
    entries: list[AttributeEntryDef]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/apply-attributes")
def apply_attributes(body: ApplyAttributesRequest, root: Root) -> dict[str, Any]:
    """Batch-apply model-specific attribute values in a single commit."""
    applied_ids, sha = configure_ops.batch_set_view_attributes(
        model_type=body.model_type,
        attribute=body.attribute,
        entries=[e.model_dump() for e in body.entries],
        root=root,
    )
    return {"applied_ids": applied_ids, "commit_sha": sha}
