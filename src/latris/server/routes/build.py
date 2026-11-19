"""Build a model from a spec in one commit (``latris build``)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, model_validator

from latris.operations.build import build_from_spec, load_spec, preview_build
from latris.schema.build_spec import BuildSpec
from latris.server.deps import Root

router = APIRouter(prefix="/api/build", tags=["build"])


class _SpecRequest(BaseModel):
    """The spec as data (``spec``) or as written in a file (``text``: YAML or JSON, read as
    ``latris build --spec`` reads it) — one of the two."""

    spec: BuildSpec | None = None
    text: str | None = None
    # A factor, link or source the project already has: refuse the spec, or use it as it is.
    existing: Literal["refuse", "reuse"] = "refuse"

    @model_validator(mode="after")
    def _one(self) -> _SpecRequest:
        if (self.spec is None) == (self.text is None):
            raise ValueError("give the spec as spec (data) or text (YAML or JSON), not both or neither")
        return self

    def parsed(self) -> BuildSpec:
        return self.spec if self.spec is not None else load_spec(self.text or "")


class BuildRequest(_SpecRequest):
    verified_by: Literal["human", "ai"] = "human"


class PreviewRequest(_SpecRequest):
    pass


@router.post("")
def build(body: BuildRequest, root: Root) -> dict[str, Any]:
    result = build_from_spec(body.parsed(), verified_by=body.verified_by, existing=body.existing, root=root)
    return {"result": asdict(result), "commit_sha": result.commit_sha}


@router.post("/preview")
def preview(body: PreviewRequest, root: Root) -> dict[str, Any]:
    """What building the spec would add, reuse and change — or why it can't be built. Nothing changes."""
    return asdict(preview_build(body.parsed(), existing=body.existing, root=root))
