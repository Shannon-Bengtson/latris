"""Provenance endpoints — 7 append-only log types."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from latris.operations import provenance as prov_ops
from latris.server.deps import get_project_root

router = APIRouter(prefix="/api/provenance", tags=["provenance"])
Root = Annotated[Path, Depends(get_project_root)]


class AssumptionRequest(BaseModel):
    statement: str
    rationale: str | None = None
    target_id: str | None = None


class DecisionRequest(BaseModel):
    statement: str
    rationale: str
    target_id: str | None = None


class SignoffRequest(BaseModel):
    role: str = "Reviewer"
    scope: str | None = None
    target_id: str | None = None
    notes: str | None = None


class SessionRequest(BaseModel):
    held_at: date
    attendees: list[str]
    notes: str | None = None
    notes_file: str | None = None


class QuestionRequest(BaseModel):
    question: str
    target_id: str | None = None


class ExclusionRequest(BaseModel):
    statement: str
    rationale: str


class PredictionRequest(BaseModel):
    statement: str
    horizon: str


@router.post("/assumptions", status_code=201)
def add_assumption(body: AssumptionRequest, root: Root) -> dict[str, Any]:
    entry, sha = prov_ops.add_assumption(body.statement, body.rationale, target_id=body.target_id, root=root)
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


@router.post("/decisions", status_code=201)
def log_decision(body: DecisionRequest, root: Root) -> dict[str, Any]:
    entry, sha = prov_ops.log_decision(body.statement, body.rationale, target_id=body.target_id, root=root)
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


@router.post("/signoffs", status_code=201)
def record_signoff(body: SignoffRequest, root: Root) -> dict[str, Any]:
    entry, sha = prov_ops.record_signoff(
        role=body.role,
        scope=body.scope,
        target_id=body.target_id,
        notes=body.notes,
        root=root,
    )
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


@router.post("/sessions", status_code=201)
def record_session(body: SessionRequest, root: Root) -> dict[str, Any]:
    entry, sha = prov_ops.record_session(
        body.held_at,
        body.attendees,
        notes=body.notes,
        notes_file=body.notes_file,
        root=root,
    )
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


@router.post("/questions", status_code=201)
def add_question(body: QuestionRequest, root: Root) -> dict[str, Any]:
    entry, sha = prov_ops.add_question(body.question, target_id=body.target_id, root=root)
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


@router.post("/exclusions", status_code=201)
def add_exclusion(body: ExclusionRequest, root: Root) -> dict[str, Any]:
    entry, sha = prov_ops.add_exclusion(body.statement, body.rationale, root=root)
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


@router.post("/predictions", status_code=201)
def add_prediction(body: PredictionRequest, root: Root) -> dict[str, Any]:
    entry, sha = prov_ops.add_prediction(body.statement, body.horizon, root=root)
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}
