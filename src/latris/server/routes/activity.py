"""Recent project activity — thin wrapper around ``git log``."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from latris.repo import git
from latris.server.deps import Root

router = APIRouter(prefix="/api/activity", tags=["activity"])


@router.get("")
def activity(root: Root, limit: int = Query(default=20, ge=1, le=50)) -> dict[str, Any]:
    entries = git.recent_commits(root, limit=limit)
    return {"entries": entries}
