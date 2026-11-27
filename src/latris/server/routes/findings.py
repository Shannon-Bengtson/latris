"""Findings routes — list, show, record, edit, remove, advance maturity, staleness."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from latris.operations.findings import (
    check_staleness,
    edit_finding,
    get_finding,
    list_findings,
    record_new_finding,
    remove_finding,
    set_finding_maturity,
)
from latris.schema import HumanActor, Maturity
from latris.schema.common import ProvenanceOrigin
from latris.schema.findings import FindingCategory, FindingSourceType
from latris.server.deps import Root

router = APIRouter(prefix="/api/findings", tags=["findings"])

# Where each route sits in the workflow (schema/workflow.py; rules in docs/engineering/WORKFLOW_STRUCTURE.md).
PLACE = {
    "*": "interpret.findings",
    "update_maturity_route": "review",
}


class RecordFindingRequest(BaseModel):
    statement: str
    category: FindingCategory
    model_type: str
    detail: str = ""
    payload: dict = Field(default_factory=dict)
    origin: ProvenanceOrigin = "human-direct"
    source_id: str | None = None
    source_type: FindingSourceType = "human-direct"
    target_ids: list[str] = Field(default_factory=list)
    related_attributes: list[str] = Field(default_factory=list)


class EditFindingRequest(BaseModel):
    """What to change; a field left out stays as it is."""

    statement: str | None = None
    detail: str | None = None
    category: FindingCategory | None = None


class MaturityUpdateRequest(BaseModel):
    maturity: Maturity
    reviewer_name: str
    reviewer_email: str | None = None


@router.get("")
def list_findings_route(
    root: Root,
    category: FindingCategory | None = None,
    model_type: str | None = None,
    maturity: Maturity | None = None,
    target_id: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """List findings with optional filters, newest first."""
    results = list_findings(
        category=category,
        model_type=model_type,
        maturity=maturity,
        target_id=target_id,
        limit=limit,
        root=root,
    )
    return {
        "findings": [f.model_dump(mode="json") for f in results],
        "count": len(results),
    }


# Static paths before dynamic /{finding_id} to avoid route conflicts.
@router.get("/{finding_id}")
def get_finding_route(finding_id: str, root: Root) -> dict[str, Any]:
    """Retrieve a single finding by ID or prefix."""
    f = get_finding(finding_id, root=root)
    stale = check_staleness(f, root=root)
    return {
        "finding": f.model_dump(mode="json"),
        "stale": stale,
    }


@router.post("")
def record_finding_route(body: RecordFindingRequest, root: Root) -> dict[str, Any]:
    """Record a new finding."""
    finding, sha = record_new_finding(
        body.statement,
        body.category,
        body.model_type,
        detail=body.detail,
        payload=body.payload,
        origin=body.origin,
        source_id=body.source_id,
        source_type=body.source_type,
        target_ids=body.target_ids,
        related_attributes=body.related_attributes,
        root=root,
    )
    return {
        "finding": finding.model_dump(mode="json"),
        "commit_sha": sha,
    }


@router.patch("/{finding_id}/maturity")
def update_maturity_route(
    finding_id: str,
    body: MaturityUpdateRequest,
    root: Root,
) -> dict[str, Any]:
    """Update a finding's maturity (proposed → reviewed → approved)."""
    reviewer = HumanActor(name=body.reviewer_name, email=body.reviewer_email)
    updated, sha = set_finding_maturity(
        finding_id,
        maturity=body.maturity,
        reviewed_by=reviewer,
        root=root,
    )
    return {
        "finding": updated.model_dump(mode="json"),
        "commit_sha": sha,
    }


@router.patch("/{finding_id}")
def edit_finding_route(finding_id: str, body: EditFindingRequest, root: Root) -> dict[str, Any]:
    """Change what a finding says (a reviewed or approved one goes back to proposed)."""
    updated, sha = edit_finding(
        finding_id, statement=body.statement, detail=body.detail, category=body.category, root=root
    )
    return {"finding": updated.model_dump(mode="json"), "commit_sha": sha}


@router.delete("/{finding_id}")
def remove_finding_route(finding_id: str, root: Root) -> dict[str, Any]:
    """Remove a finding."""
    removed, sha = remove_finding(finding_id, root=root)
    return {"finding": removed.model_dump(mode="json"), "commit_sha": sha}
