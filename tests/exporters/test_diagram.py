"""Tests for the diagram embedding helper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from latris.exporters.diagram import (
    add_diagram_to_word,
    dot_source,
    render_markdown_diagram,
    render_png_bytes,
    render_svg,
)
from latris.repo.layout import ProjectPaths


@pytest.fixture
def empty_project(empty_project_root: Path) -> ProjectPaths:
    return ProjectPaths(empty_project_root)


@pytest.fixture
def populated_project(two_node_project_root: Path) -> ProjectPaths:
    return ProjectPaths(two_node_project_root)


def test_dot_source_empty_project(empty_project) -> None:
    source = dot_source(empty_project)
    assert "// empty project" in source
    assert "digraph" in source


def test_dot_source_populated_project(populated_project) -> None:
    source = dot_source(populated_project)
    assert "digraph" in source
    assert "Price" in source
    assert "Demand" in source


def test_render_markdown_diagram_empty_returns_empty(empty_project) -> None:
    result = render_markdown_diagram(empty_project)
    assert result == ""


def test_render_markdown_diagram_has_dot_fenced_block(populated_project) -> None:
    result = render_markdown_diagram(populated_project)
    assert "## Model Diagram" in result
    assert "```dot" in result
    assert "digraph" in result


def test_render_svg_empty_project(empty_project) -> None:
    result = render_svg(empty_project)
    assert result is None


def test_render_svg_returns_string_when_graphviz_available(populated_project, monkeypatch) -> None:
    """Mock graphviz subprocess to return SVG output."""
    import subprocess as sp
    from unittest.mock import patch

    fake_svg = '<svg xmlns="http://www.w3.org/2000/svg"><g>graph</g></svg>'
    mock_result = sp.CompletedProcess(["dot", "-Tsvg"], 0, stdout=fake_svg.encode("utf-8"))

    with patch("latris.exporters.diagram.subprocess.run", return_value=mock_result):
        result = render_svg(populated_project)
    assert result is not None
    assert "<svg" in result
    assert isinstance(result, str)


def test_render_svg_returns_none_without_graphviz(populated_project, monkeypatch) -> None:
    """If graphviz is not installed, render_svg returns None."""
    from unittest.mock import patch

    with patch("latris.exporters.diagram.subprocess.run", side_effect=FileNotFoundError):
        result = render_svg(populated_project)
    assert result is None


def test_render_png_bytes_empty_project(empty_project) -> None:
    result = render_png_bytes(empty_project)
    assert result is None


def test_render_png_bytes_returns_bytes_when_graphviz_available(populated_project) -> None:
    import subprocess as sp

    png = b"\x89PNG\r\n\x1a\n" + b"fakepngdata"
    mock_result = sp.CompletedProcess(["dot", "-Tpng"], 0, stdout=png)
    with patch("latris.exporters.diagram.subprocess.run", return_value=mock_result):
        result = render_png_bytes(populated_project)
    assert result == png


def test_render_png_bytes_returns_none_without_graphviz(populated_project) -> None:
    with patch("latris.exporters.diagram.subprocess.run", side_effect=FileNotFoundError):
        result = render_png_bytes(populated_project)
    assert result is None


def test_render_png_bytes_returns_none_on_nonzero_exit(populated_project) -> None:
    """A graphviz failure (non-zero return code) yields None, not garbage."""
    import subprocess as sp

    mock_result = sp.CompletedProcess(["dot", "-Tpng"], 1, stdout=b"", stderr=b"boom")
    with patch("latris.exporters.diagram.subprocess.run", return_value=mock_result):
        result = render_png_bytes(populated_project)
    assert result is None


def test_render_svg_returns_none_on_nonzero_exit(populated_project) -> None:
    import subprocess as sp

    mock_result = sp.CompletedProcess(["dot", "-Tsvg"], 1, stdout=b"")
    with patch("latris.exporters.diagram.subprocess.run", return_value=mock_result):
        result = render_svg(populated_project)
    assert result is None


def test_render_svg_returns_none_on_timeout(populated_project) -> None:
    import subprocess as sp

    with patch(
        "latris.exporters.diagram.subprocess.run",
        side_effect=sp.TimeoutExpired(cmd="dot", timeout=10),
    ):
        result = render_svg(populated_project)
    assert result is None


# ── add_diagram_to_word ──────────────────────────────────────────────


def test_add_diagram_to_word_embeds_png_when_graphviz_available(populated_project) -> None:
    """When graphviz renders a PNG, the diagram is embedded as a picture."""
    doc = MagicMock()
    with patch(
        "latris.exporters.diagram.render_png_bytes", return_value=b"PNGDATA"
    ):
        add_diagram_to_word(doc, populated_project)
    doc.add_heading.assert_called_once_with("Model Diagram", level=2)
    doc.add_picture.assert_called_once()
    # No text fallback when the picture path is taken.
    doc.add_paragraph.assert_not_called()


def test_add_diagram_to_word_falls_back_to_text_summary(populated_project) -> None:
    """Without graphviz, a populated model still gets a text edge list."""
    doc = MagicMock()
    with patch("latris.exporters.diagram.render_png_bytes", return_value=None):
        add_diagram_to_word(doc, populated_project)
    doc.add_heading.assert_called_once_with("Model Diagram", level=2)
    doc.add_picture.assert_not_called()
    # One bullet per edge (the two-node fixture has a single edge).
    bullets = [c for c in doc.add_paragraph.call_args_list if c.kwargs.get("style") == "List Bullet"]
    assert len(bullets) >= 1
    assert "→" in bullets[0].args[0]  # arrow between source and target labels


def test_add_diagram_to_word_empty_project_adds_nothing(empty_project) -> None:
    """An empty model produces neither a picture nor a heading."""
    doc = MagicMock()
    # render_png_bytes returns None naturally for an empty project.
    add_diagram_to_word(doc, empty_project)
    doc.add_heading.assert_not_called()
    doc.add_picture.assert_not_called()
