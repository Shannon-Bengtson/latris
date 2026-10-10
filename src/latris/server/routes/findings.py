"""Findings routes — list, show, record, advance maturity, staleness."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from latris.operations.findings import (
    check_staleness,
    get_finding,
    list_findings,
    record_new_finding,
    set_finding_maturity,
)
from latris.schema import HumanActor, Maturity
from latris.schema.common import ProvenanceOrigin
from latris.schema.findings import FindingCategory, FindingSourceType
from latris.server.deps import get_project_root

router = APIRouter(prefix="/api/findings", tags=["findings"])
Root = Annotated[Path, Depends(get_project_root)]


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
@router.get("/check/stale")
def check_stale_route(root: Root) -> dict[str, Any]:
    """Check all active (proposed or reviewed) findings for staleness."""
    active = list_findings(maturity="proposed", root=root) + list_findings(maturity="reviewed", root=root)
    stale_findings = [f for f in active if check_staleness(f, root=root)]
    return {
        "stale_findings": [f.model_dump(mode="json") for f in stale_findings],
        "total_active": len(active),
        "stale_count": len(stale_findings),
    }


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
