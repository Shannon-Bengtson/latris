"""The workflow structure: stages, steps and tracks (``schema/workflow.py``).

A surface reads its navigation, groupings and headings from here instead of keeping its own list. Registry
only: no project needed.
"""

from __future__ import annotations

from fastapi import APIRouter

from latris.schema.workflow import WorkflowStructure, structure

router = APIRouter(prefix="/api/workflow", tags=["workflow"])

# Where each route sits in the workflow (schema/workflow.py; rules in docs/engineering/WORKFLOW_STRUCTURE.md).
PLACE = "project"


@router.get("", response_model=WorkflowStructure)
def get_workflow() -> WorkflowStructure:
    """Every stage with its steps, in order, and every track."""
    return structure()
