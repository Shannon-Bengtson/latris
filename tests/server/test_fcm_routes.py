"""Tests for FCM API endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.operations.edges import add_edge
from latris.operations.init import init_project
from latris.operations.nodes import add_node
from latris.operations.view_attributes import set_view_attribute
from latris.server.app import create_app


@pytest.fixture
def project(tmp_path: Path, git_identity) -> Path:
    root = tmp_path / "demo"
    init_project(root, statement="FCM test")
    return root


@pytest.fixture
def client(project: Path) -> TestClient:
    app = create_app(project_root=project)
    return TestClient(app)


@pytest.fixture
def triangle(project: Path):
    """Triangle with weights."""
    a, _ = add_node("Investment", kind="variable", root=project)
    b, _ = add_node("Growth", kind="variable", root=project)
    c, _ = add_node("Revenue", kind="variable", root=project)
    e1, _ = add_edge(a.id, b.id, kind="causal", root=project)
    e2, _ = add_edge(b.id, c.id, kind="causal", root=project)
    e3, _ = add_edge(c.id, a.id, kind="causal", root=project)
    set_view_attribute(e1.id, "fcm", "weight", "0.8", root=project)
    set_view_attribute(e2.id, "fcm", "weight", "0.6", root=project)
    set_view_attribute(e3.id, "fcm", "weight", "0.4", root=project)
    return a, b, c, e1, e2, e3


def test_get_weights_empty(client: TestClient):
    resp = client.get("/api/fcm/weights")
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


def test_get_weights(client: TestClient, triangle):
    resp = client.get("/api/fcm/weights")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 3
    values = {w["value"] for w in data["weights"]}
    assert 0.8 in values
    assert 0.6 in values
    assert 0.4 in values


def test_infer_empty(client: TestClient):
    resp = client.post("/api/fcm/infer")
    assert resp.status_code == 200
    data = resp.json()
    assert data["converged"] is True


def test_infer_with_weights(client: TestClient, triangle):
    resp = client.post("/api/fcm/infer")
    assert resp.status_code == 200
    data = resp.json()
    assert data["converged"] is True
    assert len(data["activations"]) == 3
    # All activations should be in [0, 1]
    for val in data["activations"].values():
        assert 0.0 <= val <= 1.0


def test_infer_with_clamp(client: TestClient, triangle):
    a, _, _, _, _, _ = triangle
    resp = client.post("/api/fcm/infer", json={"clamped": {a.id: 1.0}})
    assert resp.status_code == 200
    data = resp.json()
    assert data["converged"] is True
    assert data["activations"][a.id] == pytest.approx(1.0)


def test_infer_with_custom_settings(client: TestClient, triangle):
    resp = client.post(
        "/api/fcm/infer",
        json={
            "lambda_steepness": 3.0,
            "transfer_function": "tanh",
            "max_iterations": 50,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["converged"] is True
