"""Report configuration routes — the persisted Communicate report curation.

GET returns the stored config (defaults if unset); PUT replaces it and commits.
The GUI report store reads/writes through here so the Report's curation is a
git-versioned artifact rather than browser localStorage.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from latris.operations.report_config import (
    load_report_config,
    save_report_config,
)
from latris.schema.report_config import ReportConfig
from latris.server.deps import get_project_root

router = APIRouter(prefix="/api/report-config", tags=["report-config"])
Root = Annotated[Path, Depends(get_project_root)]


@router.get("")
def get_report_config(root: Root, model_type: str = Query(...)) -> dict[str, Any]:
    """Load the persisted report configuration for one formalism."""
    config = load_report_config(model_type, root=root)
    return {"result": config.model_dump(mode="json")}


@router.put("")
def put_report_config(body: ReportConfig, root: Root) -> dict[str, Any]:
    """Replace one formalism's report configuration and commit.

    The ``model_type`` carried on the body selects which entry to replace.
    """
    config, sha = save_report_config(body, root=root)
    return {"result": config.model_dump(mode="json"), "commit_sha": sha}
