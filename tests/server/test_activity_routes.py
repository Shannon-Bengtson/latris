"""Tests for recent activity endpoint (git log)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.operations.init import init_project
from latris.repo import git
from latris.server.app import create_app


@pytest.fixture
def project(tmp_path: Path, git_identity) -> Path:
    root = tmp_path / "demo"
    init_project(root, statement="Test Q?")
    return root


@pytest.fixture
def client(project: Path) -> TestClient:
    app = create_app(project_root=project)
    return TestClient(app)


# ── recent_commits unit tests ────────────────────────────────────────


def test_recent_commits_returns_entries(project: Path) -> None:
    entries = git.recent_commits(project)
    assert len(entries) >= 1
    first = entries[0]
    assert set(first.keys()) == {"sha", "author_name", "author_email", "timestamp", "subject"}
    assert len(first["sha"]) == 40
    assert first["author_name"] == "Test Runner"


def test_recent_commits_respects_limit(project: Path) -> None:
    # Create extra commits so we can test the limit.
    for i in range(3):
        (project / f"file{i}.txt").write_text(f"content {i}")
        git.add_all(project)
        git.commit(project, f"Commit {i}")

    all_entries = git.recent_commits(project, limit=50)
    limited = git.recent_commits(project, limit=2)
    assert len(limited) == 2
    assert len(all_entries) > 2


def test_recent_commits_empty_repo(tmp_path: Path, git_identity) -> None:
    """A bare-init repo with no commits returns an empty list."""
    git.init(tmp_path)
    entries = git.recent_commits(tmp_path)
    assert entries == []


# ── API endpoint tests ───────────────────────────────────────────────


def test_activity_endpoint(client: TestClient) -> None:
    resp = client.get("/api/activity")
    assert resp.status_code == 200
    data = resp.json()
    assert "entries" in data
    assert len(data["entries"]) >= 1
    entry = data["entries"][0]
    assert "sha" in entry
    assert "author_name" in entry
    assert "timestamp" in entry
    assert "subject" in entry


def test_activity_limit_param(client: TestClient, project: Path) -> None:
    # Add a couple of commits.
    (project / "a.txt").write_text("a")
    git.add_all(project)
    git.commit(project, "Add a")
    (project / "b.txt").write_text("b")
    git.add_all(project)
    git.commit(project, "Add b")

    resp = client.get("/api/activity?limit=1")
    assert resp.status_code == 200
    assert len(resp.json()["entries"]) == 1


def test_activity_limit_validation(client: TestClient) -> None:
    resp = client.get("/api/activity?limit=0")
    assert resp.status_code == 422

    resp = client.get("/api/activity?limit=100")
    assert resp.status_code == 422
