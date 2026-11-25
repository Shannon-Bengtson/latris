"""Recent project activity — ``git log``, with IDs in subjects replaced by names."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from latris.operations.activity import recent_activity
from latris.server.deps import Root

router = APIRouter(prefix="/api/activity", tags=["activity"])


@router.get("")
def activity(root: Root, limit: int = Query(default=20, ge=1, le=50)) -> dict[str, Any]:
    return {"entries": recent_activity(root, limit=limit)}
