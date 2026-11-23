"""Contract and predict routes — a model's inputs and outputs, and running it on values a caller gives.

Mirrors the `contract` and `predict` CLI. `POST /api/predict` computes and returns; it records nothing.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from latris.operations import contract, predict
from latris.server.deps import Root

router = APIRouter(prefix="/api", tags=["contract"])


class InitRequest(BaseModel):
    model_type: str
    replace: bool = False


class InputRequest(BaseModel):
    """Only the fields sent change."""

    model_type: str
    node: str
    name: str | None = None
    units: str | None = None
    default: float | str | None = None
    valid_min: float | None = None
    valid_max: float | None = None
    mode: Literal["observe", "set"] | None = None
    required: bool | None = None
    description: str | None = None


class OutputRequest(BaseModel):
    model_type: str
    node: str
    name: str | None = None
    kind: Literal["value", "series", "distribution"] | None = None
    metric: str | None = None
    description: str | None = None


class PredictRequest(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)  # contract input name → number, "250 cm" or a state
    model_type: str | None = None
    ref: str | None = None  # a commit, a milestone's name or a version's name; omit for the project as it is
    require: Literal["reviewed", "approved"] | None = None


@router.get("/contract/types")
def types(root: Root) -> dict[str, Any]:
    """Which model types can have a contract, and which have one here."""
    from latris.operations import formalisms
    from latris.repo.project import require_project

    return {"available": [f.model_type for f in formalisms.all_formalisms() if f.predictor],
            "declared": contract.model_types(require_project(root))}


@router.get("/contract")
def show(root: Root, model_type: str | None = None, ref: str | None = None) -> dict[str, Any]:
    return predict.load(model_type=model_type, ref=ref, root=root).describe()


@router.get("/contract/candidates")
def candidates(model_type: str, root: Root) -> dict[str, Any]:
    return contract.candidates(model_type, root=root)


@router.get("/contract/check")
def check(root: Root, model_type: str | None = None) -> dict[str, Any]:
    problems = contract.check(model_type, root=root)
    return {"ready": not problems, "problems": problems}


@router.get("/contract/compare")
def compare(base: str, root: Root, head: str | None = None, model_type: str | None = None) -> dict[str, Any]:
    return contract.compare(base, head, model_type=model_type, root=root)


@router.post("/contract/init")
def init(body: InitRequest, root: Root) -> dict[str, Any]:
    _, sha = contract.init(body.model_type, replace=body.replace, root=root)
    return {"result": contract.describe(body.model_type, root=root), "commit_sha": sha}


@router.post("/contract/input")
def set_input(body: InputRequest, root: Root) -> dict[str, Any]:
    sent = body.model_dump(exclude={"model_type", "node"}, exclude_unset=True)
    plain = {k: sent.pop(k) for k in ("name", "units", "mode", "required", "description") if sent.get(k) is not None}
    entry, sha = contract.set_input(body.model_type, body.node, **plain,
                                    **{k: v for k, v in sent.items() if k in ("default", "valid_min", "valid_max")},
                                    root=root)
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


@router.post("/contract/output")
def set_output(body: OutputRequest, root: Root) -> dict[str, Any]:
    entry, sha = contract.set_output(body.model_type, body.node, name=body.name, kind=body.kind, metric=body.metric,
                                     description=body.description, root=root)
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


@router.delete("/contract/{model_type}/{name}")
def remove(model_type: str, name: str, root: Root) -> dict[str, Any]:
    return {"result": {"removed": name}, "commit_sha": contract.remove(model_type, name, root=root)}


@router.post("/predict")
def run(body: PredictRequest, root: Root) -> dict[str, Any]:
    return predict.predict(body.inputs, model_type=body.model_type, ref=body.ref, require=body.require, root=root)
