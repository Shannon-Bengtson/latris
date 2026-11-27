"""Canvas layout persistence — GET/PUT for node positions and sizes.

The layout file is gitignored by default (coordinates aren't model content),
so a PUT writes it without committing.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import dump_model, load_model_or_default
from latris.schema.layout_ui import CanvasLayout
from latris.server.deps import Root

router = APIRouter(prefix="/api/layout", tags=["layout"])

# Where each route sits in the workflow (schema/workflow.py; rules in docs/engineering/WORKFLOW_STRUCTURE.md).
PLACE = "project"


@router.get("")
def get_layout(root: Root) -> dict[str, Any]:
    return load_model_or_default(CanvasLayout, ProjectPaths(root).canvas_layout_yaml).model_dump(mode="json")


@router.put("")
def put_layout(body: CanvasLayout, root: Root) -> dict[str, str]:
    dump_model(body, ProjectPaths(root).canvas_layout_yaml)
    return {"status": "ok"}
