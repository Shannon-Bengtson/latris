"""Universal attribute endpoints (description, confidence).

Maturity is no longer per-attribute — see ``operations/maturity.py``.
Per-cell uncertainty is expressible via ``Confidence`` and the
``EvidenceLink`` audit axes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from latris.operations.attributes import AttributeName, set_attribute
from latris.server.deps import get_project_root

router = APIRouter(prefix="/api/attributes", tags=["attributes"])
Root = Annotated[Path, Depends(get_project_root)]


class SetAttributeRequest(BaseModel):
    value: str


@router.put("/{target}/{attribute}")
def set_attr(target: str, attribute: AttributeName, body: SetAttributeRequest, root: Root) -> dict[str, Any]:
    target_id, sha = set_attribute(target, attribute, body.value, root=root)
    return {"target_id": target_id, "commit_sha": sha}
