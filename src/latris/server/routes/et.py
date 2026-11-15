"""Event tree routes — elements, order, sequences, probabilities, frequency, check, analysis.

Mirrors the `et` CLI surface. Mutations return ``{"result": ..., "commit_sha":
sha}``; reads return plain data. Answers are ``{"heading": ..., "answer": "yes"|"no"}``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from latris.operations import event_tree as et
from latris.operations.readiness import assess_readiness
from latris.schema.common import ProvenanceOrigin, ProvenanceVerification
from latris.server.deps import get_project_root

router = APIRouter(prefix="/api/et", tags=["et"])
Root = Annotated[Path, Depends(get_project_root)]


def _bad(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


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


class ProbabilityRequest(BaseModel):
    node: str
    p_yes: float
    given: list[Answer] = Field(default_factory=list)
    origin: ProvenanceOrigin = "human-direct"
    source_id: str | None = None
    verification: ProvenanceVerification = "unverified"
    notes: str | None = None


class FrequencyRequest(BaseModel):
    node: str
    frequency: float
    origin: ProvenanceOrigin = "human-direct"
    source_id: str | None = None
    verification: ProvenanceVerification = "unverified"
    notes: str | None = None


class AnalyseRequest(BaseModel):
    record: bool = True


def _pairs(answers: list[Answer]) -> list[tuple[str, str]]:
    return [(a.heading, a.answer) for a in answers]


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except (ValueError, LookupError) as exc:
        raise _bad(exc) from exc


@router.get("/tree")
def tree(root: Root) -> dict[str, Any]:
    return {
        "elements": et.get_elements(root=root),
        "structure": et.get_structure(root=root).model_dump(mode="json"),
        "probabilities": et.get_probabilities(root=root).model_dump(mode="json")["entries"],
        "frequencies": et.get_frequencies(root=root).model_dump(mode="json")["entries"],
    }


@router.get("/check")
def check(root: Root) -> dict[str, Any]:
    r = assess_readiness("event_tree", root=root)
    return {"ready": r.can_switch, "gaps": [
        {"element_id": g.element_id, "element_label": g.element_label, "gap_type": g.gap_type, "message": g.message}
        for g in r.gaps
    ]}


@router.post("/element")
def set_element(body: ElementRequest, root: Root) -> dict[str, Any]:
    target_id, sha = _call(et.set_element, body.node, body.element, root=root)
    return {"result": {"target_id": target_id, "element": body.element}, "commit_sha": sha}


@router.post("/order")
def set_order(body: OrderRequest, root: Root) -> dict[str, Any]:
    store, sha = _call(et.set_order, body.headings, root=root)
    return {"result": store.model_dump(mode="json"), "commit_sha": sha}


@router.post("/sequence")
def set_sequence(body: SequenceRequest, root: Root) -> dict[str, Any]:
    seq, sha = _call(et.set_sequence, body.end_state, _pairs(body.answers), root=root)
    return {"result": seq.model_dump(mode="json"), "commit_sha": sha}


@router.post("/sequence/remove")
def remove_sequence(body: RemoveSequenceRequest, root: Root) -> dict[str, Any]:
    sha = _call(et.remove_sequence, _pairs(body.answers), root=root)
    return {"result": {"removed": True}, "commit_sha": sha}


@router.post("/probability")
def set_probability(body: ProbabilityRequest, root: Root) -> dict[str, Any]:
    entry, sha = _call(et.set_probability, body.node, body.p_yes, given=_pairs(body.given), origin=body.origin,
                       source_id=body.source_id, verification=body.verification, notes=body.notes, root=root)
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


@router.post("/frequency")
def set_frequency(body: FrequencyRequest, root: Root) -> dict[str, Any]:
    entry, sha = _call(et.set_frequency, body.node, body.frequency, origin=body.origin, source_id=body.source_id,
                       verification=body.verification, notes=body.notes, root=root)
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


@router.post("/analyse")
def analyse(root: Root, body: AnalyseRequest | None = None) -> dict[str, Any]:
    body = body or AnalyseRequest()
    payload = et.analyse(root=root)
    sha = None
    if body.record and not payload["problems"]:
        sha, payload["run_id"] = et.record(payload, root=root)
    return {"result": payload, "commit_sha": sha}
