"""MCDA routes — options, criteria, scores, check and analysis.

Mirrors the `mcda` CLI surface. Mutations return ``{"result": ..., "commit_sha": sha}``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from latris.operations import mcda
from latris.schema.common import ProvenanceOrigin, ProvenanceVerification
from latris.server.deps import Root
from latris.server.routes import _formalism
from latris.server.routes._formalism import ProvenanceFields

router = APIRouter(prefix="/api/mcda", tags=["mcda"])

# Where each route sits in the workflow (schema/workflow.py; rules in docs/engineering/WORKFLOW_STRUCTURE.md).
PLACE = {
    "model": "formalise",
    "set_element": "formalise.definitions",
    "set_criterion": "formalise.values",
    "set_score": "formalise.values",
}


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


class ScoreRequest(ProvenanceFields):
    option: str
    criterion: str
    value: float




@router.get("/model")
def model(root: Root) -> dict[str, Any]:
    return {"elements": mcda.get_elements(root=root),
            "criteria": mcda.get_criteria(root=root).model_dump(mode="json")["entries"],
            "scores": mcda.get_scores(root=root).model_dump(mode="json")["entries"]}


@router.post("/element")
def set_element(body: ElementRequest, root: Root) -> dict[str, Any]:
    target_id, sha = mcda.set_element(body.node, body.element, root=root)
    return {"result": {"target_id": target_id, "element": body.element}, "commit_sha": sha}


@router.post("/criterion")
def set_criterion(body: CriterionRequest, root: Root) -> dict[str, Any]:
    entry, sha = mcda.set_criterion(body.node, root=root,
                       **body.model_dump(exclude={"node"}, exclude_unset=True))
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


@router.post("/score")
def set_score(body: ScoreRequest, root: Root) -> dict[str, Any]:
    entry, sha = mcda.set_score(body.option, body.criterion, body.value, **body.provenance(), root=root)
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


_formalism.add_check_route(router, "mcda")
_formalism.add_analyse_route(router, mcda, model_type="mcda")
