"""Declared analyses, for surfaces that generate their run controls (the editor's analysis forms).

``GET /api/analyses`` lists a model type's analyses with each one's option schema (see
``capabilities.analysis_catalog``), ``GET /api/analyses/choices`` the project's values for those options,
and ``POST /api/analyses/run`` runs and records one from the options filled in.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Query

from latris.operations import analysis_inputs
from latris.operations.capabilities import analysis_catalog
from latris.server.deps import Root

router = APIRouter(prefix="/api/analyses", tags=["analyses"])


@router.get("")
def list_analyses(model_type: str = Query(...)) -> dict[str, Any]:
    """The analyses ``model_type`` declares: result kind, title, the analysis kind and its options' schema
    (each option described and marked ``x-input``), chart kinds, whether it needs a dataset."""
    return {"analyses": analysis_catalog(model_type)}


@router.get("/choices")
def choices(root: Root, model_type: str = Query(...)) -> dict[str, Any]:
    """The factors, states, saved scenarios and datasets ``model_type``'s analysis options choose from."""
    return analysis_inputs.choices(model_type, root=root)


_EXAMPLE = {"kind": "dag_estimate", "treatment": "Smoking", "outcome": "Cancer", "dataset": "survey"}


@router.post("/run")
def run(root: Root, options: dict[str, Any] = Body(..., examples=[_EXAMPLE])) -> dict[str, Any]:
    """Run and record one analysis: ``kind`` plus its options, as in a build spec's ``analyses``. The result
    is recorded, so it shows in the report and the results list; ``run_id`` names it."""
    return {"result": {"run_id": analysis_inputs.run(options, root=root)}, "commit_sha": None}
