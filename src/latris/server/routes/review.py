"""Review pack import endpoint."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, UploadFile

from latris.operations import review as review_ops
from latris.server.deps import get_project_root

router = APIRouter(prefix="/api/review", tags=["review"])
Root = Annotated[Path, Depends(get_project_root)]


@router.post("/import")
async def import_review(root: Root, file: UploadFile = File(...)) -> dict[str, Any]:
    """Import a completed review HTML file and extract feedback as provenance."""
    content = (await file.read()).decode("utf-8")
    result = review_ops.import_review(content, root=root)
    return {
        "session": result.session.model_dump(mode="json"),
        "commit_sha": result.commit_sha,
        "version_drift": result.version_drift,
        "items_imported": result.items_imported,
        "challenges_created": result.challenges_created,
        "questions_created": result.questions_created,
        "signoffs_created": result.signoffs_created,
        "warnings": result.warnings,
    }
