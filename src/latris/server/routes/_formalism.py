"""Pieces every formalism router shares: provenance fields, `/check` and `/analyse`."""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from latris.schema.common import ProvenanceOrigin, ProvenanceVerification
from latris.server.deps import Root


class ProvenanceFields(BaseModel):
    """Where a number came from — the fields every parameter-setting request takes."""

    origin: ProvenanceOrigin = "human-direct"
    source_id: str | None = None
    verification: ProvenanceVerification = "unverified"
    notes: str | None = None

    def provenance(self) -> dict[str, Any]:
        """The fields as keyword arguments for an operation."""
        return {"origin": self.origin, "source_id": self.source_id, "verification": self.verification,
                "notes": self.notes}


class AnalyseRequest(BaseModel):
    record: bool = True


def _no_problems(payload: dict[str, Any]) -> bool:
    return not payload["problems"]


def add_check_route(router: APIRouter, model_type: str) -> None:
    """``GET /check``: whether the model is ready, and the gaps if not."""
    from latris.operations.readiness import assess_readiness

    @router.get("/check")
    def check(root: Root) -> dict[str, Any]:
        r = assess_readiness(model_type, root=root)
        return {"ready": r.can_switch, "gaps": [
            {"element_id": g.element_id, "element_label": g.element_label, "gap_type": g.gap_type,
             "message": g.message}
            for g in r.gaps
        ]}


def add_analyse_route(
    router: APIRouter,
    ops: ModuleType,
    *,
    request: type[AnalyseRequest] = AnalyseRequest,
    options: Callable[[Any], dict[str, Any]] = lambda _body: {},
    recordable: Callable[[dict[str, Any]], bool] = _no_problems,
) -> None:
    """``POST /analyse``: run ``ops.analyse`` and, unless asked not to, record it.

    ``options`` turns the request body into extra ``analyse`` arguments;
    the result is recorded only when ``recordable(payload)``.
    """

    def analyse(root: Root, body: AnalyseRequest | None = None) -> dict[str, Any]:
        body = body or request()
        payload = ops.analyse(root=root, **options(body))
        sha = None
        if body.record and recordable(payload):
            sha, payload["run_id"] = ops.record(payload, root=root)
        return {"result": payload, "commit_sha": sha}

    # The body type is this formalism's request class; annotations are strings
    # here (``from __future__``), so give FastAPI the real type.
    analyse.__annotations__["body"] = request | None
    router.post("/analyse")(analyse)
