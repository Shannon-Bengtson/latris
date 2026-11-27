"""Decision tree routes — node types, branches, payoffs, uncertainties, settings, check, analysis.

Mirrors the `dt` CLI surface. Mutations return ``{"result": ..., "commit_sha": sha}``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from latris.operations import decision_tree as dt
from latris.schema.common import ProvenanceOrigin, ProvenanceVerification
from latris.server.deps import Root
from latris.server.routes import _formalism
from latris.server.routes._formalism import ProvenanceFields

router = APIRouter(prefix="/api/dt", tags=["decision-tree"])

# Where each route sits in the workflow (schema/workflow.py; rules in docs/engineering/WORKFLOW_STRUCTURE.md).
PLACE = {
    "tree": "formalise",
    "set_element": "formalise.definitions",
    "set_branch": "formalise.values",
    "set_payoff": "formalise.values",
    "set_uncertainty": "formalise.definitions",
    "set_settings": "formalise.definitions",
}


class ElementRequest(BaseModel):
    node: str
    element: str


class BranchRequest(BaseModel):
    """Only the fields sent change."""

    link: str
    label: str | None = None
    probability: float | None = None
    value: float | None = None
    notes: str | None = None
    origin: ProvenanceOrigin | None = None
    source_id: str | None = None
    verification: ProvenanceVerification | None = None


class PayoffRequest(ProvenanceFields):
    node: str
    value: float


class UncertaintyRequest(BaseModel):
    node: str
    uncertainty: str


class SettingsRequest(BaseModel):
    objective: str | None = None
    units: str | None = None




@router.get("/tree")
def tree(root: Root) -> dict[str, Any]:
    """Everything the tree is made of: node elements, branches (by edge id), payoffs, chance names, settings."""
    return {
        "elements": dt.get_elements(root=root),
        "branches": dt.get_branches(root=root).model_dump(mode="json")["entries"],
        "payoffs": dt.get_payoffs(root=root).model_dump(mode="json")["entries"],
        "chances": dt.get_chances(root=root).model_dump(mode="json")["entries"],
        "settings": dt.get_settings(root=root).model_dump(mode="json"),
    }


@router.post("/element")
def set_element(body: ElementRequest, root: Root) -> dict[str, Any]:
    target_id, sha = dt.set_element(body.node, body.element, root=root)
    return {"result": {"target_id": target_id, "element": body.element}, "commit_sha": sha}


@router.post("/branch")
def set_branch(body: BranchRequest, root: Root) -> dict[str, Any]:
    entry, sha = dt.set_branch(body.link, root=root, **body.model_dump(exclude={"link"}, exclude_unset=True))
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


@router.post("/payoff")
def set_payoff(body: PayoffRequest, root: Root) -> dict[str, Any]:
    entry, sha = dt.set_payoff(body.node, body.value, **body.provenance(), root=root)
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


@router.post("/uncertainty")
def set_uncertainty(body: UncertaintyRequest, root: Root) -> dict[str, Any]:
    entry, sha = dt.set_uncertainty(body.node, body.uncertainty, root=root)
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


@router.post("/settings")
def set_settings(body: SettingsRequest, root: Root) -> dict[str, Any]:
    s, sha = dt.set_settings(objective=body.objective, units=body.units, root=root)
    return {"result": s.model_dump(mode="json"), "commit_sha": sha}


_formalism.add_check_route(router, "decision_tree")
_formalism.add_analyse_route(router, dt, model_type="decision_tree")


from latris.server.routes import _psa  # noqa: E402

_psa.add_routes(router, "decision_tree")
