"""Tests for graph analysis API endpoints."""

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
    init_project(root, statement="Test Q?")
    return root


@pytest.fixture
def client(project: Path) -> TestClient:
    app = create_app(project_root=project)
    return TestClient(app)


@pytest.fixture
def triangle(project: Path):
    """Triangle with polarity: A →(+) B →(+) C →(−) A."""
    a, _ = add_node("Emissions", kind="variable", root=project)
    b, _ = add_node("Pollution", kind="variable", root=project)
    c, _ = add_node("Regulation", kind="variable", root=project)
    e1, _ = add_edge(a.id, b.id, kind="causal", root=project)
    e2, _ = add_edge(b.id, c.id, kind="causal", root=project)
    e3, _ = add_edge(c.id, a.id, kind="causal", root=project)
    set_view_attribute(e1.id, "cld", "polarity", "+", root=project)
    set_view_attribute(e2.id, "cld", "polarity", "+", root=project)
    set_view_attribute(e3.id, "cld", "polarity", "-", root=project)
    return a, b, c, e1, e2, e3


@pytest.fixture
def dag(project: Path):
    """DAG: z → x → y, z → y."""
    z, _ = add_node("Confounder", kind="variable", root=project)
    x, _ = add_node("Exposure", kind="variable", root=project)
    y, _ = add_node("Outcome", kind="variable", root=project)
    add_edge(z.id, x.id, kind="causal", root=project)
    add_edge(z.id, y.id, kind="causal", root=project)
    add_edge(x.id, y.id, kind="causal", root=project)
    return z, x, y


def test_loops(client: TestClient, triangle):
    resp = client.get("/api/analysis/loops")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["loops"][0]["classification"] == "B"


def test_loops_empty(client: TestClient):
    resp = client.get("/api/analysis/loops")
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


def test_propagate(client: TestClient, triangle):
    a, _, _, _, _, _ = triangle
    resp = client.get(f"/api/analysis/propagate/{a.id}")
    assert resp.status_code == 200
    effects = resp.json()["effects"]
    assert len(effects) > 0


def test_d_separation(client: TestClient, dag):
    z, x, y = dag
    resp = client.get("/api/analysis/d-separation", params={"x": x.id, "y": y.id})
    assert resp.status_code == 200
    assert resp.json()["d_separated"] is False


def test_d_separation_given_confounder(client: TestClient, dag):
    z, x, y = dag
    resp = client.get("/api/analysis/d-separation", params={"x": x.id, "y": y.id, "given": z.id})
    assert resp.status_code == 200
    # Still not d-separated (direct path x → y remains)
    assert resp.json()["d_separated"] is False


def test_blanket(client: TestClient, dag):
    z, x, y = dag
    resp = client.get(f"/api/analysis/blanket/{x.id}")
    assert resp.status_code == 200
    blanket = resp.json()["blanket"]
    assert z.id in blanket
    assert y.id in blanket


def test_paths(client: TestClient, dag):
    z, _, y = dag
    resp = client.get("/api/analysis/paths", params={"from_id": z.id, "to_id": y.id})
    assert resp.status_code == 200
    assert resp.json()["count"] == 2  # Direct z→y and z→x→y


def test_adjustment_sets(client: TestClient, dag):
    z, x, y = dag
    resp = client.get(
        "/api/analysis/adjustment-sets",
        params={"exposure_id": x.id, "outcome_id": y.id},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 1
    # Z should be in at least one adjustment set
    assert any(z.id in s for s in data["adjustment_sets"])
