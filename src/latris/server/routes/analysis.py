"""Graph analysis routes — loops, propagation, d-separation, blanket, paths, effect estimates, global
sensitivity."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from latris.operations import analysis as analysis_ops
from latris.server.deps import Root

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

# Where each route sits in the workflow (schema/workflow.py; rules in docs/engineering/WORKFLOW_STRUCTURE.md).
PLACE = {
    "*": "analyse.structural",
    "global_sensitivity": "analyse.sensitivity",
}


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


class GlobalSensitivityRequest(BaseModel):
    model_type: str
    method: str = "sobol"
    n: int | None = None
    seed: int = 1234
    output: str | None = None
    variable: str | None = None  # SD: the variable; BN: the factor asked about
    metric: str | None = None  # SD only
    state: str | None = None  # BN only
    evidence: dict[str, str] = {}  # BN only
    record: bool = True


@router.post("/global-sensitivity")
def global_sensitivity(body: GlobalSensitivityRequest, root: Root) -> dict[str, Any]:
    """Sobol indices or Morris screening over every input with a range (operations/global_sensitivity.py)."""
    from latris.operations import global_sensitivity as gs

    payload = gs.analyse(body.model_type, method=body.method, n=body.n, seed=body.seed, output=body.output,
                         variable=body.variable, metric=body.metric, state=body.state,
                         evidence=body.evidence or None, root=root)
    sha = None
    if body.record:
        sha, payload["run_id"] = gs.record(payload, root=root)
    return {"result": payload, "commit_sha": sha}
