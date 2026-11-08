"""Recorded results routes — what reports show, and hiding results from them.

Mirrors the `results` CLI surface.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from latris.operations import analysis_results as ar
from latris.server.deps import get_project_root

router = APIRouter(prefix="/api/results", tags=["results"])
Root = Annotated[Path, Depends(get_project_root)]


@router.get("")
def list_results(root: Root, all: bool = False) -> dict[str, Any]:  # noqa: A002 - query parameter name
    shown = {r.run.id: r for r in ar.report_results(root=root)}
    rows = []
    for run, hidden, stale in ar.list_results(root=root):
        if not all and run.id not in shown:
            continue
        rows.append({
            "run": run.model_dump(mode="json"), "in_reports": run.id in shown, "hidden": hidden, "out_of_date": stale,
        })
    return {"results": rows, "count": len(rows)}


@router.get("/{run_id}")
def get_result(run_id: str, root: Root) -> dict[str, Any]:
    try:
        run, payload = ar.get_result(run_id, root=root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"run": run.model_dump(mode="json"), "result": payload}


@router.post("/{run_id}/hide")
def hide(run_id: str, root: Root) -> dict[str, Any]:
    return _set(run_id, True, root)


@router.post("/{run_id}/unhide")
def unhide(run_id: str, root: Root) -> dict[str, Any]:
    return _set(run_id, False, root)


def _set(run_id: str, hidden: bool, root: Path) -> dict[str, Any]:
    try:
        run, sha = ar.set_hidden(run_id, hidden, root=root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"result": {"run_id": run.id, "hidden": hidden}, "commit_sha": sha}
