"""Bow-tie routes — elements, barriers, threat frequencies, check and analysis.

Mirrors the `bowtie` CLI surface. Mutations return ``{"result": ..., "commit_sha":
sha}``; reads return plain data.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from latris.operations import bow_tie as bt
from latris.schema.common import ProvenanceOrigin, ProvenanceVerification
from latris.server.deps import Root
from latris.server.routes import _formalism
from latris.server.routes._formalism import ProvenanceFields

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


class FrequencyRequest(ProvenanceFields):
    node: str
    frequency: float



@router.get("/elements")
def elements(root: Root) -> dict[str, Any]:
    return {
        "elements": bt.get_elements(root=root),
        "barriers": bt.get_barriers(root=root).model_dump(mode="json")["entries"],
        "frequencies": bt.get_frequencies(root=root).model_dump(mode="json")["entries"],
    }


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
    entry, sha = bt.set_frequency(body.node, body.frequency, **body.provenance(), root=root)
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


from latris.server.routes import _risk_mc  # noqa: E402

_risk_mc.add_routes(router, "bow_tie")


_formalism.add_check_route(router, "bow_tie")
_formalism.add_analyse_route(router, bt)
