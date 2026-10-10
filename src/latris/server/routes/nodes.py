"""Node (Entity) endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from latris.operations import nodes as node_ops
from latris.schema import EntityKind
from latris.server.deps import get_project_root

router = APIRouter(prefix="/api/nodes", tags=["nodes"])
Root = Annotated[Path, Depends(get_project_root)]


class AddNodeRequest(BaseModel):
    label: str
    kind: EntityKind = "concept"


class RenameNodeRequest(BaseModel):
    new_label: str


class RetypeNodeRequest(BaseModel):
    new_kind: EntityKind


@router.get("")
def list_nodes(root: Root) -> list[dict[str, Any]]:
    return [e.model_dump(mode="json") for e in node_ops.list_nodes(root)]


@router.get("/{query}")
def get_node(query: str, root: Root) -> dict[str, Any]:
    return node_ops.get_node(query, root).model_dump(mode="json")


@router.post("", status_code=201)
def add_node(body: AddNodeRequest, root: Root) -> dict[str, Any]:
    entity, sha = node_ops.add_node(body.label, kind=body.kind, root=root)
    return {"result": entity.model_dump(mode="json"), "commit_sha": sha}


@router.patch("/{query}")
def rename_node(query: str, body: RenameNodeRequest, root: Root) -> dict[str, Any]:
    entity, sha = node_ops.rename_node(query, body.new_label, root=root)
    return {"result": entity.model_dump(mode="json"), "commit_sha": sha}


@router.patch("/{query}/kind")
def retype_node(query: str, body: RetypeNodeRequest, root: Root) -> dict[str, Any]:
    entity, sha = node_ops.retype_node(query, body.new_kind, root=root)
    return {"result": entity.model_dump(mode="json"), "commit_sha": sha}


@router.delete("/{query}")
def remove_node(query: str, root: Root) -> dict[str, Any]:
    entity, removed_edges, sha = node_ops.remove_node(query, root=root)
    return {
        "result": entity.model_dump(mode="json"),
        "removed_edge_ids": removed_edges,
        "commit_sha": sha,
    }
