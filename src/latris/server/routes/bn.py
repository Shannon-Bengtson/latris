"""Bayesian Network routes — state spaces, CPTs, readiness check, inference.

Mirrors the `bn` CLI surface. Mutations return ``{"result": ..., "commit_sha":
sha}``; reads return plain data. All operations receive the injected project
root explicitly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from latris.operations import bn as bn_ops
from latris.server.deps import get_project_root

router = APIRouter(prefix="/api/bn", tags=["bn"])
Root = Annotated[Path, Depends(get_project_root)]


# ── state spaces ─────────────────────────────────────────────────────


class SetStateSpaceRequest(BaseModel):
    node: str
    states: list[str]
    ordered: bool = False


@router.get("/state-spaces")
def list_state_spaces(root: Root) -> dict[str, Any]:
    store = bn_ops.get_state_spaces(root=root)
    return {"state_spaces": store.model_dump(mode="json")["entries"], "count": len(store.entries)}


@router.post("/state-space")
def set_state_space(body: SetStateSpaceRequest, root: Root) -> dict[str, Any]:
    try:
        entry, sha = bn_ops.set_state_space(body.node, body.states, ordered=body.ordered, root=root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


# ── CPTs ─────────────────────────────────────────────────────────────


class SetCPTRequest(BaseModel):
    node: str
    parents: list[str] = []
    probs: list[float]
    origin: str = "human-direct"
    source_id: str | None = None


@router.get("/cpts")
def list_cpts(root: Root) -> dict[str, Any]:
    store = bn_ops.get_cpts(root=root)
    return {"cpts": store.model_dump(mode="json")["entries"], "count": len(store.entries)}


@router.post("/cpt")
def set_cpt(body: SetCPTRequest, root: Root) -> dict[str, Any]:
    try:
        cpt, sha = bn_ops.set_cpt(
            body.node, body.parents, body.probs, origin=body.origin, source_id=body.source_id, root=root
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"result": cpt.model_dump(mode="json"), "commit_sha": sha}


# ── canonical models (Noisy-OR) ──────────────────────────────────────


class NoisyOrCause(BaseModel):
    parent: str
    active_state: str
    prob: float


class SetNoisyOrRequest(BaseModel):
    node: str
    causes: list[NoisyOrCause]
    leak: float = 0.0
    origin: str = "human-elicited"
    source_id: str | None = None


@router.get("/noisy-or")
def list_noisy_or(root: Root) -> dict[str, Any]:
    store = bn_ops.get_noisy_or(root=root)
    return {"noisy_or": store.model_dump(mode="json")["entries"], "count": len(store.entries)}


@router.post("/noisy-or")
def set_noisy_or(body: SetNoisyOrRequest, root: Root) -> dict[str, Any]:
    causes = [(c.parent, c.active_state, c.prob) for c in body.causes]
    try:
        entry, sha = bn_ops.set_noisy_or(
            body.node, body.leak, causes, origin=body.origin, source_id=body.source_id, root=root
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


# ── parameter learning ───────────────────────────────────────────────


class LearnRequest(BaseModel):
    dataset: str
    nodes: list[str] | None = None
    estimator: str = "bayesian"
    prior: str = "BDeu"
    equivalent_sample_size: int = 5
    apply: bool = False


@router.post("/learn")
def learn(body: LearnRequest, root: Root) -> dict[str, Any]:
    from latris.operations import bn_learn

    try:
        proposal = bn_learn.learn_cpts(
            body.dataset,
            nodes=body.nodes,
            estimator=body.estimator,
            prior=body.prior,
            equivalent_sample_size=body.equivalent_sample_size,
            root=root,
        )
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    preview = [
        {
            "node_id": d.node_id,
            "parents": d.parents,
            "rows_learned": d.rows_learned,
            "rows_kept": d.rows_kept,
            "zero_support_combos": d.zero_support_combos,
            "skipped_reason": d.skipped_reason,
            "origin": ("mixed" if (d.rows_kept and d.rows_learned) else "data-derived"),
        }
        for d in proposal.diffs
    ]
    out: dict[str, Any] = {
        "preview": preview,
        "rows_used": proposal.rows_used,
        "rows_dropped_na": proposal.rows_dropped_na,
        "applied": False,
    }
    if body.apply and proposal.affected_ids:
        sha, run_id = bn_learn.apply_learned(proposal, root=root)
        out.update(applied=True, commit_sha=sha, run_id=run_id)
    return out


# ── readiness ────────────────────────────────────────────────────────


@router.get("/check")
def check(root: Root) -> dict[str, Any]:
    gaps = bn_ops.check(root=root)
    return {
        "ready": not gaps,
        "gaps": [
            {
                "element_id": g.element_id,
                "element_label": g.element_label,
                "gap_type": g.gap_type,
                "message": g.message,
            }
            for g in gaps
        ],
    }


# ── sensitivity ──────────────────────────────────────────────────────


class SensitivityRequest(BaseModel):
    target: str
    state: str
    evidence: dict[str, str] | None = None
    top: int | None = 15
    record: bool = True


@router.post("/sensitivity")
def sensitivity(body: SensitivityRequest, root: Root) -> dict[str, Any]:
    from latris.operations import bn_sensitivity

    try:
        result = bn_sensitivity.sensitivity(
            body.target, body.state, evidence=body.evidence, top=body.top, root=root
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    out = result.model_dump(mode="json")
    if body.record:
        sha, run_id = bn_sensitivity.record_sensitivity(result, root=root)
        out["commit_sha"] = sha
        out["run_id"] = run_id
    return out


# ── inference ────────────────────────────────────────────────────────


class QueryRequest(BaseModel):
    query: list[str] | None = None
    evidence: dict[str, str] | None = None


@router.post("/query")
def query(body: QueryRequest, root: Root) -> dict[str, Any]:
    try:
        result = bn_ops.infer(query=body.query, evidence=body.evidence, root=root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"marginals": result.marginals, "evidence": result.evidence, "method": result.method}


@router.get("/marginals")
def marginals(root: Root) -> dict[str, Any]:
    try:
        result = bn_ops.infer(root=root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"marginals": result.marginals, "evidence": result.evidence, "method": result.method}
