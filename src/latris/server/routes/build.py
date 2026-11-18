"""Build a model from a spec in one commit (``latris build``)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel

from latris.operations.build import build_from_spec
from latris.schema.build_spec import BuildSpec
from latris.server.deps import Root

router = APIRouter(prefix="/api/build", tags=["build"])


class BuildRequest(BaseModel):
    spec: BuildSpec
    verified_by: Literal["human", "ai"] = "human"


@router.post("")
def build(body: BuildRequest, root: Root) -> dict[str, Any]:
    result = build_from_spec(body.spec, verified_by=body.verified_by, root=root)
    return {"result": asdict(result), "commit_sha": result.commit_sha}
