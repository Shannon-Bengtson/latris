"""CLI tests for the `review import` command."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from latris.cli.app import app
from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations.init import init_project
from latris.repo import git
from latris.schema import HumanActor
from latris.schema.review import (
    ReviewerInfo,
    ReviewFeedbackItem,
    ReviewManifest,
)

runner = CliRunner()

FIXED_DT = datetime(2026, 5, 4, 12, 0, 0, tzinfo=UTC)
ALICE = HumanActor(name="Alice Example", email="alice@example.com")


def _build_review_html(manifest: ReviewManifest) -> str:
    manifest_json = manifest.model_dump_json(indent=2)
    return (
        "<!DOCTYPE html>\n<html><head><title>Test Review</title></head>\n<body>\n"
        '<script type="application/json" id="review-manifest">\n'
        f"{manifest_json}\n"
        "</script>\n</body></html>"
    )


def _project(tmp_path: Path):
    root = tmp_path / "demo"
    init_project(root, statement="Does X cause Y?")
    a, _ = node_ops.add_node("Price", kind="variable", root=root)
    b, _ = node_ops.add_node("Demand", kind="variable", root=root)
    edge_ops.add_edge(a.id, b.id, kind="causal", root=root)
    return root, a.id


def _manifest(export_sha: str, target_id: str, *, reviewer_name: str = "Bob") -> ReviewManifest:
    return ReviewManifest(
        review_session_id="review-session_01EXAMPLE0000000000000000",
        project_name="demo",
        export_commit_sha=export_sha,
        exported_at=FIXED_DT,
        exported_by=ALICE,
        pack="review",
        sections=["nodes"],
        reviewer=ReviewerInfo(name=reviewer_name, role="Expert"),
        items=[
            ReviewFeedbackItem(
                target_id=target_id,
                feedback_type="challenge",
                text="I disagree with this node.",
            ),
            ReviewFeedbackItem(feedback_type="question", text="What about seasonality?"),
            ReviewFeedbackItem(feedback_type="signoff", text="OK overall."),
        ],
        completed_at=FIXED_DT,
    )


def test_import_happy(tmp_path: Path, git_identity, monkeypatch):
    root, node_a = _project(tmp_path)
    monkeypatch.chdir(root)
    sha = git.head_sha(root)
    html = _build_review_html(_manifest(sha, node_a))
    f = tmp_path / "completed.html"
    f.write_text(html, encoding="utf-8")

    r = runner.invoke(app, ["review", "import", str(f)])
    assert r.exit_code == 0, r.output
    assert "Imported review from Bob" in r.output
    assert "Challenges: 1" in r.output
    assert "Questions:  1" in r.output
    assert "Sign-offs:  1" in r.output
    assert "Commit:" in r.output
    # No drift: HTML was exported at current HEAD.
    assert "Warning" not in r.output


def test_import_version_drift_warns(tmp_path: Path, git_identity, monkeypatch):
    root, node_a = _project(tmp_path)
    monkeypatch.chdir(root)
    old_sha = git.head_sha(root)
    # Advance HEAD so the manifest's export sha is stale.
    node_ops.add_node("Supply", kind="variable", root=root)
    html = _build_review_html(_manifest(old_sha, node_a))
    f = tmp_path / "completed.html"
    f.write_text(html, encoding="utf-8")

    r = runner.invoke(app, ["review", "import", str(f)])
    assert r.exit_code == 0, r.output
    assert "Warning: model has changed" in r.output


def test_import_missing_file_errors(tmp_path: Path, git_identity, monkeypatch):
    root, _ = _project(tmp_path)
    monkeypatch.chdir(root)
    r = runner.invoke(app, ["review", "import", str(tmp_path / "nope.html")])
    assert r.exit_code != 0
    assert "File not found" in r.output


def test_import_invalid_html_errors(tmp_path: Path, git_identity, monkeypatch):
    root, _ = _project(tmp_path)
    monkeypatch.chdir(root)
    f = tmp_path / "bad.html"
    f.write_text("<html><body>not a review</body></html>", encoding="utf-8")
    r = runner.invoke(app, ["review", "import", str(f)])
    # ValueError ("No review manifest") -> exit code 2.
    assert r.exit_code == 2
    assert "No review manifest" in r.output
