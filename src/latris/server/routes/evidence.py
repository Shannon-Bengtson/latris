"""Evidence link endpoints."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel

from latris.operations.evidence import (
    add_data_link,
    add_evidence,
    remove_data_link,
    remove_evidence,
    set_evidence_support_verdict,
)
from latris.schema.common import SupportVerdict
from latris.server.deps import Root

router = APIRouter(prefix="/api/evidence", tags=["evidence"])

# Where each route sits in the workflow (schema/workflow.py; rules in docs/engineering/WORKFLOW_STRUCTURE.md).
PLACE = "evidence"


class AddEvidenceRequest(BaseModel):
    target: str | None = None
    attribute: str = "description"
    bibkey: str
    verified_by: Literal["human", "ai"] = "human"
    notes: str | None = None
    contradicts: bool = False


@router.post("", status_code=201)
def attach_evidence(body: AddEvidenceRequest, root: Root) -> dict[str, Any]:
    link, sha = add_evidence(
        body.target,
        body.attribute,
        body.bibkey,
        verified_by=body.verified_by,
        notes=body.notes,
        contradicts=body.contradicts,
        root=root,
    )
    return {"result": link.model_dump(mode="json"), "commit_sha": sha}


class AddDataLinkRequest(BaseModel):
    target: str | None = None
    dataset_id: str
    column_names: list[str] = []
    statistic: str | None = None
    value: str | None = None
    rationale: str | None = None
    notes: str | None = None


@router.post("/data-links", status_code=201)
def attach_data_link(body: AddDataLinkRequest, root: Root) -> dict[str, Any]:
    link, sha = add_data_link(
        body.target,
        body.dataset_id,
        column_names=body.column_names,
        statistic=body.statistic,
        value=body.value,
        rationale=body.rationale,
        notes=body.notes,
        root=root,
    )
    return {"result": link.model_dump(mode="json"), "commit_sha": sha}


class CitationRef(BaseModel):
    """One citation: the source ``bibkey`` cited for ``attribute`` of ``target`` (a factor or link)."""

    target: str | None = None
    attribute: str = "description"
    bibkey: str


class CheckCitationRequest(CitationRef):
    verdict: SupportVerdict
    rationale: str  # what the source says, in a sentence
    quote: str | None = None  # a passage copied from the source; looked up in the text latris holds


@router.post("/check")
def check_citation(body: CheckCitationRequest, root: Root) -> dict[str, Any]:
    """A person read the source: record whether it supports the claim it's cited for, argues against it, is
    off topic, or the text seen was too short to tell (``unverified`` sets it back to unchecked)."""
    link, sha = set_evidence_support_verdict(
        body.target, body.attribute, body.bibkey, new_verdict=body.verdict, rationale=body.rationale,
        quote=body.quote, checked_by="human", root=root,
    )
    return {"result": link.model_dump(mode="json"), "commit_sha": sha}


class RemoveCitationRequest(CitationRef):
    rationale: str | None = None


@router.post("/remove")
def remove_citation(body: RemoveCitationRequest, root: Root) -> dict[str, Any]:
    """Detach a citation from a claim, as a recorded change."""
    link, sha = remove_evidence(body.target, body.attribute, body.bibkey, rationale=body.rationale, root=root)
    return {"result": link.model_dump(mode="json"), "commit_sha": sha}


class RemoveDataLinkRequest(BaseModel):
    target: str | None = None
    dataset_id: str
    column_names: list[str] = []
    rationale: str | None = None


@router.post("/data-links/remove")
def detach_data_link(body: RemoveDataLinkRequest, root: Root) -> dict[str, Any]:
    """Detach data evidence from an element (or the model), found by dataset and columns."""
    link, sha = remove_data_link(
        body.target,
        body.dataset_id,
        column_names=body.column_names,
        rationale=body.rationale,
        root=root,
    )
    return {"result": link.model_dump(mode="json"), "commit_sha": sha}
