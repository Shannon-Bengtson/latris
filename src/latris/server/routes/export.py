"""Export endpoints — Markdown and DOT.

The polished formats (Word, review pack, story HTML) are served by the
Latris app through the server plugin hook, at /api/export/word,
/api/export/review and /api/story/export."""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse

from latris.exporters import dot as dot_exporter
from latris.exporters import markdown as md_exporter
from latris.repo.layout import ProjectPaths
from latris.server.deps import Root

router = APIRouter(prefix="/api/export", tags=["export"])


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


@router.get("/spec")
def export_spec(root: Root, model_type: str | None = Query(None)) -> dict:
    """The model as a build spec (what ``latris export spec`` prints and ``POST /api/build`` reads back):
    factors, links, sources, ``model_type``'s values (default: the first chosen) and its analyses."""
    from latris.operations.share_link import export_spec as export
    from latris.operations.share_link import spec_data

    _, spec = export(model_type=model_type, root=root)
    return spec_data(spec)
