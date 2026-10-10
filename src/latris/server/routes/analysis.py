"""Graph analysis routes — loops, propagation, d-separation, blanket, paths."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from latris.operations import analysis as analysis_ops
from latris.server.deps import get_project_root

router = APIRouter(prefix="/api/analysis", tags=["analysis"])
Root = Annotated[Path, Depends(get_project_root)]


@router.get("/loops")
def loops(root: Root) -> dict[str, Any]:
    """List all feedback loops with R/B classification."""
    classified = analysis_ops.analyse_loops(root)
    return {
        "loops": [
            {
                "node_ids": list(loop.node_ids),
                "edge_ids": list(loop.edge_ids),
                "classification": loop.classification,
            }
            for loop in classified
        ],
        "count": len(classified),
    }


@router.get("/propagate/{entity_id}")
def propagate(entity_id: str, root: Root) -> dict[str, Any]:
    """Trace qualitative impact from a variable."""
    effects = analysis_ops.analyse_propagation(entity_id, root)
    return {
        "source_id": entity_id,
        "effects": [
            {
                "entity_id": e.entity_id,
                "effect": e.effect,
                "paths_positive": e.paths_positive,
                "paths_negative": e.paths_negative,
            }
            for e in effects
        ],
    }


@router.get("/d-separation")
def d_sep_route(
    root: Root,
    x: list[str] = Query(...),
    y: list[str] = Query(...),
    given: list[str] = Query(default=[]),
) -> dict[str, Any]:
    """Test d-separation: are X and Y independent given Z?"""
    result = analysis_ops.analyse_d_separation(x, y, given, root=root)
    return {
        "x": x,
        "y": y,
        "given": given,
        "d_separated": result,
    }


@router.get("/blanket/{entity_id}")
def blanket_route(entity_id: str, root: Root) -> dict[str, Any]:
    """Compute the Markov blanket of a variable."""
    mb = analysis_ops.analyse_blanket(entity_id, root)
    return {
        "entity_id": entity_id,
        "blanket": sorted(mb),
    }


@router.get("/paths")
def paths_route(
    root: Root,
    from_id: str = Query(...),
    to_id: str = Query(...),
) -> dict[str, Any]:
    """Enumerate paths between two variables with classification."""
    found = analysis_ops.analyse_paths(from_id, to_id, root)
    return {
        "from_id": from_id,
        "to_id": to_id,
        "paths": [
            {
                "nodes": [{"entity_id": pn.entity_id, "classification": pn.classification} for pn in p.nodes],
                "is_directed": p.is_directed,
            }
            for p in found
        ],
        "count": len(found),
    }


@router.get("/adjustment-sets")
def adjustment_sets_route(
    root: Root,
    exposure_id: str = Query(...),
    outcome_id: str = Query(...),
) -> dict[str, Any]:
    """Find valid adjustment sets via the backdoor criterion."""
    sets = analysis_ops.analyse_adjustment_sets(exposure_id, outcome_id, root)
    return {
        "exposure_id": exposure_id,
        "outcome_id": outcome_id,
        "adjustment_sets": [sorted(s) for s in sets],
        "count": len(sets),
    }
