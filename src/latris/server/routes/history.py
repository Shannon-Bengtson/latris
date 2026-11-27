"""Undo and redo endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from latris.operations import history as history_ops
from latris.server.deps import Root

router = APIRouter(prefix="/api/history", tags=["history"])

# Where each route sits in the workflow (schema/workflow.py; rules in docs/engineering/WORKFLOW_STRUCTURE.md).
PLACE = "versions"


def _status(root: Root) -> dict[str, Any]:
    s = history_ops.status(root)
    return {"undo": s.undo, "redo": s.redo}


@router.get("")
def history_status(root: Root) -> dict[str, Any]:
    """What undo and redo would do next: the action's description, or null when there is none."""
    return _status(root)


@router.post("/undo")
def undo(root: Root) -> dict[str, Any]:
    """Take back the last action (a new commit; nothing is rewritten). Repeat to step further back."""
    try:
        sha, subject = history_ops.undo(root)
    except (history_ops.NothingToUndo, history_ops.CannotUndo) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"commit_sha": sha, "message": f"Undid: {subject}", "action": subject, **_status(root)}


@router.post("/redo")
def redo(root: Root) -> dict[str, Any]:
    """Put back the last action undone. A new action after an undo leaves nothing to redo."""
    try:
        sha, subject = history_ops.redo(root)
    except (history_ops.NothingToUndo, history_ops.CannotUndo) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"commit_sha": sha, "message": f"Redid: {subject}", "action": subject, **_status(root)}
