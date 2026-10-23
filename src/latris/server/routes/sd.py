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
    record: bool = True


@router.post("/simulate")
def simulate(body: SimulateRequest, root: Root) -> dict[str, Any]:
    try:
        result = sd_ops.simulate(
            initial_time=body.initial_time, final_time=body.final_time, dt=body.dt, saveper=body.saveper,
            method=body.method, time_units=body.time_units, root=root,
        )
    except ValueError as exc:
        raise _bad_request(exc) from exc
    out: dict[str, Any] = {"result": asdict(result)}
    if body.record:
        sha, run_id = sd_ops.record_simulation(result, root=root)
        out["commit_sha"] = sha
        out["run_id"] = run_id
    return out
