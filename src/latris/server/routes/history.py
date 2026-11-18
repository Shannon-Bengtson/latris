"""Undo and history endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from latris.repo import git
from latris.server.deps import Root

router = APIRouter(prefix="/api/history", tags=["history"])


def _is_branch_root_commit(root: Path) -> bool:
    """True if HEAD is the version-creation commit on a non-main branch."""
    if git.current_branch(root) == "main":
        return False
    try:
        subject = git.run_git(
            ["log", "-1", "--format=%s", "HEAD"],
            cwd=root,
        ).stdout.strip()
    except git.GitError:
        return False
    return subject.startswith("Created alternative:")


@router.post("/undo")
def undo(root: Root) -> dict[str, Any]:
    if _is_branch_root_commit(root):
        raise HTTPException(
            status_code=409,
            detail="Nothing more to undo on this version.",
        )
    sha = git.revert_head(root)
    return {"commit_sha": sha, "message": "Reverted HEAD commit"}
