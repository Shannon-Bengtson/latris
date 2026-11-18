"""MCDA routes — options, criteria, scores, check and analysis.

Mirrors the `mcda` CLI surface. Mutations return ``{"result": ..., "commit_sha": sha}``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from latris.operations import mcda
from latris.operations.readiness import assess_readiness
from latris.schema.common import ProvenanceOrigin, ProvenanceVerification
from latris.server.deps import Root

router = APIRouter(prefix="/api/mcda", tags=["mcda"])


class ElementRequest(BaseModel):
    node: str
    element: str


class CriterionRequest(BaseModel):
    """Only the fields sent change."""

    node: str
    weight: float | None = None
    direction: str | None = None
    worst: float | None = None
    best: float | None = None
    units: str | None = None
    notes: str | None = None
    origin: ProvenanceOrigin | None = None
    source_id: str | None = None
    verification: ProvenanceVerification | None = None


class ScoreRequest(BaseModel):
    option: str
    criterion: str
    value: float
    origin: ProvenanceOrigin = "human-direct"
    source_id: str | None = None
    verification: ProvenanceVerification = "unverified"
    notes: str | None = None


class AnalyseRequest(BaseModel):
    record: bool = True


def _call(fn, *args, **kwargs):
    return fn(*args, **kwargs)


@router.get("/model")
def model(root: Root) -> dict[str, Any]:
    return {"elements": mcda.get_elements(root=root),
            "criteria": mcda.get_criteria(root=root).model_dump(mode="json")["entries"],
            "scores": mcda.get_scores(root=root).model_dump(mode="json")["entries"]}


@router.get("/check")
def check(root: Root) -> dict[str, Any]:
    r = assess_readiness("mcda", root=root)
    return {"ready": r.can_switch, "gaps": [{"element_id": g.element_id, "element_label": g.element_label,
                                             "gap_type": g.gap_type, "message": g.message} for g in r.gaps]}


@router.post("/element")
def set_element(body: ElementRequest, root: Root) -> dict[str, Any]:
    target_id, sha = _call(mcda.set_element, body.node, body.element, root=root)
    return {"result": {"target_id": target_id, "element": body.element}, "commit_sha": sha}


@router.post("/criterion")
def set_criterion(body: CriterionRequest, root: Root) -> dict[str, Any]:
    entry, sha = _call(mcda.set_criterion, body.node, root=root,
                       **body.model_dump(exclude={"node"}, exclude_unset=True))
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


@router.post("/score")
def set_score(body: ScoreRequest, root: Root) -> dict[str, Any]:
    entry, sha = _call(mcda.set_score, body.option, body.criterion, body.value, origin=body.origin,
                       source_id=body.source_id, verification=body.verification, notes=body.notes, root=root)
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


@router.post("/analyse")
def analyse(root: Root, body: AnalyseRequest | None = None) -> dict[str, Any]:
    body = body or AnalyseRequest()
    payload = mcda.analyse(root=root)
    sha = None
    if body.record and not payload["problems"]:
        sha, payload["run_id"] = mcda.record(payload, root=root)
    return {"result": payload, "commit_sha": sha}
