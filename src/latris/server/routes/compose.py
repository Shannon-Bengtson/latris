"""Compose endpoints — suggest nodes/edges from data, apply staged selections."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from latris.operations import compose as compose_ops
from latris.server.deps import get_project_root

router = APIRouter(prefix="/api/compose", tags=["compose"])
Root = Annotated[Path, Depends(get_project_root)]


# ---------------------------------------------------------------------------
# Request / response bodies
# ---------------------------------------------------------------------------


class SuggestEdgesRequest(BaseModel):
    node_labels: list[str]
    threshold: float = 0.3
    method: str = "pearson"


class ComposeNodeDef(BaseModel):
    label: str
    kind: str = "concept"
    origin: str = "human-direct"
    source_detail: str = ""
    description: str = ""
    # Data provenance (for DataLink creation)
    dataset_id: str | None = None
    column_name: str | None = None


class ComposeEdgeDef(BaseModel):
    from_label: str
    to_label: str
    kind: str = "causal"
    origin: str = "human-direct"
    source_detail: str = ""
    description: str = ""
    # Data provenance (for DataLink creation)
    dataset_id: str | None = None
    from_column: str | None = None
    to_column: str | None = None
    statistic: str | None = None
    stat_value: str | None = None


class ApplyRequest(BaseModel):
    nodes: list[ComposeNodeDef] = []
    edges: list[ComposeEdgeDef] = []


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/suggest-nodes")
def suggest_nodes(root: Root) -> list[dict[str, Any]]:
    """Return candidate entities extracted from dataset column metadata."""
    return compose_ops.suggest_nodes_from_data(root=root)


@router.post("/suggest-edges")
def suggest_edges(body: SuggestEdgesRequest, root: Root) -> list[dict[str, Any]]:
    """Return candidate edges from pairwise correlations in loaded datasets."""
    return compose_ops.suggest_edges_from_correlations(
        node_labels=body.node_labels,
        threshold=body.threshold,
        method=body.method,
        root=root,
    )


@router.post("/apply")
def apply_selections(body: ApplyRequest, root: Root) -> dict[str, Any]:
    """Commit staged Compose selections to the substrate in a single commit."""
    created_ids, sha, remapped = compose_ops.apply_compose_selections(
        nodes=[n.model_dump() for n in body.nodes],
        edges=[e.model_dump() for e in body.edges],
        root=root,
    )
    return {"created_ids": created_ids, "commit_sha": sha, "remapped": remapped}
