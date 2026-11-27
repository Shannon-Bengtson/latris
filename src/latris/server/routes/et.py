"""Event tree routes — elements, order, sequences, probabilities, frequency, check, analysis.

Mirrors the `et` CLI surface. Mutations return ``{"result": ..., "commit_sha":
sha}``; reads return plain data. Answers are ``{"heading": ..., "answer": "yes"|"no"}``.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from latris.operations import event_tree as et
from latris.server.deps import Root
from latris.server.routes import _formalism
from latris.server.routes._formalism import ProvenanceFields

router = APIRouter(prefix="/api/et", tags=["et"])

# Where each route sits in the workflow (schema/workflow.py; rules in docs/engineering/WORKFLOW_STRUCTURE.md).
PLACE = {
    "tree": "formalise",
    "set_element": "formalise.definitions",
    "set_order": "formalise.definitions",
    "set_sequence": "formalise.definitions",
    "remove_sequence": "formalise.definitions",
    "set_probability": "formalise.values",
    "set_frequency": "formalise.values",
}



class Answer(BaseModel):
    heading: str
    answer: Literal["yes", "no"]


class ElementRequest(BaseModel):
    node: str
    element: str


class OrderRequest(BaseModel):
    headings: list[str]


class SequenceRequest(BaseModel):
    end_state: str
    answers: list[Answer] = Field(default_factory=list)


class RemoveSequenceRequest(BaseModel):
    answers: list[Answer]


class ProbabilityRequest(ProvenanceFields):
    node: str
    p_yes: float
    given: list[Answer] = Field(default_factory=list)


class FrequencyRequest(ProvenanceFields):
    node: str
    frequency: float



def _pairs(answers: list[Answer]) -> list[tuple[str, str]]:
    return [(a.heading, a.answer) for a in answers]



@router.get("/tree")
def tree(root: Root) -> dict[str, Any]:
    return {
        "elements": et.get_elements(root=root),
        "structure": et.get_structure(root=root).model_dump(mode="json"),
        "probabilities": et.get_probabilities(root=root).model_dump(mode="json")["entries"],
        "frequencies": et.get_frequencies(root=root).model_dump(mode="json")["entries"],
    }


@router.post("/element")
def set_element(body: ElementRequest, root: Root) -> dict[str, Any]:
    target_id, sha = et.set_element(body.node, body.element, root=root)
    return {"result": {"target_id": target_id, "element": body.element}, "commit_sha": sha}


@router.post("/order")
def set_order(body: OrderRequest, root: Root) -> dict[str, Any]:
    store, sha = et.set_order(body.headings, root=root)
    return {"result": store.model_dump(mode="json"), "commit_sha": sha}


@router.post("/sequence")
def set_sequence(body: SequenceRequest, root: Root) -> dict[str, Any]:
    seq, sha = et.set_sequence(body.end_state, _pairs(body.answers), root=root)
    return {"result": seq.model_dump(mode="json"), "commit_sha": sha}


@router.post("/sequence/remove")
def remove_sequence(body: RemoveSequenceRequest, root: Root) -> dict[str, Any]:
    sha = et.remove_sequence(_pairs(body.answers), root=root)
    return {"result": {"removed": True}, "commit_sha": sha}


@router.post("/probability")
def set_probability(body: ProbabilityRequest, root: Root) -> dict[str, Any]:
    entry, sha = et.set_probability(body.node, body.p_yes, given=_pairs(body.given), **body.provenance(), root=root)
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


@router.post("/frequency")
def set_frequency(body: FrequencyRequest, root: Root) -> dict[str, Any]:
    entry, sha = et.set_frequency(body.node, body.frequency, **body.provenance(), root=root)
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


from latris.server.routes import _risk_mc  # noqa: E402

_risk_mc.add_routes(router, "event_tree")


_formalism.add_check_route(router, "event_tree")
_formalism.add_analyse_route(router, et, model_type="event_tree")
