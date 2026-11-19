"""Build a model from a spec in one commit (``latris build``)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel

from latris.operations.build import build_from_spec, preview_build
from latris.schema.build_spec import BuildSpec
from latris.server.deps import Root

router = APIRouter(prefix="/api/build", tags=["build"])


class BuildRequest(BaseModel):
    spec: BuildSpec
    verified_by: Literal["human", "ai"] = "human"
    # A factor, link or source the project already has: refuse the spec, or use it as it is.
    existing: Literal["refuse", "reuse"] = "refuse"


class PreviewRequest(BaseModel):
    spec: BuildSpec
    existing: Literal["refuse", "reuse"] = "refuse"


@router.post("")
def build(body: BuildRequest, root: Root) -> dict[str, Any]:
    result = build_from_spec(body.spec, verified_by=body.verified_by, existing=body.existing, root=root)
    return {"result": asdict(result), "commit_sha": result.commit_sha}


@router.post("/preview")
def preview(body: PreviewRequest, root: Root) -> dict[str, Any]:
    """What building the spec would add, reuse and change — or why it can't be built. Nothing changes."""
    return asdict(preview_build(body.spec, existing=body.existing, root=root))
