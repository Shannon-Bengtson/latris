"""FCM routes — weights, inference, and scenario comparison."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from latris.operations import analysis as analysis_ops
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model
from latris.schema import FloatSet
from latris.schema.settings import FCMSettings
from latris.server.deps import get_project_root

router = APIRouter(prefix="/api/fcm", tags=["fcm"])
Root = Annotated[Path, Depends(get_project_root)]


@router.get("/weights")
def get_weights(root: Root) -> dict[str, Any]:
    """Return all FCM edge weights with provenance."""
    paths = ProjectPaths(root)
    weight_path = paths.view_attribute_path("fcm", "weight")
    store = load_model(FloatSet, weight_path) if weight_path.exists() else FloatSet()
    return {
        "weights": [
            {
                "target_id": e.target_id,
                "value": e.value,
                "origin": e.origin,
                "verification": e.verification,
            }
            for e in store.entries
        ],
        "count": len(store.entries),
    }


class InferRequest(BaseModel):
    initial_activations: dict[str, float] | None = None
    clamped: dict[str, float] | None = None
    lambda_steepness: float | None = None
    transfer_function: str | None = None
    max_iterations: int | None = None


@router.post("/infer")
def infer(root: Root, body: InferRequest | None = None) -> dict[str, Any]:
    """Run FCM inference to steady state."""
    # Build settings from request overrides
    settings_kwargs: dict[str, Any] = {}
    if body:
        if body.lambda_steepness is not None:
            settings_kwargs["lambda_steepness"] = body.lambda_steepness
        if body.transfer_function is not None:
            settings_kwargs["transfer_function"] = body.transfer_function
        if body.max_iterations is not None:
            settings_kwargs["max_iterations"] = body.max_iterations
    settings = FCMSettings(**settings_kwargs) if settings_kwargs else None

    result = analysis_ops.infer_fcm(
        root,
        initial_activations=body.initial_activations if body else None,
        clamped=body.clamped if body else None,
        settings=settings,
    )

    return {
        "activations": result.activations,
        "converged": result.converged,
        "iterations": result.iterations,
    }
