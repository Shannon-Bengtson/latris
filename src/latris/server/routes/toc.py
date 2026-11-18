"""Theory of Change routes — levels and the pathway check.

Mirrors the `toc` CLI surface. Mutations return ``{"result": ..., "commit_sha":
sha}``; reads return plain data.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from latris.operations import toc
from latris.server.deps import Root

router = APIRouter(prefix="/api/toc", tags=["toc"])


class SetLevelRequest(BaseModel):
    node: str
    level: str


class CheckRequest(BaseModel):
    record: bool = True


@router.get("/levels")
def list_levels(root: Root) -> dict[str, Any]:
    levels = toc.get_levels(root=root)
    return {"levels": levels, "order": list(toc.LEVELS), "names": toc.LEVEL_NAMES, "count": len(levels)}


@router.post("/level")
def set_level(body: SetLevelRequest, root: Root) -> dict[str, Any]:
    target_id, sha = toc.set_level(body.node, body.level, root=root)
    return {"result": {"target_id": target_id, "level": body.level}, "commit_sha": sha}


@router.post("/check")
def check(root: Root, body: CheckRequest | None = None) -> dict[str, Any]:
    payload, sha = toc.check(record=body.record if body else True, root=root)
    return {"result": payload, "commit_sha": sha}


# ── process tracing ─────────────────────────────────────────────────


class PriorRequest(BaseModel):
    link: str
    prior: float
    source_id: str | None = None
    origin: str = "human-direct"
    verification: str = "unverified"
    notes: str | None = None


class TestRequest(BaseModel):
    link: str
    name: str
    p_if_true: float | None = None
    p_if_false: float | None = None
    found: bool | None = None
    clear_found: bool = False  # set found back to "not yet looked for"
    description: str | None = None
    notes: str | None = None
    source_id: str | None = None
    origin: str | None = None
    verification: str | None = None
    remove: bool = False


@router.get("/trace")
def get_trace(root: Root) -> dict[str, Any]:
    from latris.operations import process_tracing as pt

    return {"priors": pt.get_priors(root=root).model_dump(mode="json")["entries"],
            "tests": pt.get_tests(root=root).model_dump(mode="json")["entries"]}


@router.post("/prior")
def set_prior(body: PriorRequest, root: Root) -> dict[str, Any]:
    from latris.operations import process_tracing as pt

    entry, sha = pt.set_prior(body.link, body.prior, origin=body.origin, source_id=body.source_id,  # type: ignore[arg-type]
                              verification=body.verification, notes=body.notes, root=root)  # type: ignore[arg-type]
    return {"result": entry.model_dump(mode="json"), "commit_sha": sha}


@router.post("/test")
def set_test(body: TestRequest, root: Root) -> dict[str, Any]:
    from latris.operations import process_tracing as pt

    if body.remove:
        return {"result": {"removed": body.name}, "commit_sha": pt.remove_test(body.link, body.name, root=root)}
    kw = {k: v for k, v in body.model_dump(exclude={"link", "name", "remove", "clear_found"}).items()
          if v is not None}
    if body.clear_found:
        kw["found"] = None
    entry, sha = pt.set_test(body.link, body.name, root=root, **kw)
    return {"result": entry.model_dump(mode="json") | {"type": pt.classify(entry.p_if_true, entry.p_if_false)},
            "commit_sha": sha}


@router.post("/trace")
def trace(root: Root, body: CheckRequest | None = None) -> dict[str, Any]:
    from latris.operations import process_tracing as pt

    payload, sha = pt.trace(record=body.record if body else True, root=root)
    return {"result": payload, "commit_sha": sha}


class ImpactRequest(BaseModel):
    outcome: str
    dataset: str
    time: str
    at: str | float
    group: str | None = None
    treated: list[str] = []
    column: str | None = None
    record: bool = True


@router.post("/impact")
def impact(body: ImpactRequest, root: Root) -> dict[str, Any]:
    from latris.operations import impact as ops

    payload = ops.estimate(body.outcome, body.dataset, time=body.time, at=body.at, group=body.group,
                           treated=body.treated or None, column=body.column, root=root)
    sha = None
    if body.record:
        sha, payload["run_id"] = ops.record(payload, root=root)
    return {"result": payload, "commit_sha": sha}
