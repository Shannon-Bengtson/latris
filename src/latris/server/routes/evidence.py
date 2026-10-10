"""Evidence link endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from latris.operations.evidence import add_data_link, add_evidence
from latris.server.deps import get_project_root

router = APIRouter(prefix="/api/evidence", tags=["evidence"])
Root = Annotated[Path, Depends(get_project_root)]


class AddEvidenceRequest(BaseModel):
    target: str | None = None
    attribute: str = "description"
    bibkey: str
    verified_by: Literal["human", "ai"] = "human"
    notes: str | None = None


@router.post("", status_code=201)
def attach_evidence(body: AddEvidenceRequest, root: Root) -> dict[str, Any]:
    link, sha = add_evidence(
        body.target,
        body.attribute,
        body.bibkey,
        verified_by=body.verified_by,
        notes=body.notes,
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
