"""Bow-tie routes — elements, barriers, threat frequencies, check and analysis.

Mirrors the `bowtie` CLI surface. Mutations return ``{"result": ..., "commit_sha":
sha}``; reads return plain data.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from latris.operations import bow_tie as bt
from latris.operations.readiness import assess_readiness
from latris.schema.common import ProvenanceOrigin, ProvenanceVerification
from latris.server.deps import Root

router = APIRouter(prefix="/api/bowtie", tags=["bowtie"])



class ElementRequest(BaseModel):
    node: str
    element: str


class BarrierRequest(BaseModel):
    """Only the fields sent change."""

    node: str
    barrier_type: str | None = None
    status: str | None = None
    owner: str | None = None
    pfd: float | None = None
    origin: ProvenanceOrigin | None = None
    source_id: str | None = None
    verification: ProvenanceVerification | None = None
    notes: str | None = None


class FrequencyRequest(BaseModel):
    node: str
    frequency: float
    origin: ProvenanceOrigin = "human-direct"
    source_id: str | None = None
    verification: ProvenanceVerification = "unverified"
    notes: str | None = None


class AnalyseRequest(BaseModel):
    record: bool = True


@router.get("/elements")
def elements(root: Root) -> dict[str, Any]:
    return {
        "elements": bt.get_elements(root=root),
        "barriers": bt.get_barriers(root=root).model_dump(mode="json")["entries"],
        "frequencies": bt.get_frequencies(root=root).model_dump(mode="json")["entries"],
    }


@router.get("/check")
def check(root: Root) -> dict[str, Any]:
    r = assess_readiness("bow_tie", root=root)
    return {"ready": r.can_switch, "gaps": [
        {"element_id": g.element_id, "element_label": g.element_label, "gap_type": g.gap_type, "message": g.message}
        for g in r.gaps
    ]}


@router.post("/element")
def set_element(body: ElementRequest, root: Root) -> dict[str, Any]:
    target_id, sha = bt.set_element(body.node, body.element, root=root)
    return {"result": {"target_id": target_id, "element": body.element}, "commit_sha": sha}


@router.post("/barrier")
def set_barrier(body: BarrierRequest, root: Root) -> dict[str, Any]:
    fields = body.model_dump(exclude={"node"}, exclude_unset=True)
    entry, sha = bt.set_barrier(body.node, root=root, **fields)
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


@router.post("/frequency")
def set_frequency(body: FrequencyRequest, root: Root) -> dict[str, Any]:
    entry, sha = bt.set_frequency(body.node, body.frequency, origin=body.origin, source_id=body.source_id,
                                  verification=body.verification, notes=body.notes, root=root)
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


@router.post("/analyse")
def analyse(root: Root, body: AnalyseRequest | None = None) -> dict[str, Any]:
    body = body or AnalyseRequest()
    payload = bt.analyse(root=root)
    sha = None
    if body.record and not payload["problems"]:
        sha, payload["run_id"] = bt.record(payload, root=root)
    return {"result": payload, "commit_sha": sha}


from latris.server.routes import _risk_mc  # noqa: E402

_risk_mc.add_routes(router, "bow_tie")
