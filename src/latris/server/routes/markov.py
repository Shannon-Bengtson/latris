"""Markov routes — states, strategies, transitions, rewards, start, settings, check and analysis.

Mirrors the `markov` CLI surface. Mutations return ``{"result": ..., "commit_sha": sha}``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from latris.operations import markov
from latris.operations.readiness import assess_readiness
from latris.schema.common import ProvenanceOrigin, ProvenanceVerification
from latris.server.deps import Root

router = APIRouter(prefix="/api/markov", tags=["markov"])


class ElementRequest(BaseModel):
    node: str
    element: str


class TransitionRequest(BaseModel):
    link: str
    probability: float
    strategy: str | None = None
    origin: ProvenanceOrigin = "human-direct"
    source_id: str | None = None
    verification: ProvenanceVerification = "unverified"
    notes: str | None = None


class RewardRequest(BaseModel):
    """Only the fields sent change (besides state and strategy)."""

    state: str
    strategy: str | None = None
    cost: float | None = None
    utility: float | None = None
    notes: str | None = None
    origin: ProvenanceOrigin | None = None
    source_id: str | None = None
    verification: ProvenanceVerification | None = None


class StartRequest(BaseModel):
    state: str
    proportion: float


class AnalyseRequest(BaseModel):
    record: bool = True


def _call(fn, *args, **kwargs):
    return fn(*args, **kwargs)


@router.get("/check")
def check(root: Root) -> dict[str, Any]:
    r = assess_readiness("markov", root=root)
    return {"ready": r.can_switch, "gaps": [{"element_id": g.element_id, "element_label": g.element_label,
                                             "gap_type": g.gap_type, "message": g.message} for g in r.gaps]}


@router.get("/settings")
def get_settings(root: Root) -> dict[str, Any]:
    return markov.get_settings(root=root).model_dump(mode="json")


@router.post("/element")
def set_element(body: ElementRequest, root: Root) -> dict[str, Any]:
    target_id, sha = _call(markov.set_element, body.node, body.element, root=root)
    return {"result": {"target_id": target_id, "element": body.element}, "commit_sha": sha}


@router.post("/transition")
def set_transition(body: TransitionRequest, root: Root) -> dict[str, Any]:
    entry, sha = _call(markov.set_transition, body.link, body.probability, strategy=body.strategy, origin=body.origin,
                       source_id=body.source_id, verification=body.verification, notes=body.notes, root=root)
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


@router.post("/reward")
def set_reward(body: RewardRequest, root: Root) -> dict[str, Any]:
    fields = body.model_dump(exclude={"state", "strategy"}, exclude_unset=True)
    entry, sha = _call(markov.set_reward, body.state, strategy=body.strategy, root=root, **fields)
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


@router.post("/start")
def set_start(body: StartRequest, root: Root) -> dict[str, Any]:
    entry, sha = _call(markov.set_start, body.state, body.proportion, root=root)
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


@router.post("/settings")
def set_settings(body: dict[str, Any], root: Root) -> dict[str, Any]:
    s, sha = _call(markov.set_settings, root=root, **body)
    return {"result": s.model_dump(mode="json"), "commit_sha": sha}


@router.post("/analyse")
def analyse(root: Root, body: AnalyseRequest | None = None) -> dict[str, Any]:
    body = body or AnalyseRequest()
    payload = markov.analyse(root=root)
    sha = None
    if body.record and not payload["problems"]:
        sha, payload["run_id"] = markov.record(payload, root=root)
    return {"result": payload, "commit_sha": sha}
