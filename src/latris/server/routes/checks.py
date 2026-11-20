"""Check routes: the handover list (what's left before the model is ready to share)."""

from __future__ import annotations

from fastapi import APIRouter

from latris.operations.handover import HandoverReport, handover_check
from latris.server.deps import Root

router = APIRouter(prefix="/api/checks", tags=["checks"])


@router.get("/handover", response_model=HandoverReport)
def handover(root: Root, model_type: str | None = None) -> HandoverReport:
    """What's left before the model is ready to share: each item with what to do, where in the model it is,
    and the factors and links concerned. Ready when the list is empty."""
    return handover_check(model_type=model_type, root=root)
