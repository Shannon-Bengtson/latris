"""Equation-model routes — quantities (values, formulas), scenarios, ranges, check and the three analyses.

Mirrors the `eq` CLI surface. Mutations return ``{"result": ..., "commit_sha": sha}``.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from latris.operations import equation_model as eq
from latris.schema.common import ProvenanceOrigin, ProvenanceVerification
from latris.server.deps import Root
from latris.server.routes import _formalism
from latris.server.routes._formalism import ProvenanceFields

router = APIRouter(prefix="/api/eq", tags=["equation_model"])

# Where each route sits in the workflow (schema/workflow.py; rules in docs/engineering/WORKFLOW_STRUCTURE.md).
PLACE = {
    "model": "formalise",
    "set_value": "formalise.values",
    "set_formula": "formalise.values",
    "set_role": "formalise.definitions",
    "remove": "formalise.definitions",
    "set_scenario": "formalise.scenarios",
    "remove_scenario": "formalise.scenarios",
    "set_uncertainty": "formalise.ranges",
    "clear_uncertainty": "formalise.ranges",
    "evaluate": "analyse.base_case",
    "sweep": "analyse.sensitivity",
    "monte_carlo": "analyse.uncertainty",
}


class ValueRequest(ProvenanceFields):
    node: str
    role: Literal["input", "parameter"] | None = None  # omit to keep the factor's role
    value: float
    units: str
    valid_min: float | None = None
    valid_max: float | None = None


class FormulaRequest(ProvenanceFields):
    node: str
    role: Literal["computed", "output"] | None = None  # omit to keep the factor's role
    expression: str
    units: str
    link: bool = True  # add the links the formula needs


class RoleRequest(BaseModel):
    node: str
    role: Literal["input", "parameter", "computed", "output"]


class NodeRequest(BaseModel):
    node: str


class ScenarioRequest(BaseModel):
    name: str
    set: list[str] = Field(min_length=1)  # 'Quantity=value [units]'
    description: str = ""
    reason: str = ""
    origin: ProvenanceOrigin = "human-direct"
    source_id: str | None = None
    verification: ProvenanceVerification = "unverified"


class UncertaintyRequest(BaseModel):
    node: str
    distribution: str
    params: dict[str, float]
    reason: str = ""
    origin: ProvenanceOrigin = "human-direct"
    source_id: str | None = None
    verification: ProvenanceVerification = "unverified"


class EvaluateRequest(BaseModel):
    scenarios: list[str] | None = None  # None: every saved scenario
    set: list[str] = Field(default_factory=list)
    record: bool = True


class SweepRequest(BaseModel):
    input: str | None = None
    target: str | None = None
    low: float | None = None
    high: float | None = None
    steps: int = 25
    record: bool = True


class MonteCarloRequest(BaseModel):
    runs: int = 2000
    seed: int = 1234
    sampling: Literal["lhs", "random"] = "lhs"
    target: str | None = None
    record: bool = True


@router.get("/model")
def model(root: Root) -> dict[str, Any]:
    return eq.snapshot(root=root)


@router.post("/value")
def set_value(body: ValueRequest, root: Root) -> dict[str, Any]:
    entry, sha = eq.set_value(body.node, body.value, body.units, role=body.role, valid_min=body.valid_min,
                              valid_max=body.valid_max, **body.provenance(), root=root)
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


@router.post("/formula")
def set_formula(body: FormulaRequest, root: Root) -> dict[str, Any]:
    entry, sha = eq.set_formula(body.node, body.expression, body.units, role=body.role, link=body.link,
                                **body.provenance(), root=root)
    return {"result": {**entry.model_dump(mode="json"), "reads": eq.formula_reads(entry.expression, root=root)},
            "commit_sha": sha}


@router.post("/role")
def set_role(body: RoleRequest, root: Root) -> dict[str, Any]:
    target_id, sha = eq.set_role(body.node, body.role, root=root)
    return {"result": {"target_id": target_id, "role": body.role}, "commit_sha": sha}


@router.post("/remove")
def remove(body: NodeRequest, root: Root) -> dict[str, Any]:
    target_id, removed, sha = eq.remove(body.node, root=root)
    return {"result": {"target_id": target_id, "rows_removed": removed}, "commit_sha": sha}


@router.post("/scenario")
def set_scenario(body: ScenarioRequest, root: Root) -> dict[str, Any]:
    scenario, sha = eq.set_scenario(body.name, body.set, description=body.description, reason=body.reason,
                                    origin=body.origin, source_id=body.source_id, verification=body.verification,
                                    root=root)
    return {"result": scenario.model_dump(mode="json"), "commit_sha": sha}


@router.delete("/scenario/{name}")
def remove_scenario(name: str, root: Root) -> dict[str, Any]:
    return {"result": {"removed": name}, "commit_sha": eq.remove_scenario(name, root=root)}


@router.post("/uncertainty")
def set_uncertainty(body: UncertaintyRequest, root: Root) -> dict[str, Any]:
    entry, sha = eq.set_uncertainty(body.node, body.distribution, body.params, reason=body.reason,
                                    origin=body.origin, source_id=body.source_id, verification=body.verification,
                                    root=root)
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


@router.post("/uncertainty/clear")
def clear_uncertainty(body: NodeRequest, root: Root) -> dict[str, Any]:
    return {"result": {"cleared": body.node}, "commit_sha": eq.clear_uncertainty(body.node, root=root)}


_formalism.add_check_route(router, "equation_model")


@router.post("/evaluate")
def evaluate(root: Root, body: EvaluateRequest | None = None) -> dict[str, Any]:
    body = body or EvaluateRequest()
    payload = eq.evaluate(scenarios=body.scenarios, set=body.set or None, root=root)
    sha = None
    if body.record and not payload["problems"]:
        sha, payload["run_id"] = eq.record(payload, root=root)
    return {"result": payload, "commit_sha": sha}


@router.post("/sweep")
def sweep(root: Root, body: SweepRequest | None = None) -> dict[str, Any]:
    body = body or SweepRequest()
    payload = eq.sweep(input=body.input, target=body.target, low=body.low, high=body.high, steps=body.steps,
                       root=root)
    sha = None
    if body.record:
        sha, payload["run_id"] = eq.record_sweep(payload, root=root)
    return {"result": payload, "commit_sha": sha}


@router.post("/monte-carlo")
def monte_carlo(root: Root, body: MonteCarloRequest | None = None) -> dict[str, Any]:
    body = body or MonteCarloRequest()
    payload = eq.monte_carlo(runs=body.runs, seed=body.seed, sampling=body.sampling, target=body.target, root=root)
    sha = None
    if body.record:
        sha, payload["run_id"] = eq.record_monte_carlo(payload, root=root)
    return {"result": payload, "commit_sha": sha}
