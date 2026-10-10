"""Tests for view projection and mapping endpoints (T6)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations.init import init_project
from latris.server.app import create_app


@pytest.fixture
def project(tmp_path: Path, git_identity) -> Path:
    root = tmp_path / "demo"
    init_project(root, statement="Q?")
    return root


@pytest.fixture
def project_with_graph(project: Path) -> Path:
    a, _ = node_ops.add_node("Price", kind="variable", root=project)
    b, _ = node_ops.add_node("Demand", kind="variable", root=project)
    edge_ops.add_edge(a.id, b.id, root=project)
    return project


@pytest.fixture
def client(project_with_graph: Path) -> TestClient:
    return TestClient(create_app(project_root=project_with_graph))


def test_auto_project_maps_all_elements(client: TestClient) -> None:
    resp = client.post("/api/views/dag/auto-project")
    assert resp.status_code == 200
    data = resp.json()
    assert "mappings" in data
    assert len(data["mappings"]) >= 2  # at least the 2 nodes


def test_project_view_with_manual_mappings(client: TestClient) -> None:
    """Project a view after manually mapping elements (not via auto-project)."""
    nodes = client.get("/api/nodes").json()
    for n in nodes:
        client.post("/api/views/mappings", json={"l2_query": n["id"], "view_kind": "dag"})
    resp = client.post("/api/views/dag/project")
    assert resp.status_code == 200
    data = resp.json()
    assert "result" in data
    assert len(data["result"]["entity_ids"]) >= 2


def test_list_mappings_empty_then_populated(client: TestClient) -> None:
    assert client.get("/api/views/mappings").json() == []
    client.post("/api/views/dag/auto-project")
    mappings = client.get("/api/views/mappings").json()
    assert len(mappings) >= 2


def test_add_mapping_creates_commit(client: TestClient, project_with_graph: Path) -> None:
    nodes = client.get("/api/nodes").json()
    node_id = nodes[0]["id"]
    resp = client.post(
        "/api/views/mappings",
        json={
            "l2_query": node_id,
            "view_kind": "cld",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["result"]["l3_view"] == "cld"


def test_delete_mapping(client: TestClient) -> None:
    nodes = client.get("/api/nodes").json()
    node_id = nodes[0]["id"]
    client.post("/api/views/mappings", json={"l2_query": node_id, "view_kind": "cld"})
    resp = client.delete(f"/api/views/mappings/{node_id}/cld")
    assert resp.status_code == 200


def test_approve_mapping(client: TestClient) -> None:
    nodes = client.get("/api/nodes").json()
    node_id = nodes[0]["id"]
    client.post(
        "/api/views/mappings",
        json={
            "l2_query": node_id,
            "view_kind": "cld",
            "ai_proposed": True,
        },
    )
    resp = client.post(f"/api/views/mappings/{node_id}/cld/approve")
    assert resp.status_code == 200
    assert resp.json()["result"]["maturity"] == "approved"
