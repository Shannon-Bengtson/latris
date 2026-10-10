"""Tests for the self-contained Story HTML exporter."""

from __future__ import annotations

import pytest

from latris.exporters import story_html
from latris.operations.commit import auto_commit
from latris.operations.edges import add_edge
from latris.operations.findings import record_new_finding
from latris.operations.init import init_project
from latris.operations.nodes import add_node
from latris.operations.story import draft_story, set_beat_prose
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import dump_model, load_model
from latris.schema.project import ProjectFoundation
from latris.schema.story import StoryGenerationRequest


@pytest.fixture
def story_with_prose(tmp_path, git_identity):
    root = tmp_path / "proj"
    init_project(root, statement="What drives water quality decline?")
    paths = ProjectPaths(root)
    f = load_model(ProjectFoundation, paths.project_yaml)
    f.selected_model_types = ["cld"]
    f.name = "Coastal water quality"
    dump_model(f, paths.project_yaml)
    auto_commit(root, subject="cld", paths=[paths.project_yaml])
    a, _ = add_node("Nutrient load", kind="variable", root=root)
    b, _ = add_node("Algal bloom", kind="variable", root=root)
    e1, _ = add_edge(a.id, b.id, kind="causal", root=root)
    e2, _ = add_edge(b.id, a.id, kind="causal", root=root)
    record_new_finding(
        "Reinforcing loop",
        category="structure",
        model_type="cld",
        payload={"node_ids": [a.id, b.id], "edge_ids": [e1.id, e2.id]},
        root=root,
    )
    doc, _ = draft_story(
        "cld",
        StoryGenerationRequest(include_sections=["key_findings", "answer_to_question", "open_questions", "implications"]),
        root=root,
    )
    answer = next(x for x in doc.beats if x.kind == "answer")
    set_beat_prose("cld", answer.id, "We found that nutrients feed the blooms.", root=root)
    return paths, a, b, e1, e2


def test_renders_self_contained_html(story_with_prose) -> None:
    paths, a, b, e1, e2 = story_with_prose
    html = story_html.render(paths, "cld")

    # Structure
    assert html.startswith("<!DOCTYPE html>")
    assert "Coastal water quality" in html
    assert "We found that nutrients feed the blooms." in html
    assert 'id="story-manifest"' in html
    assert "<noscript>" in html
    assert "traces to evidence" in html
    assert "scrollama" in html.lower()

    # The diagram is self-rendered to SVG from the (auto-)layout — no graphviz
    # binary needed — with node labels and addressable node/edge groups inline.
    assert "<svg" in html
    assert "How the model connects" not in html  # text fallback NOT used
    assert "Nutrient load" in html
    assert f'<g class="node" id="{a.id}">' in html
    assert f'<g class="edge" id="{e1.id}">' in html

    # Emphasis data attributes seeded from the loop (system_tour beat)
    assert f'data-nodes="{a.id},{b.id}"' in html
    assert f'data-edges="{e1.id},{e2.id}"' in html

    # Self-contained: no externally-loaded resources
    assert 'src="http' not in html
    assert 'href="http' not in html


def test_unknown_model_type_raises(story_with_prose) -> None:
    paths, *_ = story_with_prose
    with pytest.raises(ValueError):
        story_html.render(paths, "fcm")


def test_unknown_theme_falls_back_to_default(story_with_prose) -> None:
    paths, *_ = story_with_prose
    # A theme name with no matching CSS falls back to default.css, not an error.
    html = story_html.render(paths, "cld", theme="does-not-exist")
    assert html.startswith("<!DOCTYPE html>")


def test_write_emits_file(story_with_prose, tmp_path) -> None:
    paths, *_ = story_with_prose
    target = tmp_path / "out" / "story.html"
    returned = story_html.write(paths, target, model_type="cld")
    assert returned == target
    assert target.exists()
    assert target.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")


def test_asset_data_uri_handles_missing_and_present(story_with_prose) -> None:
    paths, *_ = story_with_prose
    # No asset id → None.
    assert story_html._asset_data_uri(paths, None) is None
    # Asset id but no assets dir yet → None.
    assert story_html._asset_data_uri(paths, "logo") is None
    # With a real asset file present → a base64 data URI.
    paths.story_assets_dir.mkdir(parents=True, exist_ok=True)
    (paths.story_assets_dir / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    uri = story_html._asset_data_uri(paths, "logo")
    assert uri is not None
    assert uri.startswith("data:image/png;base64,")
