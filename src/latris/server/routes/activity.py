"""Recent project activity — thin wrapper around ``git log``."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from latris.repo import git
from latris.server.deps import get_project_root

router = APIRouter(prefix="/api/activity", tags=["activity"])
Root = Annotated[Path, Depends(get_project_root)]


@router.get("")
def activity(root: Root, limit: int = Query(default=20, ge=1, le=50)) -> dict[str, Any]:
    entries = git.recent_commits(root, limit=limit)
    return {"entries": entries}
