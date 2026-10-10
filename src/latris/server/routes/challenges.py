"""Challenge workflow endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from latris.operations import challenges as ch_ops
from latris.schema import ChallengeState
from latris.server.deps import get_project_root

router = APIRouter(prefix="/api/challenges", tags=["challenges"])
Root = Annotated[Path, Depends(get_project_root)]


class OpenChallengeRequest(BaseModel):
    target: str | None = None
    argument: str
    attribute: str | None = None


class AddTurnRequest(BaseModel):
    message: str


class ResolveChallengeRequest(BaseModel):
    state: ChallengeState
    rationale: str | None = None


@router.get("")
def list_challenges(root: Root) -> list[dict[str, Any]]:
    return [c.model_dump(mode="json") for c in ch_ops.list_challenges(root)]


@router.get("/{query}")
def get_challenge(query: str, root: Root) -> dict[str, Any]:
    return ch_ops.get_challenge(query, root).model_dump(mode="json")


@router.post("", status_code=201)
def open_challenge(body: OpenChallengeRequest, root: Root) -> dict[str, Any]:
    challenge, sha = ch_ops.open_challenge(body.target, body.argument, attribute=body.attribute, root=root)
    return {"result": challenge.model_dump(mode="json"), "commit_sha": sha}


@router.post("/{query}/turns", status_code=201)
def add_turn(query: str, body: AddTurnRequest, root: Root) -> dict[str, Any]:
    challenge, sha = ch_ops.add_turn(query, body.message, root=root)
    return {"result": challenge.model_dump(mode="json"), "commit_sha": sha}


@router.post("/{query}/resolve")
def resolve_challenge(query: str, body: ResolveChallengeRequest, root: Root) -> dict[str, Any]:
    challenge, sha = ch_ops.resolve_challenge(query, body.state, rationale=body.rationale, root=root)
    return {"result": challenge.model_dump(mode="json"), "commit_sha": sha}
