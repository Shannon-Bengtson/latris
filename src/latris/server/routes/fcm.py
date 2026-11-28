"""Fuzzy cognitive map routes: a link's weight (a Formalise value, where CLD polarity is Build's structure)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from latris.operations import view_attributes as view_attr_ops
from latris.server.deps import Root

router = APIRouter(prefix="/api/fcm", tags=["fcm"])

# Where each route sits in the workflow (schema/workflow.py; rules in docs/engineering/WORKFLOW_STRUCTURE.md).
PLACE = "formalise.values"


class WeightRequest(BaseModel):
    link: str  # edge id, id prefix, or 'From -> To'
    weight: float = Field(ge=-1, le=1)


@router.post("/weight")
def set_weight(body: WeightRequest, root: Root) -> dict[str, Any]:
    """Set an FCM link's weight, from -1 to +1 (`latris fcm set-weight`)."""
    target_id, sha = view_attr_ops.set_view_attribute(body.link, "fcm", "weight", repr(body.weight), root=root)
    return {"result": {"target_id": target_id, "weight": body.weight}, "commit_sha": sha}
