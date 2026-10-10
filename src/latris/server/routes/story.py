"""Story (Communicate phase) routes — draft, prose, emphasis, HTML export."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from latris.server.deps import get_project_root

router = APIRouter(prefix="/api/story", tags=["story"])
Root = Annotated[Path, Depends(get_project_root)]

_DEFAULT_SECTIONS = ["key_findings", "answer_to_question", "open_questions", "implications"]


class DraftBody(BaseModel):
    model_type: str
    include_sections: list[str] | None = None
    prompt: str = ""
    source_report_selection: list[str] = []


class ProseBody(BaseModel):
    prose: str


class EmphasisBody(BaseModel):
    node_ids: list[str] = []
    edge_ids: list[str] = []
    loop_ids: list[str] = []


class ReorderBody(BaseModel):
    ordered_beat_ids: list[str]


@router.get("")
def get_story(root: Root, model_type: str = Query(...)) -> dict[str, Any]:
    """Return the story for a model type (null if none drafted yet)."""
    from latris.operations.story import load_story

    store = load_story(root=root)
    doc = next((d for d in store.docs if d.model_type == model_type), None)
    return {"result": doc.model_dump(mode="json") if doc else None}


@router.post("/draft")
def draft(body: DraftBody, root: Root) -> dict[str, Any]:
    """Build (or rebuild) the beat skeleton, seeded from the Report selection."""
    from latris.operations.story import draft_story
    from latris.schema.story import StoryGenerationRequest

    req = StoryGenerationRequest(
        include_sections=body.include_sections or list(_DEFAULT_SECTIONS),
        prompt=body.prompt,
        source_report_selection=body.source_report_selection,
    )
    doc, sha = draft_story(body.model_type, req, root=root)
    return {"result": doc.model_dump(mode="json"), "commit_sha": sha}


@router.post("/{model_type}/beats/{beat_id}/generate-prose")
def generate_prose(model_type: str, beat_id: str, root: Root) -> dict[str, Any]:
    """Generate public-register prose for a beat (the op handles cwd for the AI call)."""
    from latris.operations.story import generate_beat_prose

    beat, sha = generate_beat_prose(model_type, beat_id, root=root)
    return {"result": beat.model_dump(mode="json"), "commit_sha": sha}


@router.patch("/{model_type}/beats/{beat_id}/prose")
def set_prose(model_type: str, beat_id: str, body: ProseBody, root: Root) -> dict[str, Any]:
    """Save a human edit to a beat's prose."""
    from latris.operations.story import set_beat_prose

    beat, sha = set_beat_prose(model_type, beat_id, body.prose, root=root)
    return {"result": beat.model_dump(mode="json"), "commit_sha": sha}


@router.put("/{model_type}/beats/{beat_id}/emphasis")
def set_emphasis(model_type: str, beat_id: str, body: EmphasisBody, root: Root) -> dict[str, Any]:
    """Set a beat's emphasis (loop IDs expand into member node/edge IDs)."""
    from latris.operations.story import set_emphasis as _set_emphasis

    beat, sha = _set_emphasis(
        model_type,
        beat_id,
        node_ids=body.node_ids,
        edge_ids=body.edge_ids,
        loop_ids=body.loop_ids,
        root=root,
    )
    return {"result": beat.model_dump(mode="json"), "commit_sha": sha}


@router.post("/{model_type}/reorder")
def reorder(model_type: str, body: ReorderBody, root: Root) -> dict[str, Any]:
    """Reorder a story's beats."""
    from latris.operations.story import reorder_beats

    doc, sha = reorder_beats(model_type, body.ordered_beat_ids, root=root)
    return {"result": doc.model_dump(mode="json"), "commit_sha": sha}


@router.get("/export")
def export_story(
    root: Root,
    model_type: str = Query(...),
    theme: str | None = Query(None),
) -> StreamingResponse:
    """Render the story to self-contained HTML and stream it as a download."""
    from latris.exporters import story_html
    from latris.repo.layout import ProjectPaths

    html = story_html.render(ProjectPaths(root), model_type, theme=theme)
    buf = BytesIO(html.encode("utf-8"))
    return StreamingResponse(
        buf,
        media_type="text/html",
        headers={"Content-Disposition": f'attachment; filename="story-{model_type}.html"'},
    )
