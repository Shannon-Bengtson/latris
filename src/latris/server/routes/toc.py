"""Theory of Change routes — levels and the pathway check.

Mirrors the `toc` CLI surface. Mutations return ``{"result": ..., "commit_sha":
sha}``; reads return plain data.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from latris.operations import toc
from latris.server.deps import get_project_root

router = APIRouter(prefix="/api/toc", tags=["toc"])
Root = Annotated[Path, Depends(get_project_root)]


class SetLevelRequest(BaseModel):
    node: str
    level: str


class CheckRequest(BaseModel):
    record: bool = True


@router.get("/levels")
def list_levels(root: Root) -> dict[str, Any]:
    levels = toc.get_levels(root=root)
    return {"levels": levels, "order": list(toc.LEVELS), "names": toc.LEVEL_NAMES, "count": len(levels)}


@router.post("/level")
def set_level(body: SetLevelRequest, root: Root) -> dict[str, Any]:
    try:
        target_id, sha = toc.set_level(body.node, body.level, root=root)
    except (ValueError, LookupError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"result": {"target_id": target_id, "level": body.level}, "commit_sha": sha}


@router.post("/check")
def check(root: Root, body: CheckRequest | None = None) -> dict[str, Any]:
    payload, sha = toc.check(record=body.record if body else True, root=root)
    return {"result": payload, "commit_sha": sha}
