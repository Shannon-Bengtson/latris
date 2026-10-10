"""Self-contained scrollytelling HTML exporter for the Story artifact.

Renders a ``StoryDoc`` to a single HTML file via Jinja2 + a vendored Scrollama
scroll controller + a shipped CSS theme. The model SVG (with addressable
node/edge ids from ``dot.py``) is inlined; scroll-driven highlighting
emphasises each beat's nodes/edges and dims the rest. Falls back to a text
model summary when graphviz is unavailable, and degrades to a readable article
under ``<noscript>``.

No external/network resources: CSS, JS, SVG, and images are all inlined.
See docs/design/STORY.md.
"""

from __future__ import annotations

import base64
import json
import mimetypes
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from latris.exporters.diagram import render_svg
from latris.exporters.story_diagram import render_story_svg
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model
from latris.schema import ProjectFoundation, Substrate
from latris.schema.story import StoryBeat, StoryStore

_TEMPLATE_DIR = Path(__file__).parent / "templates" / "story"


@lru_cache(maxsize=1)
def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "jinja2"]),
    )


def _load_theme(name: str) -> str:
    path = _TEMPLATE_DIR / "themes" / f"{name}.css"
    if not path.exists():
        path = _TEMPLATE_DIR / "themes" / "default.css"
    return path.read_text(encoding="utf-8")


def _load_vendor(name: str) -> str:
    return (_TEMPLATE_DIR / "vendor" / name).read_text(encoding="utf-8")


def _asset_data_uri(paths: ProjectPaths, asset_id: str | None) -> str | None:
    """Base64 data-URI for an uploaded asset (keeps the file self-contained)."""
    if not asset_id:
        return None
    if not paths.story_assets_dir.exists():
        return None
    for f in sorted(paths.story_assets_dir.glob(f"{asset_id}.*")):
        mime = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        b64 = base64.b64encode(f.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{b64}"
    return None


def _beat_view(beat: StoryBeat) -> dict:
    paragraphs = [p.strip() for p in (beat.prose or "").split("\n\n") if p.strip()]
    return {
        "kind": beat.kind,
        "title": beat.title,
        "paragraphs": paragraphs,
        "show_confidence": beat.show_confidence,
        "node_csv": ",".join(beat.emphasis.node_ids),
        "edge_csv": ",".join(beat.emphasis.edge_ids),
    }


def render(paths: ProjectPaths, model_type: str, *, theme: str | None = None) -> str:
    """Render the Story for ``model_type`` to a single self-contained HTML string."""
    store = load_model(StoryStore, paths.story_yaml) if paths.story_yaml.exists() else StoryStore()
    doc = next((d for d in store.docs if d.model_type == model_type), None)
    if doc is None:
        raise ValueError(f"no story for model type {model_type!r}")

    foundation = load_model(ProjectFoundation, paths.project_yaml)
    # Self-render the diagram from the saved canvas layout (no external binary,
    # matches the build canvas). Fall back to graphviz only if that yields
    # nothing, and to the text edge list in the template if both are empty.
    svg = render_story_svg(paths, model_type) or render_svg(paths, view=model_type)

    substrate = load_model(Substrate, paths.conceptual_yaml)
    labels = {e.id: e.label for e in substrate.entities}
    fallback_edges = [
        (labels.get(e.from_id, e.from_id), labels.get(e.to_id, e.to_id), e.kind) for e in substrate.edges
    ]

    coverage_pct: int | None = None
    try:
        from latris.operations.interpret import coverage_ratio

        _cited, _total, ratio = coverage_ratio(model_type, paths)
        coverage_pct = round(ratio * 100)
    except Exception:  # noqa: BLE001 — coverage is a nice-to-have, never block export
        coverage_pct = None

    title_image_data = _asset_data_uri(paths, doc.title_image.asset_id) if doc.title_image else None
    logo_data = (
        _asset_data_uri(paths, doc.brand.logo_asset_id) if doc.brand and doc.brand.logo_asset_id else None
    )

    tmpl = _env().get_template("story.html.jinja2")
    return tmpl.render(
        doc=doc,
        foundation=foundation,
        beats=[_beat_view(b) for b in doc.beats],
        svg=svg,
        fallback_edges=fallback_edges,
        coverage_pct=coverage_pct,
        title_image_data=title_image_data,
        logo_data=logo_data,
        brand=doc.brand,
        theme_css=_load_theme(theme or doc.theme or "default"),
        scrollama_js=_load_vendor("scrollama.min.js"),
        manifest=json.dumps(doc.model_dump(mode="json")),
        source_commit=doc.source_commit[:10],
        export_date=datetime.now(UTC).strftime("%Y-%m-%d"),
    )


def write(paths: ProjectPaths, target: Path, *, model_type: str, theme: str | None = None) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(paths, model_type, theme=theme), encoding="utf-8", newline="")
    return target
