"""Export endpoints — Markdown, DOT, Word, Review HTML."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse, Response, StreamingResponse

from latris.exporters import dot as dot_exporter
from latris.exporters import markdown as md_exporter
from latris.exporters import review_html as review_exporter
from latris.exporters import word as word_exporter
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
def export_dot(root: Root, view: str = "conceptual") -> PlainTextResponse:
    paths = ProjectPaths(root)
    content = dot_exporter.render(paths, view=view)
    return PlainTextResponse(content, media_type="text/plain")


@router.get("/word")
def export_word(
    root: Root,
    sections: list[str] | None = Query(default=None),
    model_type: str | None = Query(default=None),
) -> StreamingResponse:
    paths = ProjectPaths(root)
    doc = word_exporter.render(paths, sections=sections, model_type=model_type)
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": 'attachment; filename="report.docx"'},
    )


@router.get("/review")
def export_review_html(
    root: Root,
    pack: str = Query(default="review"),
    zip: bool = Query(default=False),
    model_type: str | None = Query(default=None),
) -> Response:
    paths = ProjectPaths(root)
    html = review_exporter.render(paths, pack=pack, model_type=model_type)
    filename = f"review-{paths.root.name}.html"

    if zip:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(filename, html)
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="review-{paths.root.name}.zip"'},
        )

    return Response(
        content=html,
        media_type="text/html",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
