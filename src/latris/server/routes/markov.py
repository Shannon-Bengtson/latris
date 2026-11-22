"""Markov routes — states, strategies, transitions, rewards, start, settings, check and analysis.

Mirrors the `markov` CLI surface. Mutations return ``{"result": ..., "commit_sha": sha}``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from latris.operations import markov
from latris.schema.common import ProvenanceOrigin, ProvenanceVerification
from latris.server.deps import Root
from latris.server.routes import _formalism
from latris.server.routes._formalism import ProvenanceFields

router = APIRouter(prefix="/api/markov", tags=["markov"])


class ElementRequest(BaseModel):
    node: str
    element: str


class TransitionRequest(ProvenanceFields):
    link: str
    probability: float
    strategy: str | None = None


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




@router.get("/model")
def model(root: Root) -> dict[str, Any]:
    """Everything the model is made of: states and strategies, transitions (by edge id), costs and utilities,
    the starting cohort."""
    return {
        "elements": markov.get_elements(root=root),
        "transitions": markov.get_transitions(root=root).model_dump(mode="json")["entries"],
        "rewards": markov.get_rewards(root=root).model_dump(mode="json")["entries"],
        "start": markov.get_start(root=root).model_dump(mode="json")["entries"],
    }


@router.get("/settings")
def get_settings(root: Root) -> dict[str, Any]:
    return markov.get_settings(root=root).model_dump(mode="json")


@router.post("/element")
def set_element(body: ElementRequest, root: Root) -> dict[str, Any]:
    target_id, sha = markov.set_element(body.node, body.element, root=root)
    return {"result": {"target_id": target_id, "element": body.element}, "commit_sha": sha}


@router.post("/transition")
def set_transition(body: TransitionRequest, root: Root) -> dict[str, Any]:
    entry, sha = markov.set_transition(
        body.link, body.probability, strategy=body.strategy, **body.provenance(), root=root
    )
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


@router.post("/reward")
def set_reward(body: RewardRequest, root: Root) -> dict[str, Any]:
    fields = body.model_dump(exclude={"state", "strategy"}, exclude_unset=True)
    entry, sha = markov.set_reward(body.state, strategy=body.strategy, root=root, **fields)
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


@router.post("/start")
def set_start(body: StartRequest, root: Root) -> dict[str, Any]:
    entry, sha = markov.set_start(body.state, body.proportion, root=root)
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


@router.post("/settings")
def set_settings(body: dict[str, Any], root: Root) -> dict[str, Any]:
    s, sha = markov.set_settings(root=root, **body)
    return {"result": s.model_dump(mode="json"), "commit_sha": sha}


_formalism.add_check_route(router, "markov")
_formalism.add_analyse_route(router, markov)


from latris.server.routes import _psa  # noqa: E402

_psa.add_routes(router, "markov")
