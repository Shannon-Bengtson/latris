"""Check routes: the handover list (what's left before the model is ready to share), and putting right
broken references between the project's files."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from latris.operations.handover import HandoverReport, handover_check
from latris.operations.integrity import IntegrityProblem, check_integrity, remove_dangling_rows
from latris.server.deps import Root

router = APIRouter(prefix="/api/checks", tags=["checks"])

# Where each route sits in the workflow (schema/workflow.py; rules in docs/engineering/WORKFLOW_STRUCTURE.md).
PLACE = "validation"


@router.get("/handover", response_model=HandoverReport)
def handover(root: Root, model_type: str | None = None) -> HandoverReport:
    """What's left before the model is ready to share: each item with what to do, where in the model it is,
    and the factors and links concerned. Ready when the list is empty."""
    return handover_check(model_type=model_type, root=root)


class IntegrityFix(BaseModel):
    removed: int  # rows about factors and links that no longer exist, removed
    commit_sha: str  # "" when there was nothing to remove
    remaining: list[IntegrityProblem]  # what's still broken (needs a person: a duplicate label, an unknown source…)


@router.post("/integrity/fix", response_model=IntegrityFix)
def fix_integrity(root: Root) -> IntegrityFix:
    """Remove the rows left behind by deleted factors and links (one commit; history kept), and say what's
    still broken."""
    removed, sha = remove_dangling_rows(root=root)
    return IntegrityFix(removed=removed, commit_sha=sha, remaining=check_integrity(root=root).errors)
