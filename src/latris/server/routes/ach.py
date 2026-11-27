"""ACH routes — hypotheses, evidence items, ratings, check and analysis.

Mirrors the `ach` CLI surface. Mutations return ``{"result": ..., "commit_sha": sha}``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from latris.operations import ach
from latris.schema.common import ProvenanceOrigin, ProvenanceVerification
from latris.server.deps import Root
from latris.server.routes import _formalism

router = APIRouter(prefix="/api/ach", tags=["ach"])

# Where each route sits in the workflow (schema/workflow.py; rules in docs/engineering/WORKFLOW_STRUCTURE.md).
PLACE = {
    "matrix": "formalise",
    "set_element": "formalise.definitions",
    "set_item": "formalise.definitions",
    "set_rating": "formalise.values",
}


class ElementRequest(BaseModel):
    node: str
    element: str


class ItemRequest(BaseModel):
    """Only the fields sent change."""

    node: str
    credibility: str | None = None
    relevance: str | None = None
    notes: str | None = None


class RatingRequest(BaseModel):
    item: str
    hypothesis: str
    rating: str
    rationale: str | None = None
    origin: ProvenanceOrigin = "human-direct"
    verification: ProvenanceVerification = "unverified"




@router.get("/matrix")
def matrix(root: Root) -> dict[str, Any]:
    return {"elements": ach.get_elements(root=root),
            "items": ach.get_items(root=root).model_dump(mode="json")["entries"],
            "ratings": ach.get_ratings(root=root).model_dump(mode="json")["entries"]}


@router.post("/element")
def set_element(body: ElementRequest, root: Root) -> dict[str, Any]:
    target_id, sha = ach.set_element(body.node, body.element, root=root)
    return {"result": {"target_id": target_id, "element": body.element}, "commit_sha": sha}


@router.post("/item")
def set_item(body: ItemRequest, root: Root) -> dict[str, Any]:
    entry, sha = ach.set_item(body.node, root=root, **body.model_dump(exclude={"node"}, exclude_unset=True))
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


@router.post("/rating")
def set_rating(body: RatingRequest, root: Root) -> dict[str, Any]:
    entry, sha = ach.set_rating(body.item, body.hypothesis, body.rating, rationale=body.rationale,
                       origin=body.origin, verification=body.verification, root=root)
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


_formalism.add_check_route(router, "ach")
_formalism.add_analyse_route(router, ach, model_type="ach")
