"""Tests for the self-contained HTML review pack exporter."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from latris.exporters import review_html
from latris.operations.init import init_project
from latris.repo.layout import ProjectPaths
from tests.conftest import build_with_template_identity, clone_project


@pytest.fixture(scope="module")
def _module_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """init + Rainfall + Sediment + edge. Specific statement and node names
    are asserted against in this file's tests."""
    from latris.operations import edges as edge_ops
    from latris.operations import nodes as node_ops

    def build() -> Path:
        root = tmp_path_factory.mktemp("review_html_tpl") / "demo"
        init_project(root, statement="Does rainfall affect sediment?")
        a, _ = node_ops.add_node("Rainfall", kind="variable", root=root)
        b, _ = node_ops.add_node("Sediment", kind="variable", root=root)
        edge_ops.add_edge(a.id, b.id, kind="causal", root=root)
        return root

    return build_with_template_identity(build)


@pytest.fixture
def project(_module_template: Path, tmp_path: Path, git_identity, monkeypatch) -> Path:
    dest = clone_project(_module_template, tmp_path / "demo")
    monkeypatch.chdir(dest)
    return dest


def _extract_manifest(html_str: str) -> dict:
    """Extract the JSON manifest from the HTML."""
    pattern = r'<script\s+type="application/json"\s+id="review-manifest">\s*(.*?)\s*</script>'
    match = re.search(pattern, html_str, re.DOTALL)
    assert match, "No review manifest found in HTML"
    return json.loads(match.group(1))


class TestRender:
    def test_produces_valid_html(self, project):
        paths = ProjectPaths(project)
        html = review_html.render(paths)
        assert "<!DOCTYPE html>" in html
        assert "<html" in html
        assert "</html>" in html

    def test_includes_model_data(self, project):
        paths = ProjectPaths(project)
        html = review_html.render(paths)
        assert "Rainfall" in html
        assert "Sediment" in html

    def test_includes_project_statement(self, project):
        paths = ProjectPaths(project)
        html = review_html.render(paths)
        assert "Does rainfall affect sediment?" in html

    def test_includes_manifest_json(self, project):
        paths = ProjectPaths(project)
        html = review_html.render(paths)
        manifest = _extract_manifest(html)
        assert "review_session_id" in manifest
        assert manifest["review_session_id"].startswith("review-session_")
        assert manifest["project_name"] == "demo"
        assert manifest["export_commit_sha"] != ""
        assert manifest["items"] == []
        assert manifest["reviewer"] is None

    def test_manifest_has_element_ids(self, project):
        paths = ProjectPaths(project)
        html = review_html.render(paths)
        manifest = _extract_manifest(html)
        assert "Rainfall" in manifest["element_ids"].values()
        assert "Sediment" in manifest["element_ids"].values()

    def test_includes_feedback_buttons(self, project):
        paths = ProjectPaths(project)
        html = review_html.render(paths)
        assert 'class="fb-btn"' in html
        assert "data-target=" in html

    def test_includes_reviewer_form(self, project):
        paths = ProjectPaths(project)
        html = review_html.render(paths)
        assert 'id="reviewer-name"' in html
        assert 'id="save-review-btn"' in html

    def test_includes_noscript_banner(self, project):
        paths = ProjectPaths(project)
        html = review_html.render(paths)
        assert "<noscript>" in html
        assert "JavaScript is required" in html

    def test_includes_status_bar(self, project):
        paths = ProjectPaths(project)
        html = review_html.render(paths)
        assert 'id="status-bar"' in html

    def test_includes_project_level_feedback(self, project):
        paths = ProjectPaths(project)
        html = review_html.render(paths)
        assert 'id="project-feedback-btn"' in html
        assert "Project-Level Feedback" in html

    def test_includes_embedded_js(self, project):
        paths = ProjectPaths(project)
        html = review_html.render(paths)
        assert "function saveReview()" in html
        assert "feedbackItems" in html


class TestPackFiltering:
    def test_default_review_pack(self, project):
        paths = ProjectPaths(project)
        html = review_html.render(paths, pack="review")
        # Review pack includes: foundation, nodes, edges, evidence, challenges, questions, findings
        assert "Foundation" in html
        assert "Nodes" in html
        assert "Edges" in html

    def test_explicit_sections(self, project):
        paths = ProjectPaths(project)
        html = review_html.render(paths, sections=["nodes"])
        assert "Nodes" in html
        # Should not include edges when only nodes requested
        # (Foundation is excluded, edges section excluded)
        assert ">Edges<" not in html

    def test_all_sections_pack(self, project):
        paths = ProjectPaths(project)
        html = review_html.render(paths, pack="audit")
        assert "Assumptions" in html
        assert "References" in html


class TestDiagramRendering:
    def test_svg_embedded_when_available(self, project, monkeypatch):
        """Mock graphviz to return SVG, verify it's embedded."""
        import subprocess as sp
        from unittest.mock import patch

        fake_svg = '<svg xmlns="http://www.w3.org/2000/svg"><g>test</g></svg>'
        mock_result = sp.CompletedProcess(["dot", "-Tsvg"], 0, stdout=fake_svg.encode())
        with patch("latris.exporters.diagram.subprocess.run", return_value=mock_result):
            paths = ProjectPaths(project)
            html = review_html.render(paths)
        assert "<svg" in html
        assert "diagram-container" in html

    def test_text_fallback_without_graphviz(self, project, monkeypatch):
        """Without graphviz, should render text-based edge list."""
        from unittest.mock import patch

        with patch("latris.exporters.diagram.subprocess.run", side_effect=FileNotFoundError):
            paths = ProjectPaths(project)
            html = review_html.render(paths)
        # Should have text fallback with arrow
        assert "&rarr;" in html
        assert "Rainfall" in html


class TestEmptyProject:
    def test_renders_without_error(self, tmp_path, git_identity, monkeypatch):
        root = tmp_path / "empty"
        init_project(root, statement="Empty project")
        monkeypatch.chdir(root)
        paths = ProjectPaths(root)
        html = review_html.render(paths)
        assert "<!DOCTYPE html>" in html
        assert "Empty project" in html
