"""Check routes: coherence, and the handover list."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from latris.operations import analysis as analysis_ops
from latris.operations.handover import HandoverReport, handover_check
from latris.server.deps import Root

router = APIRouter(prefix="/api/checks", tags=["checks"])


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


@router.get("/handover", response_model=HandoverReport)
def handover(root: Root, model_type: str | None = None) -> HandoverReport:
    """What's left before the model is ready to share: each item with what to do, where in the model it is,
    and the factors and links concerned. Ready when the list is empty."""
    return handover_check(model_type=model_type, root=root)
