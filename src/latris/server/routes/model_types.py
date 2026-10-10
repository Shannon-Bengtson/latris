"""Model type registry and readiness endpoints."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from latris.operations.readiness import assess_all_readiness, assess_readiness
from latris.schema.model_types import get_model_type, list_model_types
from latris.server.deps import get_project_root

router = APIRouter(prefix="/api/model-types", tags=["model-types"])
Root = Annotated[Path, Depends(get_project_root)]


@router.get("")
def get_model_types(include_planned: bool = True) -> list[dict[str, Any]]:
    specs = list_model_types(include_planned=include_planned)
    return [asdict(s) for s in specs]


@router.get("/readiness")
def all_readiness(root: Root) -> list[dict[str, Any]]:
    results = assess_all_readiness(root=root, include_planned=True)
    return [asdict(r) for r in results]


@router.get("/{type_id}")
def get_model_type_detail(type_id: str) -> dict[str, Any]:
    spec = get_model_type(type_id)
    return asdict(spec)


@router.get("/{type_id}/readiness")
def model_type_readiness(type_id: str, root: Root) -> dict[str, Any]:
    result = assess_readiness(type_id, root=root)
    return asdict(result)
