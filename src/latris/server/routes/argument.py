"""Argument map routes — conclusion and claims, links, assessments, check and analysis.

Mirrors the `argument` CLI surface. Mutations return ``{"result": ..., "commit_sha": sha}``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from latris.operations import argument_map as am
from latris.schema.common import ProvenanceOrigin, ProvenanceVerification
from latris.server.deps import Root
from latris.server.routes import _formalism

router = APIRouter(prefix="/api/argument", tags=["argument"])


class ElementRequest(BaseModel):
    node: str
    element: str


class LinkRequest(BaseModel):
    """Only the fields sent change (besides the link)."""

    link: str  # 'Premise -> Claim'
    relation: str | None = None
    reason: str | None = None
    warrant: str | None = None
    qualifier: str | None = None
    notes: str | None = None
    origin: ProvenanceOrigin | None = None
    source_id: str | None = None
    verification: ProvenanceVerification | None = None


class ClaimRequest(BaseModel):
    node: str
    assessment: str | None = None  # accepted | rejected | None (not assessed)
    rationale: str | None = None
    origin: ProvenanceOrigin = "human-direct"
    source_id: str | None = None
    verification: ProvenanceVerification = "unverified"


@router.get("/map")
def get_map(root: Root) -> dict[str, Any]:
    """Everything the map is made of: elements, links (by edge id) and assessments."""
    return {"elements": am.get_elements(root=root),
            "links": am.get_links(root=root).model_dump(mode="json")["entries"],
            "claims": am.get_claims(root=root).model_dump(mode="json")["entries"]}


@router.post("/element")
def set_element(body: ElementRequest, root: Root) -> dict[str, Any]:
    target_id, sha = am.set_element(body.node, body.element, root=root)
    return {"result": {"target_id": target_id, "element": body.element}, "commit_sha": sha}


@router.post("/link")
def set_link(body: LinkRequest, root: Root) -> dict[str, Any]:
    entry, sha = am.set_link(body.link, root=root, **body.model_dump(exclude={"link"}, exclude_unset=True))
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


@router.post("/claim")
def set_claim(body: ClaimRequest, root: Root) -> dict[str, Any]:
    entry, sha = am.set_claim(body.node, root=root, **body.model_dump(exclude={"node"}))
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


_formalism.add_check_route(router, "argument_map")
_formalism.add_analyse_route(router, am)
