"""Tests for review export and import endpoints."""

from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.operations import nodes as node_ops
from latris.operations.init import init_project
from latris.repo import git
from latris.schema import HumanActor
from latris.schema.review import (
    ReviewerInfo,
    ReviewFeedbackItem,
    ReviewManifest,
)
from latris.server.app import create_app

FIXED_DT = datetime(2026, 5, 4, 12, 0, 0, tzinfo=UTC)
ALICE = HumanActor(name="Alice Example", email="alice@example.com")


@pytest.fixture
def project(tmp_path: Path, git_identity) -> Path:
    root = tmp_path / "demo"
    init_project(root, statement="Does X cause Y?")
    node_ops.add_node("Price", kind="variable", root=root)
    node_ops.add_node("Demand", kind="variable", root=root)
    return root


@pytest.fixture
def client(project: Path) -> TestClient:
    return TestClient(create_app(project_root=project))


class TestExportReview:
    def test_returns_html(self, client):
        resp = client.get("/api/export/review")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "<!DOCTYPE html>" in resp.text

    def test_contains_model_data(self, client):
        resp = client.get("/api/export/review")
        assert "Price" in resp.text
        assert "Demand" in resp.text

    def test_contains_manifest(self, client):
        resp = client.get("/api/export/review")
        pattern = r'<script\s+type="application/json"\s+id="review-manifest">\s*(.*?)\s*</script>'
        match = re.search(pattern, resp.text, re.DOTALL)
        assert match
        manifest = json.loads(match.group(1))
        assert manifest["project_name"] == "demo"

    def test_content_disposition_attachment(self, client):
        resp = client.get("/api/export/review")
        assert "attachment" in resp.headers.get("content-disposition", "")
        assert "review-demo.html" in resp.headers["content-disposition"]

    def test_zip_variant(self, client):
        resp = client.get("/api/export/review?zip=true")
        assert resp.status_code == 200
        assert "application/zip" in resp.headers["content-type"]
        # Verify it's a valid zip containing the HTML
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        names = zf.namelist()
        assert len(names) == 1
        assert names[0] == "review-demo.html"
        html = zf.read(names[0]).decode("utf-8")
        assert "<!DOCTYPE html>" in html

    def test_pack_parameter(self, client):
        resp = client.get("/api/export/review?pack=audit")
        assert resp.status_code == 200
        assert "Assumptions" in resp.text


class TestImportReview:
    def test_import_valid_review(self, client, project):
        sha = git.head_sha(project)
        manifest = ReviewManifest(
            review_session_id="review-session_01EXAMPLE0000000000000000",
            project_name="demo",
            export_commit_sha=sha,
            exported_at=FIXED_DT,
            exported_by=ALICE,
            pack="review",
            sections=[],
            reviewer=ReviewerInfo(name="Bob", role="Expert"),
            items=[
                ReviewFeedbackItem(feedback_type="question", text="Why this?"),
            ],
            completed_at=FIXED_DT,
        )
        html = _build_review_html(manifest)
        resp = client.post(
            "/api/review/import",
            files={"file": ("review.html", html.encode("utf-8"), "text/html")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["items_imported"] == 1
        assert data["questions_created"] == 1
        assert data["commit_sha"] != ""

    def test_import_rejects_invalid_html(self, client):
        resp = client.post(
            "/api/review/import",
            files={"file": ("bad.html", b"<html>not a review</html>", "text/html")},
        )
        assert resp.status_code == 422


def _build_review_html(manifest: ReviewManifest) -> str:
    manifest_json = manifest.model_dump_json(indent=2)
    return f"""\
<!DOCTYPE html>
<html><head><title>Test</title></head>
<body>
<script type="application/json" id="review-manifest">
{manifest_json}
</script>
</body></html>"""
