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


def test_auto_project_again_writes_nothing(client: TestClient, project_with_graph: Path) -> None:
    """Opening a model type re-projects it; when nothing changed the view file isn't rewritten, so the
    file watcher reports no edit (which would clear the canvas's overlays) and nothing is committed."""
    from latris.repo import git
    from latris.repo.layout import ProjectPaths

    client.post("/api/views/dag/auto-project")
    view = ProjectPaths(project_with_graph).view_yaml("dag")
    head, mtime = git.head_sha(project_with_graph), view.stat().st_mtime_ns
    assert client.post("/api/views/dag/auto-project").json()["mappings"] == []
    assert git.head_sha(project_with_graph) == head and view.stat().st_mtime_ns == mtime


def test_leave_out_and_put_back(client: TestClient) -> None:
    client.post("/api/views/cld/auto-project")
    node_id = client.get("/api/nodes").json()[0]["id"]
    r = client.post("/api/views/mappings/leave-out", json={"l2_query": node_id, "view_kind": "cld", "reason": "x"})
    assert r.status_code == 200 and r.json()["result"]["reason"] == "x"
    client.post("/api/views/cld/auto-project")
    state = client.get("/api/state").json()["mappings"]
    assert node_id not in {m["l2_id"] for m in state["entries"] if m["l3_view"] == "cld"}
    assert [x["l2_id"] for x in state["left_out"]] == [node_id]
    assert client.post("/api/views/mappings", json={"l2_query": node_id, "view_kind": "cld"}).status_code == 201
    assert client.get("/api/state").json()["mappings"]["left_out"] == []
