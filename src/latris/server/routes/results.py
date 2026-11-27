"""Recorded results routes — what reports show, and hiding results from them.

Mirrors the `results` CLI surface.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter

from latris.exporters.results import result_heading
from latris.operations import analysis_results as ar
from latris.server.deps import Root

router = APIRouter(prefix="/api/results", tags=["results"])

# Where each route sits in the workflow (schema/workflow.py; rules in docs/engineering/WORKFLOW_STRUCTURE.md).
PLACE = {
    "*": "analyse",
    "hide": "communicate.report",
    "unhide": "communicate.report",
}


@router.get("")
def list_results(root: Root, all: bool = False) -> dict[str, Any]:  # noqa: A002 - query parameter name
    """Recorded results — those reports show, or every one with ``all``. Each row carries its model type and
    the heading reports give it (the report's heading needs the payload, so only shown rows have one)."""
    shown = {r.run.id: r for r in ar.report_results(root=root)}
    rows = []
    for run, hidden, stale in ar.list_results(root=root):
        if not all and run.id not in shown:
            continue
        res = shown.get(run.id)
        try:
            heading = result_heading(run.result_kind, res.payload) if res else run.output_summary
        except (KeyError, TypeError, ValueError, IndexError):
            heading = run.output_summary
        rows.append({
            "run": run.model_dump(mode="json"), "in_reports": run.id in shown, "hidden": hidden, "out_of_date": stale,
            "model_type": ar.KIND_MODEL_TYPE.get(run.result_kind, run.target_view or ""), "heading": heading,
        })
    return {"results": rows, "count": len(rows)}


@router.get("/{run_id}")
def get_result(run_id: str, root: Root) -> dict[str, Any]:
    run, payload = ar.get_result(run_id, root=root)
    return {"run": run.model_dump(mode="json"), "result": payload}


@router.post("/{run_id}/hide")
def hide(run_id: str, root: Root) -> dict[str, Any]:
    return _set(run_id, True, root)


@router.post("/{run_id}/unhide")
def unhide(run_id: str, root: Root) -> dict[str, Any]:
    return _set(run_id, False, root)


def _set(run_id: str, hidden: bool, root: Path) -> dict[str, Any]:
    run, sha = ar.set_hidden(run_id, hidden, root=root)
    return {"result": {"run_id": run.id, "hidden": hidden}, "commit_sha": sha}
