"""HTTP routes for AI interrogation Phase 2c CompletenessGate.

Endpoints:
- GET ``/api/completeness/{model_type}`` — return the current report.
- POST ``/api/completeness/{model_type}/check`` — run the gate.
- POST ``/api/completeness/{model_type}/{missing_var_id}/override`` —
  override with a rationale; creates an Exclusion + flips disposition.
- POST ``/api/completeness/{model_type}/{missing_var_id}/dismiss``.
- POST ``/api/completeness/{model_type}/{missing_var_id}/mark-added``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from latris.server.deps import get_project_root

router = APIRouter(prefix="/api/completeness", tags=["completeness"])
Root = Annotated[Path, Depends(get_project_root)]


class CheckBody(BaseModel):
    claims: list[str] = []


class OverrideBody(BaseModel):
    rationale: str


class MarkAddedBody(BaseModel):
    entity_id: str


@router.get("/{model_type}")
def get_report(model_type: str, root: Root) -> dict[str, Any]:
    from latris.operations.completeness import load_report

    report = load_report(model_type, root=root)
    return {"result": report.model_dump(mode="json")}


@router.post("/{model_type}/check")
def check(model_type: str, body: CheckBody, root: Root) -> dict[str, Any]:
    from latris.operations.completeness import run_completeness_gate

    report, _sha = run_completeness_gate(
        model_type, claims=body.claims, root=root
    )
    return {"result": report.model_dump(mode="json")}


@router.post("/{model_type}/{missing_var_id}/override")
def override(
    model_type: str, missing_var_id: str, body: OverrideBody, root: Root
) -> dict[str, Any]:
    from latris.operations.completeness import override_missing_variable

    try:
        mv, sha = override_missing_variable(
            model_type, missing_var_id, body.rationale, root=root
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"result": mv.model_dump(mode="json"), "commit_sha": sha}


@router.post("/{model_type}/{missing_var_id}/dismiss")
def dismiss(model_type: str, missing_var_id: str, root: Root) -> dict[str, Any]:
    from latris.operations.completeness import dismiss_missing_variable

    try:
        mv, sha = dismiss_missing_variable(model_type, missing_var_id, root=root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"result": mv.model_dump(mode="json"), "commit_sha": sha}


@router.post("/{model_type}/{missing_var_id}/mark-added")
def mark_added(
    model_type: str, missing_var_id: str, body: MarkAddedBody, root: Root
) -> dict[str, Any]:
    from latris.operations.completeness import mark_added_to_model

    try:
        mv, sha = mark_added_to_model(
            model_type, missing_var_id, body.entity_id, root=root
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"result": mv.model_dump(mode="json"), "commit_sha": sha}
