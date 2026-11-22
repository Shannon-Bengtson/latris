"""`/range` and `/psa` routes shared by the decision-tree and Markov routers (operations/psa.py)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from latris.schema.common import ProvenanceOrigin, ProvenanceVerification
from latris.server.deps import Root


class RangeRequest(BaseModel):
    target: str  # a factor, or a link 'A -> B'
    distribution: str = "beta"
    params: dict[str, float] = {}  # or {"mean": m, "sd": s} for a beta or gamma; {"n": …} for a Dirichlet
    quantity: str | None = None
    strategy: str | None = None  # Markov only
    reason: str = ""
    source_id: str | None = None
    origin: ProvenanceOrigin = "human-direct"
    verification: ProvenanceVerification = "unverified"
    clear: bool = False


class PsaRequest(BaseModel):
    runs: int | None = None
    seed: int = 1234
    sampling: str = "lhs"
    record: bool = True


def add_routes(router: APIRouter, model_type: str) -> None:
    @router.get("/range")
    def list_ranges(root: Root) -> dict[str, Any]:
        """This model's PSA ranges: each target, the cell it describes, the distribution and its parameters."""
        from latris.operations import psa
        from latris.repo.project import require_project

        rows = [e.model_dump(mode="json") for e in psa.ranges(model_type, require_project(root))]
        return {"ranges": rows, "count": len(rows)}

    @router.post("/range")
    def set_range(body: RangeRequest, root: Root) -> dict[str, Any]:
        from latris.operations import psa

        if body.clear:
            return {"result": {"cleared": body.target},
                    "commit_sha": psa.clear_range(model_type, body.target, quantity=body.quantity,
                                                  strategy=body.strategy, root=root)}
        entry, sha = psa.set_range(model_type, body.target, body.distribution, body.params, quantity=body.quantity,
                                   strategy=body.strategy, reason=body.reason, source_id=body.source_id,
                                   origin=body.origin, verification=body.verification, root=root)
        return {"result": entry.model_dump(mode="json"), "commit_sha": sha}

    @router.post("/psa")
    def run_psa(root: Root, body: PsaRequest | None = None) -> dict[str, Any]:
        from latris.operations import psa

        body = body or PsaRequest()
        payload = psa.run(model_type, runs=body.runs, seed=body.seed, sampling=body.sampling, root=root)
        sha = None
        if body.record:
            sha, payload["run_id"] = psa.record(payload, root=root)
        return {"result": payload, "commit_sha": sha}
