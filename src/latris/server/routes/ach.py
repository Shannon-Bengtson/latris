"""ACH routes — hypotheses, evidence items, ratings, check and analysis.

Mirrors the `ach` CLI surface. Mutations return ``{"result": ..., "commit_sha": sha}``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from latris.operations import ach
from latris.operations.readiness import assess_readiness
from latris.schema.common import ProvenanceOrigin, ProvenanceVerification
from latris.server.deps import Root

router = APIRouter(prefix="/api/ach", tags=["ach"])


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


class AnalyseRequest(BaseModel):
    record: bool = True


def _call(fn, *args, **kwargs):
    return fn(*args, **kwargs)


@router.get("/matrix")
def matrix(root: Root) -> dict[str, Any]:
    return {"elements": ach.get_elements(root=root),
            "items": ach.get_items(root=root).model_dump(mode="json")["entries"],
            "ratings": ach.get_ratings(root=root).model_dump(mode="json")["entries"]}


@router.get("/check")
def check(root: Root) -> dict[str, Any]:
    r = assess_readiness("ach", root=root)
    return {"ready": r.can_switch, "gaps": [{"element_id": g.element_id, "element_label": g.element_label,
                                             "gap_type": g.gap_type, "message": g.message} for g in r.gaps]}


@router.post("/element")
def set_element(body: ElementRequest, root: Root) -> dict[str, Any]:
    target_id, sha = _call(ach.set_element, body.node, body.element, root=root)
    return {"result": {"target_id": target_id, "element": body.element}, "commit_sha": sha}


@router.post("/item")
def set_item(body: ItemRequest, root: Root) -> dict[str, Any]:
    entry, sha = _call(ach.set_item, body.node, root=root, **body.model_dump(exclude={"node"}, exclude_unset=True))
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


@router.post("/rating")
def set_rating(body: RatingRequest, root: Root) -> dict[str, Any]:
    entry, sha = _call(ach.set_rating, body.item, body.hypothesis, body.rating, rationale=body.rationale,
                       origin=body.origin, verification=body.verification, root=root)
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


@router.post("/analyse")
def analyse(root: Root, body: AnalyseRequest | None = None) -> dict[str, Any]:
    body = body or AnalyseRequest()
    payload = ach.analyse(root=root)
    sha = None
    if body.record and not payload["problems"]:
        sha, payload["run_id"] = ach.record(payload, root=root)
    return {"result": payload, "commit_sha": sha}
