"""Edge endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from latris.operations import edges as edge_ops
from latris.schema import EdgeKind
from latris.server.deps import get_project_root

router = APIRouter(prefix="/api/edges", tags=["edges"])
Root = Annotated[Path, Depends(get_project_root)]


class AddEdgeRequest(BaseModel):
    from_query: str
    to_query: str
    kind: EdgeKind = "causal"


class RetypeEdgeRequest(BaseModel):
    new_kind: EdgeKind


@router.get("")
def list_edges(root: Root) -> list[dict[str, Any]]:
    return [e.model_dump(mode="json") for e in edge_ops.list_edges(root)]


@router.post("", status_code=201)
def add_edge(body: AddEdgeRequest, root: Root) -> dict[str, Any]:
    edge, sha = edge_ops.add_edge(body.from_query, body.to_query, kind=body.kind, root=root)
    return {"result": edge.model_dump(mode="json"), "commit_sha": sha}


@router.patch("/{query}/kind")
def retype_edge(query: str, body: RetypeEdgeRequest, root: Root) -> dict[str, Any]:
    edge, sha = edge_ops.retype_edge(query, body.new_kind, root=root)
    return {"result": edge.model_dump(mode="json"), "commit_sha": sha}


@router.delete("/{query}")
def remove_edge(query: str, root: Root) -> dict[str, Any]:
    edge, sha = edge_ops.remove_edge(query, root=root)
    return {"result": edge.model_dump(mode="json"), "commit_sha": sha}
