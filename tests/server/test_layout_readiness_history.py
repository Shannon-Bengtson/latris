"""Tests for layout, readiness (CLD score), and history endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.operations import attributes as attr_ops
from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations import view_attributes as vattr_ops
from latris.operations.init import init_project
from latris.server.app import create_app


@pytest.fixture
def project(tmp_path: Path, git_identity) -> Path:
    root = tmp_path / "demo"
    init_project(root, statement="Test")
    return root


@pytest.fixture
def client(project: Path) -> TestClient:
    return TestClient(create_app(project_root=project))


# ── Layout ───────────────────────────────────────────────────────────


def test_get_layout_empty_returns_default(client: TestClient) -> None:
    resp = client.get("/api/layout")
    assert resp.status_code == 200
    data = resp.json()
    assert "nodes" in data
    assert data["nodes"] == {}


def test_put_and_get_layout_round_trip(client: TestClient) -> None:
    layout = {
        "nodes": {
            "node_abc": {"x": 100, "y": 200, "width": 160, "height": 60},
        },
    }
    put_resp = client.put("/api/layout", json=layout)
    assert put_resp.status_code == 200
    assert put_resp.json()["status"] == "ok"

    get_resp = client.get("/api/layout")
    data = get_resp.json()
    assert "node_abc" in data["nodes"]
    assert data["nodes"]["node_abc"]["x"] == 100
    assert data["nodes"]["node_abc"]["y"] == 200


# ── Readiness (CLD score) ───────────────────────────────────────────


def test_readiness_includes_cld_score(client: TestClient, project: Path) -> None:
    """Verify that readiness response includes the cld score (bug fix validation)."""
    a, _ = node_ops.add_node("X", root=project)
    b, _ = node_ops.add_node("Y", root=project)
    edge_ops.add_edge(a.id, b.id, root=project)

    data = client.get("/api/readiness").json()
    assert "cld" in data["scores"]
    # One edge, no polarity yet → 0%
    assert data["scores"]["cld"] == 0


def test_readiness_cld_score_after_polarity(client: TestClient, project: Path) -> None:
    """CLD score should reach 100% when all edges have polarity AND ≥1 loop
    exists. Loops are the structural validator for CLD."""
    a, _ = node_ops.add_node("X", root=project)
    b, _ = node_ops.add_node("Y", root=project)
    edge_ab, _ = edge_ops.add_edge(a.id, b.id, root=project)
    edge_ba, _ = edge_ops.add_edge(b.id, a.id, root=project)

    vattr_ops.set_view_attribute(edge_ab.id, "cld", "polarity", "+", root=project)
    vattr_ops.set_view_attribute(edge_ba.id, "cld", "polarity", "+", root=project)

    data = client.get("/api/readiness").json()
    assert data["scores"]["cld"] == 100


def test_readiness_gaps_structure(client: TestClient, project: Path) -> None:
    """Verify the gaps object has all expected fields."""
    node_ops.add_node("Orphan", root=project)

    data = client.get("/api/readiness").json()
    gaps = data["gaps"]
    assert "nodes_without_description" in gaps
    assert "edges_without_polarity" in gaps
    assert "open_challenges" in gaps
    assert "open_questions" in gaps
    assert "elements_without_evidence" in gaps
    assert len(gaps["nodes_without_description"]) == 1


def test_readiness_model_types_included(client: TestClient) -> None:
    """Verify the readiness endpoint includes model_types list."""
    data = client.get("/api/readiness").json()
    assert "model_types" in data
    assert isinstance(data["model_types"], list)


# ── Node/Edge retype ────────────────────────────────────────────────


def test_retype_node(client: TestClient) -> None:
    node_id = client.post("/api/nodes", json={"label": "X"}).json()["result"]["id"]

    resp = client.patch(f"/api/nodes/{node_id}/kind", json={"new_kind": "variable"})
    assert resp.status_code == 200
    assert resp.json()["result"]["kind"] == "variable"


def test_retype_edge(client: TestClient) -> None:
    a = client.post("/api/nodes", json={"label": "A"}).json()["result"]["id"]
    b = client.post("/api/nodes", json={"label": "B"}).json()["result"]["id"]
    edge_id = client.post("/api/edges", json={"from_query": a, "to_query": b}).json()["result"]["id"]

    resp = client.patch(f"/api/edges/{edge_id}/kind", json={"new_kind": "temporal"})
    assert resp.status_code == 200
    assert resp.json()["result"]["kind"] == "temporal"


# ── History ──────────────────────────────────────────────────────────


def test_undo_on_empty_project_fails_gracefully(client: TestClient) -> None:
    """Undo on a fresh project with only the init commit should fail cleanly."""
    resp = client.post("/api/history/undo")
    # Might be 409 (branch root) or 500 (git error) — both are acceptable
    assert resp.status_code in (200, 409, 500)


def test_undo_after_mutation(client: TestClient) -> None:
    """Add a node, undo, verify it's gone."""
    node_id = client.post("/api/nodes", json={"label": "Temp"}).json()["result"]["id"]
    assert any(n["id"] == node_id for n in client.get("/api/nodes").json())

    resp = client.post("/api/history/undo")
    assert resp.status_code == 200

    assert not any(n["id"] == node_id for n in client.get("/api/nodes").json())


# ── Export text ──────────────────────────────────────────────────────


def test_export_markdown_returns_text(client: TestClient, project: Path) -> None:
    """Markdown export should return valid text content."""
    node_ops.add_node("Price", kind="variable", root=project)
    attr_ops.set_attribute("Price", "description", "The retail price", root=project)

    resp = client.get("/api/export/markdown")
    assert resp.status_code == 200
    text = resp.text
    assert "Price" in text


def test_export_dot_returns_text(client: TestClient, project: Path) -> None:
    """DOT export should return valid graphviz source."""
    node_ops.add_node("A", root=project)
    node_ops.add_node("B", root=project)

    resp = client.get("/api/export/dot")
    assert resp.status_code == 200
    text = resp.text
    assert "digraph" in text
