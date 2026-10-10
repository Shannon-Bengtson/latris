"""Tests for the self-contained Story SVG diagram renderer."""

from __future__ import annotations

from latris.exporters.story_diagram import render_story_svg
from latris.operations.edges import add_edge
from latris.operations.init import init_project
from latris.operations.nodes import add_node
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import dump_model
from latris.schema.layout_ui import CanvasLayout, EdgeLayout, NodeLayout


def _seed(tmp_path):
    root = tmp_path / "proj"
    init_project(root, statement="What drives water quality?")
    a, _ = add_node("Nutrient load", kind="variable", root=root)
    b, _ = add_node("Algal bloom", kind="event", root=root)
    e1, _ = add_edge(a.id, b.id, kind="causal", root=root)
    return ProjectPaths(root), a, b, e1


def test_renders_addressable_groups(tmp_path, git_identity) -> None:
    paths, a, b, e1 = _seed(tmp_path)
    svg = render_story_svg(paths, "cld")
    assert svg is not None
    assert svg.startswith("<svg")
    # Addressable groups so the scroll-emphasis controller can target them.
    assert f'<g class="node" id="{a.id}">' in svg
    assert f'<g class="node" id="{b.id}">' in svg
    assert f'<g class="edge" id="{e1.id}">' in svg
    # Outer node shape is a <path> so the .story-emph path CSS highlights it.
    assert svg.count("<path") >= 3
    # Labels are present (short enough not to be truncated).
    assert "Nutrient load" in svg
    # Kind badge letters from the kind map.
    assert ">V<" in svg and ">E<" in svg


def test_empty_view_returns_none(tmp_path, git_identity) -> None:
    root = tmp_path / "empty"
    init_project(root, statement="nothing here")
    assert render_story_svg(ProjectPaths(root), "cld") is None


def test_uses_saved_layout_positions(tmp_path, git_identity) -> None:
    paths, a, b, e1 = _seed(tmp_path)
    paths.layout_dir.mkdir(parents=True, exist_ok=True)
    layout = CanvasLayout(
        nodes={
            a.id: NodeLayout(x=40, y=80, width=180, height=70),
            b.id: NodeLayout(x=400, y=300),
        },
        edges={e1.id: EdgeLayout(waypoints=[])},
    )
    dump_model(layout, paths.layout_dir / "canvas.layout.yaml")
    svg = render_story_svg(paths, "cld")
    assert svg is not None
    # The saved width/height of node A drives the rendered rect path.
    assert "180" in svg or "220" in svg  # x+width corner reflects the saved size


def test_polarity_colours_and_signs(tmp_path, git_identity) -> None:
    from latris.schema import PolarityEntry, PolaritySet

    paths, a, b, e1 = _seed(tmp_path)
    pol_path = paths.view_attribute_path("cld", "polarity")
    pol_path.parent.mkdir(parents=True, exist_ok=True)
    dump_model(
        PolaritySet(entries=[PolarityEntry(target_id=e1.id, attribute="polarity", value="+")]),
        pol_path,
    )
    svg = render_story_svg(paths, "cld")
    assert svg is not None
    # Positive polarity → teal stroke + a "+" sign label.
    assert "#2a6b5e" in svg
    assert ">+<" in svg
