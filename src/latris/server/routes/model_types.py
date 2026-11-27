"""Model type registry and readiness endpoints."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel

from latris.operations.readiness import assess_all_readiness, assess_readiness
from latris.schema.model_types import MODEL_FAMILIES, get_model_type, list_model_types
from latris.server.deps import Root

router = APIRouter(prefix="/api/model-types", tags=["model-types"])

# Where each route sits in the workflow (schema/workflow.py; rules in docs/engineering/WORKFLOW_STRUCTURE.md).
PLACE = {
    "*": "frame.model_type",
    "model_type_elements": "formalise.definitions",
    "all_readiness": "validation",
    "model_type_readiness": "validation",
}


class ModelTypeInfo(BaseModel):
    """How a surface presents a model type to someone choosing one (``ModelTypeSpec``'s presentation and
    gating fields): the app's model picker reads only this, never a list of its own."""

    id: str
    display_name: str
    short_name: str
    description: str
    summary: str
    answers: str
    best_for: str
    key_features: list[str]
    availability: Literal["stable", "planned"]
    roadmap: Literal["built", "roadmap", "parked", "not_planned"]
    family: str


class ModelFamilyInfo(BaseModel):
    id: str
    label: str
    description: str


@router.get("", response_model=list[ModelTypeInfo])
def get_model_types(include_planned: bool = True) -> list[dict[str, Any]]:
    """Every model type, in registry order (planned ones too unless ``include_planned`` is false)."""
    specs = list_model_types(include_planned=include_planned)
    return [asdict(s) for s in specs]


@router.get("/families", response_model=list[ModelFamilyInfo])
def get_model_families() -> list[dict[str, Any]]:
    """The groups a picker shows model types in, in order (each type's ``family`` names one)."""
    return [asdict(f) for f in MODEL_FAMILIES]


@router.get("/readiness")
def all_readiness(root: Root) -> list[dict[str, Any]]:
    results = assess_all_readiness(root=root, include_planned=True)
    return [asdict(r) for r in results]


@router.get("/{type_id}/elements")
def model_type_elements(type_id: str, root: Root) -> dict[str, Any]:
    """Each factor's role in this model type (an MCDA option, an event tree's heading…), and whether the type
    lives on links. The editor leaves link-free types' elements off the other types' canvases."""
    from latris.operations import formalisms
    from latris.repo.layout import ProjectPaths
    from latris.repo.yaml_io import load_model
    from latris.schema.roles import RoleSet

    path = ProjectPaths(root).role_path(type_id)
    roles = {r.target_id: r.value for r in load_model(RoleSet, path).entries} if path.exists() else {}
    f = formalisms.get(type_id)
    return {"elements": roles, "connected_structure": f.connected_structure if f else True}


@router.get("/{type_id}")
def get_model_type_detail(type_id: str) -> dict[str, Any]:
    spec = get_model_type(type_id)
    return asdict(spec)


@router.get("/{type_id}/readiness")
def model_type_readiness(type_id: str, root: Root) -> dict[str, Any]:
    result = assess_readiness(type_id, root=root)
    return asdict(result)
