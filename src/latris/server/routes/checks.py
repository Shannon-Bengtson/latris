"""Coherence-check API routes."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from latris.operations import analysis as analysis_ops
from latris.server.deps import get_project_root

router = APIRouter(prefix="/api/checks", tags=["checks"])
Root = Annotated[Path, Depends(get_project_root)]


@router.get("/coherence")
def coherence(root: Root) -> dict[str, Any]:
    """Flag edges where description and polarity tell opposite causal stories."""
    findings = analysis_ops.run_coherence_check(root)
    return {
        "findings": [
            {
                "target_id": f.target_id,
                "kind": f.kind,
                "description": f.description,
                "polarity": f.polarity,
                "polarity_rationale": f.polarity_rationale,
                "severity": f.severity,
                "reason": f.reason,
            }
            for f in findings
        ],
        "count": len(findings),
    }
