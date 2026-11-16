"""Fault tree routes — event types, gates, probabilities, check and analysis.

Mirrors the `ft` CLI surface. Mutations return ``{"result": ..., "commit_sha":
sha}``; reads return plain data.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ValidationError

from latris.operations import fault_tree as ft
from latris.operations.readiness import assess_readiness
from latris.schema.common import ProvenanceOrigin, ProvenanceVerification
from latris.server.deps import get_project_root

router = APIRouter(prefix="/api/ft", tags=["ft"])
Root = Annotated[Path, Depends(get_project_root)]


def _bad(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


class EventRequest(BaseModel):
    node: str
    event_type: str


class GateRequest(BaseModel):
    node: str
    gate: str
    k: int | None = None


class ProbabilityRequest(BaseModel):
    node: str
    probability: float
    origin: ProvenanceOrigin = "human-direct"
    source_id: str | None = None
    verification: ProvenanceVerification = "unverified"
    notes: str | None = None


class AnalyseRequest(BaseModel):
    max_order: int | None = None
    record: bool = True


@router.get("/tree")
def get_tree(root: Root) -> dict[str, Any]:
    tree = ft.load_tree(root=root)
    return {
        "top": tree.top,
        "events": tree.events,
        "inputs": tree.inputs,
        "gates": ft.get_gates(root=root).model_dump(mode="json")["entries"],
        "probabilities": ft.get_probabilities(root=root).model_dump(mode="json")["entries"],
        "problems": [{"target_id": p.target_id, "gap_type": p.gap_type, "message": p.message} for p in tree.problems],
    }


@router.get("/check")
def check(root: Root) -> dict[str, Any]:
    r = assess_readiness("fault_tree", root=root)
    return {"ready": r.can_switch, "gaps": [
        {"element_id": g.element_id, "element_label": g.element_label, "gap_type": g.gap_type, "message": g.message}
        for g in r.gaps
    ]}


@router.post("/event")
def set_event(body: EventRequest, root: Root) -> dict[str, Any]:
    try:
        target_id, sha = ft.set_event(body.node, body.event_type, root=root)
    except (ValueError, LookupError) as exc:
        raise _bad(exc) from exc
    return {"result": {"target_id": target_id, "event_type": body.event_type}, "commit_sha": sha}


@router.post("/gate")
def set_gate(body: GateRequest, root: Root) -> dict[str, Any]:
    try:
        entry, sha = ft.set_gate(body.node, body.gate, k=body.k, root=root)
    except (ValueError, LookupError, ValidationError) as exc:
        raise _bad(exc) from exc
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


@router.post("/probability")
def set_probability(body: ProbabilityRequest, root: Root) -> dict[str, Any]:
    try:
        entry, sha = ft.set_probability(
            body.node, body.probability, origin=body.origin, source_id=body.source_id,
            verification=body.verification, notes=body.notes, root=root,
        )
    except (ValueError, LookupError, ValidationError) as exc:
        raise _bad(exc) from exc
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


@router.post("/analyse")
def analyse(root: Root, body: AnalyseRequest | None = None) -> dict[str, Any]:
    body = body or AnalyseRequest()
    payload = ft.analyse(max_order=body.max_order, root=root)
    sha = None
    if body.record and not payload["problems"] and not payload["error"]:
        sha, payload["run_id"] = ft.record(payload, root=root)
    return {"result": payload, "commit_sha": sha}


from latris.server.routes import _risk_mc  # noqa: E402

_risk_mc.add_routes(router, "fault_tree")
