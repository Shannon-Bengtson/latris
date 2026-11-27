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

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from latris.schema.completeness import CompletenessReport
from latris.server.deps import Root
from latris.server.routes._envelope import Result

router = APIRouter(prefix="/api/completeness", tags=["completeness"])

# Where each route sits in the workflow (schema/workflow.py; rules in docs/engineering/WORKFLOW_STRUCTURE.md).
PLACE = "ai"


class CheckBody(BaseModel):
    claims: list[str] = []


class OverrideBody(BaseModel):
    rationale: str


class MarkAddedBody(BaseModel):
    entity_id: str


@router.get("/{model_type}", response_model=Result[CompletenessReport])
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

    mv, sha = override_missing_variable(
        model_type, missing_var_id, body.rationale, root=root
    )
    return {"result": mv.model_dump(mode="json"), "commit_sha": sha}


@router.post("/{model_type}/{missing_var_id}/dismiss")
def dismiss(model_type: str, missing_var_id: str, root: Root) -> dict[str, Any]:
    from latris.operations.completeness import dismiss_missing_variable

    mv, sha = dismiss_missing_variable(model_type, missing_var_id, root=root)
    return {"result": mv.model_dump(mode="json"), "commit_sha": sha}


@router.post("/{model_type}/{missing_var_id}/mark-added")
def mark_added(
    model_type: str, missing_var_id: str, body: MarkAddedBody, root: Root
) -> dict[str, Any]:
    from latris.operations.completeness import mark_added_to_model

    mv, sha = mark_added_to_model(
        model_type, missing_var_id, body.entity_id, root=root
    )
    return {"result": mv.model_dump(mode="json"), "commit_sha": sha}
