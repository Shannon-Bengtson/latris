"""Tests for lineage API endpoints."""

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


# -- GET /api/lineage/tree --


def test_get_tree_fresh_project(client: TestClient) -> None:
    resp = client.get("/api/lineage/tree")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["nodes"]) == 1
    assert data["nodes"][0]["relationship"] == "original"
    assert data["current_branch"] == "main"


# -- GET /api/lineage/current --


def test_get_current_version(client: TestClient) -> None:
    resp = client.get("/api/lineage/current")
    assert resp.status_code == 200
    data = resp.json()
    assert data["relationship"] == "original"
    assert data["id"].startswith("version_")


# -- POST /api/lineage/milestone --


def test_create_milestone(client: TestClient) -> None:
    resp = client.post("/api/lineage/milestone", json={"name": "Draft 1"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["result"]["name"] == "Draft 1"
    assert data["result"]["maturity"] == "proposed"
    assert len(data["commit_sha"]) == 40


def test_create_approved_milestone(client: TestClient) -> None:
    resp = client.post(
        "/api/lineage/milestone",
        json={"name": "v1", "maturity": "approved"},
    )
    assert resp.status_code == 201
    assert resp.json()["result"]["maturity"] == "approved"


# -- POST /api/lineage/alternative --


def test_create_alternative(client: TestClient, project: Path) -> None:
    resp = client.post(
        "/api/lineage/alternative",
        json={"name": "What-if scenario"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["result"]["relationship"] == "alternative"
    assert data["branch"].startswith("lineage/")
    # Server should now be on the new branch.
    assert git.current_branch(project) == data["branch"]


# -- POST /api/lineage/switch --


def test_switch_version(client: TestClient, project: Path) -> None:
    # Create an alternative.
    alt = client.post("/api/lineage/alternative", json={"name": "Alt"})
    assert alt.status_code == 201
    assert git.current_branch(project) != "main"

    # Switch back to main.
    resp = client.post("/api/lineage/switch", json={"version_query": "main"})
    assert resp.status_code == 200
    assert git.current_branch(project) == "main"


# -- PATCH /api/lineage/version --


def test_update_version(client: TestClient) -> None:
    # Ensure lineage exists first.
    client.get("/api/lineage/current")

    resp = client.patch(
        "/api/lineage/version",
        json={"name": "Renamed", "maturity": "approved"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["result"]["name"] == "Renamed"
    assert data["result"]["maturity"] == "approved"


# -- Undo boundary --


def test_undo_blocked_at_branch_root(client: TestClient, project: Path) -> None:
    # Create an alternative (this is the branch root commit).
    client.post("/api/lineage/alternative", json={"name": "Alt"})

    # Undo should be blocked — HEAD is the branch creation commit.
    resp = client.post("/api/history/undo")
    assert resp.status_code == 409
    assert "Nothing more to undo" in resp.json()["detail"]


def test_undo_works_after_mutation_on_alternative(
    client: TestClient,
    project: Path,
) -> None:
    client.post("/api/lineage/alternative", json={"name": "Alt"})

    # Add a node — this creates a commit we CAN undo.
    client.post("/api/nodes", json={"label": "Price", "kind": "variable"})

    resp = client.post("/api/history/undo")
    assert resp.status_code == 200


# -- GET /api/lineage/tree includes milestones --


def test_set_preferred(client: TestClient) -> None:
    # Create an alternative.
    alt = client.post("/api/lineage/alternative", json={"name": "Alt"})
    alt_id = alt.json()["result"]["id"]

    # Set the alternative as preferred.
    resp = client.post("/api/lineage/preferred", json={"version_query": alt_id})
    assert resp.status_code == 200
    assert resp.json()["version_id"] == alt_id

    # Verify the tree shows it as preferred.
    tree = client.get("/api/lineage/tree").json()
    assert tree["preferred_version_id"] == alt_id


def test_preferred_defaults_to_original(client: TestClient) -> None:
    tree = client.get("/api/lineage/tree").json()
    # The original version should be implicitly preferred.
    assert tree["preferred_version_id"] is not None
    original = [n for n in tree["nodes"] if n["relationship"] == "original"]
    assert tree["preferred_version_id"] == original[0]["id"]


def test_tree_includes_milestones(client: TestClient) -> None:
    client.post("/api/lineage/milestone", json={"name": "M1"})
    client.post("/api/lineage/milestone", json={"name": "M2"})

    resp = client.get("/api/lineage/tree")
    data = resp.json()

    # Milestones should be keyed by the current version ID.
    assert len(data["milestones"]) == 1  # one version, one key
    milestones = list(data["milestones"].values())[0]
    assert len(milestones) == 2
    names = [m["name"] for m in milestones]
    assert "M1" in names
    assert "M2" in names
