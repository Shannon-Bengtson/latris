"""Fault tree routes — event types, gates, probabilities, check and analysis.

Mirrors the `ft` CLI surface. Mutations return ``{"result": ..., "commit_sha":
sha}``; reads return plain data.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from latris.operations import fault_tree as ft
from latris.server.deps import Root
from latris.server.routes import _formalism
from latris.server.routes._formalism import ProvenanceFields

router = APIRouter(prefix="/api/ft", tags=["ft"])



class EventRequest(BaseModel):
    node: str
    event_type: str


class GateRequest(BaseModel):
    node: str
    gate: str
    k: int | None = None


class ProbabilityRequest(ProvenanceFields):
    node: str
    probability: float


class AnalyseRequest(_formalism.AnalyseRequest):
    max_order: int | None = None


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


@router.post("/event")
def set_event(body: EventRequest, root: Root) -> dict[str, Any]:
    target_id, sha = ft.set_event(body.node, body.event_type, root=root)
    return {"result": {"target_id": target_id, "event_type": body.event_type}, "commit_sha": sha}


@router.post("/gate")
def set_gate(body: GateRequest, root: Root) -> dict[str, Any]:
    entry, sha = ft.set_gate(body.node, body.gate, k=body.k, root=root)
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


@router.post("/probability")
def set_probability(body: ProbabilityRequest, root: Root) -> dict[str, Any]:
    entry, sha = ft.set_probability(
        body.node, body.probability, **body.provenance(), root=root,
    )
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


from latris.server.routes import _risk_mc  # noqa: E402

_risk_mc.add_routes(router, "fault_tree")


_formalism.add_check_route(router, "fault_tree")
_formalism.add_analyse_route(
    router, ft, request=AnalyseRequest, options=lambda b: {"max_order": b.max_order},
    recordable=lambda p: not p["problems"] and not p["error"],
)
