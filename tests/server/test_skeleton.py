"""Tests for the FastAPI server skeleton (G1 endpoints)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.operations import nodes as node_ops
from latris.operations.init import init_project
from latris.server.app import create_app
from tests.conftest import build_with_template_identity, clone_project


@pytest.fixture(scope="module")
def _module_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """init + statement "What drives air quality?". The statement is asserted
    against in this file's tests, so we can't reuse the shared empty template."""

    def build() -> Path:
        root = tmp_path_factory.mktemp("skeleton_tpl") / "demo"
        init_project(root, statement="What drives air quality?")
        return root

    return build_with_template_identity(build)


@pytest.fixture
def project(_module_template: Path, tmp_path: Path, git_identity) -> Path:
    return clone_project(_module_template, tmp_path / "demo")


@pytest.fixture
def client(project: Path) -> TestClient:
    app = create_app(project_root=project)
    return TestClient(app)


@pytest.fixture
def populated_project(project: Path) -> Path:
    """Project with a few nodes and edges."""
    node_ops.add_node("Price", kind="variable", root=project)
    node_ops.add_node("Demand", kind="variable", root=project)
    return project


@pytest.fixture
def populated_client(populated_project: Path) -> TestClient:
    app = create_app(project_root=populated_project)
    return TestClient(app)


# ── Health ────────────────────────────────────────────────────────────


def test_health_returns_ok(client: TestClient) -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_health_includes_project_root(client: TestClient, project: Path) -> None:
    data = client.get("/api/health").json()
    assert data["project_root"] == str(project)


# ── Project ───────────────────────────────────────────────────────────


def test_project_returns_foundation(client: TestClient) -> None:
    resp = client.get("/api/project")
    assert resp.status_code == 200
    data = resp.json()
    assert "air quality" in data["statement"].lower()


# ── Substrate ─────────────────────────────────────────────────────────


def test_substrate_empty_on_fresh_project(client: TestClient) -> None:
    resp = client.get("/api/substrate")
    assert resp.status_code == 200
    data = resp.json()
    assert data["entities"] == []
    assert data["edges"] == []


def test_substrate_returns_nodes(populated_client: TestClient) -> None:
    resp = populated_client.get("/api/substrate")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["entities"]) == 2
    labels = sorted(e["label"] for e in data["entities"])
    assert labels == ["Demand", "Price"]


# ── References ────────────────────────────────────────────────────────


def test_references_empty_on_fresh_project(client: TestClient) -> None:
    resp = client.get("/api/references")
    assert resp.status_code == 200
    assert resp.json() == []


# ── Challenges ────────────────────────────────────────────────────────


def test_challenges_empty_on_fresh_project(client: TestClient) -> None:
    resp = client.get("/api/challenges")
    assert resp.status_code == 200
    assert resp.json() == []


# ── Full state ────────────────────────────────────────────────────────


def test_full_state_has_all_sections(client: TestClient) -> None:
    resp = client.get("/api/state")
    assert resp.status_code == 200
    data = resp.json()
    assert "project" in data
    assert "substrate" in data
    assert "references" in data
    assert "challenges" in data
    assert "mappings" in data
    assert "attributes" in data
    assert "provenance" in data
    # Nested sections
    assert "descriptions" in data["attributes"]
    assert "assumptions" in data["provenance"]


def test_full_state_reflects_nodes(populated_client: TestClient) -> None:
    data = populated_client.get("/api/state").json()
    assert len(data["substrate"]["entities"]) == 2


# ── Error handling ────────────────────────────────────────────────────


def test_nonexistent_project_returns_404(tmp_path: Path) -> None:
    """Server pointed at a directory without a project returns 404."""
    app = create_app(project_root=tmp_path / "no-such-project")
    c = TestClient(app, raise_server_exceptions=False)
    resp = c.get("/api/project")
    assert resp.status_code == 404
    assert resp.json()["error"] == "not_a_project"
