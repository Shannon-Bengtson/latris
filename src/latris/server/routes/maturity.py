"""Moving a factor, link or finding along proposed → reviewed → approved. Approving also records a sign-off
(who approved it, in what role, for what scope) — the audit row for the approval."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel

from latris.operations import maturity as ops
from latris.server.deps import Root

router = APIRouter(prefix="/api/maturity", tags=["maturity"])

# Where each route sits in the workflow (schema/workflow.py; rules in docs/engineering/WORKFLOW_STRUCTURE.md).
PLACE = "review"


class MaturityRequest(BaseModel):
    target: str  # a factor, link or finding (id or label)
    level: Literal["proposed", "reviewed", "approved"]
    role: str = "Reviewer"  # approving: the approver's role
    scope: str = "Model"  # approving: what the approval covers
    notes: str | None = None


@router.post("")
def set_maturity(body: MaturityRequest, root: Root) -> dict[str, Any]:
    """Set the target's maturity; approving writes a sign-off too."""
    if body.level == "approved":
        level, sha = ops.approve(body.target, role=body.role, scope=body.scope, notes=body.notes, root=root)
    elif body.level == "reviewed":
        level, sha = ops.mark_reviewed(body.target, root=root)
    else:
        level, sha = ops.propose(body.target, root=root)
    return {"result": level, "commit_sha": sha}
