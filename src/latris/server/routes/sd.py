"""System Dynamics routes — roles, equations, values, tables, readiness check, simulation.

Mirrors the `sd` CLI surface. Mutations return ``{"result": ..., "commit_sha":
sha}``; reads return plain data. All operations receive the injected project
root explicitly.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from latris.operations import sd as sd_ops
from latris.operations import sd_scenarios, uncertainty
from latris.server.deps import get_project_root

router = APIRouter(prefix="/api/sd", tags=["sd"])
Root = Annotated[Path, Depends(get_project_root)]


def _bad_request(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


# ── roles ────────────────────────────────────────────────────────────


class SetRoleRequest(BaseModel):
    node: str
    role: str


@router.get("/roles")
def list_roles(root: Root) -> dict[str, Any]:
    store = sd_ops.get_roles(root=root)
    return {"roles": store.model_dump(mode="json")["entries"], "count": len(store.entries)}


@router.post("/role")
def set_role(body: SetRoleRequest, root: Root) -> dict[str, Any]:
    try:
        target_id, sha = sd_ops.set_role(body.node, body.role, root=root)
    except ValueError as exc:
        raise _bad_request(exc) from exc
    return {"result": {"target_id": target_id, "role": body.role}, "commit_sha": sha}


# ── equations ────────────────────────────────────────────────────────


class SetEquationRequest(BaseModel):
    node: str
    expression: str
    units: str
    origin: str = "human-direct"
    source_id: str | None = None


@router.get("/equations")
def list_equations(root: Root) -> dict[str, Any]:
    store = sd_ops.get_equations(root=root)
    return {"equations": store.model_dump(mode="json")["entries"], "count": len(store.entries)}


@router.post("/equation")
def set_equation(body: SetEquationRequest, root: Root) -> dict[str, Any]:
    try:
        entry, sha = sd_ops.set_equation(
            body.node, body.expression, body.units, origin=body.origin, source_id=body.source_id, root=root
        )
    except ValueError as exc:
        raise _bad_request(exc) from exc
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


# ── stocks + constants ───────────────────────────────────────────────


class SetInitialValueRequest(BaseModel):
    node: str
    value: float
    units: str
    non_negative: bool = False
    origin: str = "human-direct"
    source_id: str | None = None


@router.get("/stocks")
def list_stocks(root: Root) -> dict[str, Any]:
    store = sd_ops.get_stocks(root=root)
    return {"stocks": store.model_dump(mode="json")["entries"], "count": len(store.entries)}


@router.post("/stocks")
def set_initial_value(body: SetInitialValueRequest, root: Root) -> dict[str, Any]:
    try:
        entry, sha = sd_ops.set_initial_value(
            body.node, body.value, body.units, non_negative=body.non_negative,
            origin=body.origin, source_id=body.source_id, root=root,
        )
    except ValueError as exc:
        raise _bad_request(exc) from exc
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


class SetConstantRequest(BaseModel):
    node: str
    value: float
    units: str
    origin: str = "human-direct"
    source_id: str | None = None


@router.get("/constants")
def list_constants(root: Root) -> dict[str, Any]:
    store = sd_ops.get_constants(root=root)
    return {"constants": store.model_dump(mode="json")["entries"], "count": len(store.entries)}


@router.post("/constants")
def set_constant(body: SetConstantRequest, root: Root) -> dict[str, Any]:
    try:
        entry, sha = sd_ops.set_constant(
            body.node, body.value, body.units, origin=body.origin, source_id=body.source_id, root=root
        )
    except ValueError as exc:
        raise _bad_request(exc) from exc
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


# ── tables ───────────────────────────────────────────────────────────


class TablePointIn(BaseModel):
    x: float
    y: float


class SetTableRequest(BaseModel):
    node: str
    points: list[TablePointIn]
    x_units: str
    y_units: str
    extrapolate: Literal["clamp", "linear"] = "clamp"
    origin: str = "human-elicited"
    source_id: str | None = None


@router.get("/tables")
def list_tables(root: Root) -> dict[str, Any]:
    store = sd_ops.get_tables(root=root)
    return {"tables": store.model_dump(mode="json")["entries"], "count": len(store.entries)}


@router.post("/tables")
def set_table(body: SetTableRequest, root: Root) -> dict[str, Any]:
    try:
        entry, sha = sd_ops.set_table(
            body.node, [(p.x, p.y) for p in body.points], body.x_units, body.y_units,
            extrapolate=body.extrapolate, origin=body.origin, source_id=body.source_id, root=root,
        )
    except ValueError as exc:
        raise _bad_request(exc) from exc
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


# ── readiness ────────────────────────────────────────────────────────


@router.get("/check")
def check(root: Root) -> dict[str, Any]:
    gaps = sd_ops.check(root=root)
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


# ── simulation ───────────────────────────────────────────────────────


class SimulateRequest(BaseModel):
    initial_time: float | None = None
    final_time: float | None = None
    dt: float | None = None
    saveper: float | None = None
    method: Literal["euler", "rk2", "rk4", "adaptive"] | None = None
    time_units: str | None = None
    scenarios: list[str] = []
    set: list[str] = []
    record: bool = True


@router.post("/simulate")
def simulate(body: SimulateRequest, root: Root) -> dict[str, Any]:
    """Run the baseline (plus any scenarios). ``result`` is the baseline run; ``comparison`` has every run."""
    try:
        payload, runs = sd_ops.simulate_scenarios(
            body.scenarios, body.set,
            initial_time=body.initial_time, final_time=body.final_time, dt=body.dt, saveper=body.saveper,
            method=body.method, time_units=body.time_units, root=root,
        )
    except ValueError as exc:
        raise _bad_request(exc) from exc
    out: dict[str, Any] = {"result": asdict(runs[0].result), "comparison": payload}
    if body.record:
        sha, run_id = sd_ops.record_comparison(payload, runs, root=root)
        out["commit_sha"] = sha
        out["run_id"] = run_id
    return out


# ── scenarios ────────────────────────────────────────────────────────


class ScenarioRequest(BaseModel):
    name: str
    set: list[str]
    description: str = ""
    reason: str = ""
    source_id: str | None = None
    origin: str = "human-direct"


@router.get("/scenarios")
def list_scenarios(root: Root) -> dict[str, Any]:
    items = sd_scenarios.list_scenarios(root=root)
    return {"scenarios": [s.model_dump(mode="json") for s in items], "count": len(items)}


@router.post("/scenario")
def set_scenario(body: ScenarioRequest, root: Root) -> dict[str, Any]:
    try:
        scenario, sha = sd_scenarios.set_scenario(
            body.name, body.set, description=body.description, reason=body.reason,
            source_id=body.source_id, origin=body.origin, root=root,  # type: ignore[arg-type]
        )
    except ValueError as exc:
        raise _bad_request(exc) from exc
    return {"result": scenario.model_dump(mode="json"), "commit_sha": sha}


@router.delete("/scenario/{name}")
def remove_scenario(name: str, root: Root) -> dict[str, Any]:
    try:
        sha = sd_scenarios.remove_scenario(name, root=root)
    except ValueError as exc:
        raise _bad_request(exc) from exc
    return {"result": {"removed": name}, "commit_sha": sha}


# ── uncertainty, Monte Carlo, sensitivity ────────────────────────────


class UncertaintyRequest(BaseModel):
    target: str
    distribution: str
    params: dict[str, float]
    reason: str = ""
    source_id: str | None = None
    origin: str = "human-direct"


class RunSettings(BaseModel):
    final_time: float | None = None
    dt: float | None = None
    saveper: float | None = None
    method: Literal["euler", "rk2", "rk4", "adaptive"] | None = None

    def kwargs(self) -> dict[str, Any]:
        fields = ("final_time", "dt", "saveper", "method")
        return {k: getattr(self, k) for k in fields if getattr(self, k) is not None}


class MonteCarloRequest(RunSettings):
    runs: int = 200
    seed: int = 1234
    sampling: Literal["lhs", "random"] = "lhs"
    variables: list[str] | None = None
    scenario: str | None = None
    max_seconds: float = 60.0
    record: bool = True


class SensitivityRequest(RunSettings):
    variable: str
    metric: str = "final"
    pct: float = 10.0
    scenario: str | None = None
    record: bool = True


@router.get("/uncertainty")
def list_uncertainty(root: Root) -> dict[str, Any]:
    entries = uncertainty.list_uncertainty(root=root)
    return {"uncertainty": [e.model_dump(mode="json") for e in entries], "count": len(entries)}


@router.post("/uncertainty")
def set_uncertainty(body: UncertaintyRequest, root: Root) -> dict[str, Any]:
    try:
        entry, sha = uncertainty.set_uncertainty(
            body.target, body.distribution, body.params, reason=body.reason, source_id=body.source_id,
            origin=body.origin, root=root,  # type: ignore[arg-type]
        )
    except ValueError as exc:
        raise _bad_request(exc) from exc
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


@router.delete("/uncertainty/{target}")
def clear_uncertainty(target: str, root: Root) -> dict[str, Any]:
    try:
        sha = uncertainty.clear_uncertainty(target, root=root)
    except ValueError as exc:
        raise _bad_request(exc) from exc
    return {"result": {"cleared": target}, "commit_sha": sha}


@router.post("/monte-carlo")
def monte_carlo(body: MonteCarloRequest, root: Root) -> dict[str, Any]:
    try:
        payload = sd_ops.run_monte_carlo(
            runs=body.runs, seed=body.seed, sampling=body.sampling, variables=body.variables,
            scenario=body.scenario, max_seconds=body.max_seconds, settings=body.kwargs(), root=root,
        )
    except ValueError as exc:
        raise _bad_request(exc) from exc
    out: dict[str, Any] = {"result": payload}
    if body.record:
        out["commit_sha"], out["run_id"] = sd_ops.record_monte_carlo(payload, root=root)
    return out


@router.post("/sensitivity")
def sensitivity(body: SensitivityRequest, root: Root) -> dict[str, Any]:
    try:
        payload = sd_ops.run_sensitivity(
            body.variable, metric=body.metric, pct=body.pct, scenario=body.scenario, settings=body.kwargs(),
            root=root,
        )
    except ValueError as exc:
        raise _bad_request(exc) from exc
    out: dict[str, Any] = {"result": payload}
    if body.record:
        out["commit_sha"], out["run_id"] = sd_ops.record_sensitivity(payload, root=root)
    return out
