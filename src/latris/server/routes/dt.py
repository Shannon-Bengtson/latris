"""Decision tree routes — node types, branches, payoffs, uncertainties, settings, check, analysis.

Mirrors the `dt` CLI surface. Mutations return ``{"result": ..., "commit_sha": sha}``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from latris.operations import decision_tree as dt
from latris.operations.readiness import assess_readiness
from latris.schema.common import ProvenanceOrigin, ProvenanceVerification
from latris.server.deps import get_project_root

router = APIRouter(prefix="/api/dt", tags=["decision-tree"])
Root = Annotated[Path, Depends(get_project_root)]


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


class PayoffRequest(BaseModel):
    node: str
    value: float
    origin: ProvenanceOrigin = "human-direct"
    source_id: str | None = None
    verification: ProvenanceVerification = "unverified"
    notes: str | None = None


class UncertaintyRequest(BaseModel):
    node: str
    uncertainty: str


class SettingsRequest(BaseModel):
    objective: str | None = None
    units: str | None = None


class AnalyseRequest(BaseModel):
    record: bool = True


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except (ValueError, LookupError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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


@router.get("/check")
def check(root: Root) -> dict[str, Any]:
    r = assess_readiness("decision_tree", root=root)
    return {"ready": r.can_switch, "gaps": [{"element_id": g.element_id, "element_label": g.element_label,
                                             "gap_type": g.gap_type, "message": g.message} for g in r.gaps]}


@router.post("/element")
def set_element(body: ElementRequest, root: Root) -> dict[str, Any]:
    target_id, sha = _call(dt.set_element, body.node, body.element, root=root)
    return {"result": {"target_id": target_id, "element": body.element}, "commit_sha": sha}


@router.post("/branch")
def set_branch(body: BranchRequest, root: Root) -> dict[str, Any]:
    entry, sha = _call(dt.set_branch, body.link, root=root, **body.model_dump(exclude={"link"}, exclude_unset=True))
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


@router.post("/payoff")
def set_payoff(body: PayoffRequest, root: Root) -> dict[str, Any]:
    entry, sha = _call(dt.set_payoff, body.node, body.value, origin=body.origin, source_id=body.source_id,
                       verification=body.verification, notes=body.notes, root=root)
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


@router.post("/uncertainty")
def set_uncertainty(body: UncertaintyRequest, root: Root) -> dict[str, Any]:
    entry, sha = _call(dt.set_uncertainty, body.node, body.uncertainty, root=root)
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


@router.post("/settings")
def set_settings(body: SettingsRequest, root: Root) -> dict[str, Any]:
    s, sha = _call(dt.set_settings, objective=body.objective, units=body.units, root=root)
    return {"result": s.model_dump(mode="json"), "commit_sha": sha}


@router.post("/analyse")
def analyse(root: Root, body: AnalyseRequest | None = None) -> dict[str, Any]:
    body = body or AnalyseRequest()
    payload = dt.analyse(root=root)
    sha = None
    if body.record and not payload["problems"]:
        sha, payload["run_id"] = dt.record(payload, root=root)
    return {"result": payload, "commit_sha": sha}
