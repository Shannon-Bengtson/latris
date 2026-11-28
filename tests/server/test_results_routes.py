"""Server route tests for /api/results/{run_id}/hide and /unhide: what reports show."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.operations import analysis_results as ar
from latris.operations.build import build_from_spec, load_spec
from latris.operations.init import init_project
from latris.repo import git
from latris.server.app import create_app
from tests.operations.test_bow_tie import SPEC


@pytest.fixture
def project(tmp_path: Path, git_identity) -> Path:
    root = tmp_path / "containment"
    init_project(root, statement="How well protected are we?")
    build_from_spec(load_spec(SPEC), root=root)  # records the bow-tie analysis
    return root


@pytest.fixture
def client(project: Path) -> TestClient:
    return TestClient(create_app(project_root=project))


def _hidden(root: Path) -> dict[str, bool]:
    return {run.id: hidden for run, hidden, _stale in ar.list_results(root=root)}


def test_unhide(client: TestClient, project: Path) -> None:
    (run_id,) = _hidden(project)
    assert client.post(f"/api/results/{run_id}/hide").json()["result"]["hidden"] is True
    assert _hidden(project) == {run_id: True}

    r = client.post(f"/api/results/{run_id}/unhide")
    assert r.status_code == 200
    assert r.json()["result"] == {"run_id": run_id, "hidden": False}
    assert r.json()["commit_sha"] == git.head_sha(project)
    assert _hidden(project) == {run_id: False}
    assert [row["run"]["id"] for row in client.get("/api/results").json()["results"]] == [run_id]

    # Already shown: nothing to change, nothing committed.
    head = git.head_sha(project)
    again = client.post(f"/api/results/{run_id}/unhide")
    assert again.status_code == 200 and again.json()["commit_sha"] is None
    assert git.head_sha(project) == head


def test_unhide_unknown_run(client: TestClient, project: Path) -> None:
    head = git.head_sha(project)
    assert client.post("/api/results/run_NOPE/unhide").status_code == 404
    assert git.head_sha(project) == head
