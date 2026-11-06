"""Export endpoints — Markdown and DOT.

The polished formats (Word, review pack, story HTML) are served by the
Latris app through the server plugin hook, at /api/export/word,
/api/export/review and /api/story/export."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse

from latris.exporters import dot as dot_exporter
from latris.exporters import markdown as md_exporter
from latris.repo.layout import ProjectPaths
from latris.server.deps import get_project_root

router = APIRouter(prefix="/api/export", tags=["export"])
Root = Annotated[Path, Depends(get_project_root)]


@router.get("/markdown")
def export_markdown(
    root: Root,
    sections: list[str] | None = Query(default=None),
    model_type: str | None = Query(default=None),
) -> PlainTextResponse:
    paths = ProjectPaths(root)
    content = md_exporter.render(paths, sections=sections, model_type=model_type)
    return PlainTextResponse(content, media_type="text/markdown")


@router.get("/dot")
def export_dot(root: Root, view: str = "system_map") -> PlainTextResponse:
    paths = ProjectPaths(root)
    content = dot_exporter.render(paths, view=view)
    return PlainTextResponse(content, media_type="text/plain")
