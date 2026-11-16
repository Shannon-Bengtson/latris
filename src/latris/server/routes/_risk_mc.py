"""`/uncertainty` and `/monte-carlo` routes shared by the fault-tree, bow-tie and event-tree routers."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from latris.server.deps import get_project_root

Root = Annotated[Path, Depends(get_project_root)]


class UncertaintyRequest(BaseModel):
    target: str
    distribution: str = "lognormal"
    params: dict[str, float] = {}  # or {"median": m, "error_factor": ef} for a lognormal
    given: dict[str, str] = {}  # event trees: the probability's condition, heading → yes/no
    reason: str = ""
    source_id: str | None = None
    origin: str = "human-direct"
    verification: str = "unverified"
    clear: bool = False


class MonteCarloRequest(BaseModel):
    runs: int = 5000
    seed: int = 1234
    sampling: str = "lhs"
    output: str | None = None
    record: bool = True


def add_routes(router: APIRouter, model_type: str) -> None:
    @router.post("/uncertainty")
    def set_uncertainty(body: UncertaintyRequest, root: Root) -> dict[str, Any]:
        from latris.operations import risk_uncertainty as ru

        given = list(body.given.items()) or None
        try:
            if body.clear:
                return {"result": {"cleared": body.target},
                        "commit_sha": ru.clear_uncertainty(model_type, body.target, given=given, root=root)}
            entry, sha = ru.set_uncertainty(model_type, body.target, body.distribution, body.params, given=given,
                                            reason=body.reason, source_id=body.source_id,
                                            origin=body.origin, verification=body.verification,  # type: ignore[arg-type]
                                            root=root)
        except (ValueError, LookupError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"result": entry.model_dump(mode="json"), "commit_sha": sha}

    @router.post("/monte-carlo")
    def monte_carlo(root: Root, body: MonteCarloRequest | None = None) -> dict[str, Any]:
        from latris.operations import risk_uncertainty as ru

        body = body or MonteCarloRequest()
        try:
            payload = ru.monte_carlo(model_type, runs=body.runs, seed=body.seed, sampling=body.sampling,
                                     output=body.output, root=root)
        except (ValueError, LookupError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        sha = None
        if body.record:
            sha, payload["run_id"] = ru.record(payload, root=root)
        return {"result": payload, "commit_sha": sha}
