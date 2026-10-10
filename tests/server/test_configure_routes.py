"""Tests for the Configure API endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.operations.edges import add_edge
from latris.operations.init import init_project
from latris.operations.nodes import add_node
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


@pytest.fixture
def two_edges(project: Path):
    """Create A→B and B→C edges."""
    a, _ = add_node("Price", kind="variable", root=project)
    b, _ = add_node("Demand", kind="variable", root=project)
    c, _ = add_node("Supply", kind="variable", root=project)
    e1, _ = add_edge(a.id, b.id, kind="causal", root=project)
    e2, _ = add_edge(b.id, c.id, kind="causal", root=project)
    return e1, e2


# ── Apply attributes ─────────────────────────────────────────────────


def test_apply_polarity_batch(client: TestClient, two_edges) -> None:
    e1, e2 = two_edges
    resp = client.post(
        "/api/configure/apply-attributes",
        json={
            "model_type": "cld",
            "attribute": "polarity",
            "entries": [
                {"target_id": e1.id, "value": "+"},
                {"target_id": e2.id, "value": "-"},
            ],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["applied_ids"]) == 2
    assert len(data["commit_sha"]) == 40


def test_apply_fcm_weight_batch(client: TestClient, two_edges) -> None:
    e1, e2 = two_edges
    resp = client.post(
        "/api/configure/apply-attributes",
        json={
            "model_type": "fcm",
            "attribute": "weight",
            "entries": [
                {"target_id": e1.id, "value": "0.5"},
                {"target_id": e2.id, "value": "-0.8"},
            ],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["applied_ids"]) == 2


def test_apply_invalid_model_type(client: TestClient, two_edges) -> None:
    e1, _ = two_edges
    resp = client.post(
        "/api/configure/apply-attributes",
        json={
            "model_type": "nonexistent",
            "attribute": "polarity",
            "entries": [{"target_id": e1.id, "value": "+"}],
        },
    )
    assert resp.status_code == 422 or resp.status_code == 500


def test_apply_empty_entries(client: TestClient) -> None:
    resp = client.post(
        "/api/configure/apply-attributes",
        json={
            "model_type": "cld",
            "attribute": "polarity",
            "entries": [],
        },
    )
    # ValueError from operation or 422 from framework — either rejects empty.
    assert resp.status_code in (422, 500)


def test_state_includes_fcm_weight(client: TestClient) -> None:
    """The /api/state endpoint should include FCM weight in view_attributes."""
    resp = client.get("/api/state")
    assert resp.status_code == 200
    data = resp.json()
    assert "fcm" in data["view_attributes"]
    assert "weight" in data["view_attributes"]["fcm"]
