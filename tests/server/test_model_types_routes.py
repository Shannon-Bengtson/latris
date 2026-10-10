"""Tests for model-types API endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.operations.init import init_project
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


# ── List model types ──────────────────────────────────────────────────


def test_list_model_types_includes_planned(client: TestClient) -> None:
    resp = client.get("/api/model-types", params={"include_planned": True})
    assert resp.status_code == 200
    types = resp.json()
    assert isinstance(types, list)
    assert len(types) >= 2
    ids = [t["id"] for t in types]
    assert "cld" in ids


def test_list_model_types_excludes_planned(client: TestClient) -> None:
    resp = client.get("/api/model-types", params={"include_planned": False})
    assert resp.status_code == 200
    types = resp.json()
    # All returned should be stable
    for t in types:
        assert t["availability"] == "stable"


def test_list_model_types_default_includes_planned(client: TestClient) -> None:
    resp = client.get("/api/model-types")
    assert resp.status_code == 200
    types = resp.json()
    assert len(types) >= 2


# ── Get model type detail ─────────────────────────────────────────────


def test_get_model_type_detail(client: TestClient) -> None:
    resp = client.get("/api/model-types/cld")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "cld"
    assert data["display_name"] == "Causal Loop Diagram"
    assert "availability" in data


def test_get_model_type_not_found(client: TestClient) -> None:
    resp = client.get("/api/model-types/nonexistent")
    assert resp.status_code in (404, 422, 500)


# ── Readiness ─────────────────────────────────────────────────────────


def test_all_readiness(client: TestClient) -> None:
    resp = client.get("/api/model-types/readiness")
    assert resp.status_code == 200
    results = resp.json()
    assert isinstance(results, list)
    assert len(results) >= 1
    # Each entry should have a type_id and some score
    for r in results:
        assert "type_id" in r or "model_type_id" in r or "id" in r


def test_single_type_readiness(client: TestClient) -> None:
    resp = client.get("/api/model-types/cld/readiness")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)
