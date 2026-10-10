"""Canvas layout persistence — GET/PUT for node positions and sizes."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import yaml
from fastapi import APIRouter, Depends

from latris.repo.layout import ProjectPaths
from latris.schema.layout_ui import CanvasLayout
from latris.server.deps import get_project_root

router = APIRouter(prefix="/api/layout", tags=["layout"])
Root = Annotated[Path, Depends(get_project_root)]


@router.get("")
def get_layout(root: Root) -> dict[str, Any]:
    paths = ProjectPaths(root)
    layout_file = paths.layout_dir / "canvas.layout.yaml"
    if not layout_file.exists():
        return CanvasLayout().model_dump(mode="json")
    raw = yaml.safe_load(layout_file.read_text(encoding="utf-8")) or {}
    return CanvasLayout.model_validate(raw).model_dump(mode="json")


@router.put("")
def put_layout(body: CanvasLayout, root: Root) -> dict[str, str]:
    paths = ProjectPaths(root)
    paths.layout_dir.mkdir(parents=True, exist_ok=True)
    layout_file = paths.layout_dir / "canvas.layout.yaml"
    layout_file.write_text(
        yaml.dump(body.model_dump(mode="json", exclude_none=True), default_flow_style=False),
        encoding="utf-8",
    )
    return {"status": "ok"}
