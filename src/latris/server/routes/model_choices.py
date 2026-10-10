"""Model-choice endpoints — model-type selection captured as auditable,
append-only decisions with rationale."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from latris.operations import project as project_ops
from latris.server.deps import get_project_root

router = APIRouter(prefix="/api/model-choices", tags=["model-choices"])
Root = Annotated[Path, Depends(get_project_root)]


class SelectRequest(BaseModel):
    model_type_id: str
    rationale: str = ""
    origin: str = "human-direct"


class RetireRequest(BaseModel):
    model_type_id: str
    rationale: str = ""


class ReviseRequest(BaseModel):
    model_type_id: str
    rationale: str
    origin: str = "human-direct"


@router.post("/select", status_code=201)
def select_model(body: SelectRequest, root: Root) -> dict[str, Any]:
    _root, sha = project_ops.add_model_choice(
        body.model_type_id, body.rationale, origin=body.origin, root=root
    )
    return {"commit_sha": sha}


@router.post("/retire", status_code=201)
def retire_model(body: RetireRequest, root: Root) -> dict[str, Any]:
    _root, sha = project_ops.retire_model_choice(
        body.model_type_id, body.rationale, root=root
    )
    return {"commit_sha": sha}


@router.post("/revise", status_code=201)
def revise_model(body: ReviseRequest, root: Root) -> dict[str, Any]:
    _root, sha = project_ops.revise_model_choice(
        body.model_type_id, body.rationale, origin=body.origin, root=root
    )
    return {"commit_sha": sha}
