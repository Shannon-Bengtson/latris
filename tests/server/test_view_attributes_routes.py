"""Tests for view-attributes API endpoints (CLD polarity etc.)."""

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
def two_nodes_and_edge(project: Path):
    """Create a minimal graph: two nodes connected by an edge."""
    n1, _ = add_node("Price", kind="variable", root=project)
    n2, _ = add_node("Demand", kind="variable", root=project)
    edge, _ = add_edge(n1.id, n2.id, kind="causal", root=project)
    return n1, n2, edge


# ── Set attribute ─────────────────────────────────────────────────────


def test_set_polarity_on_edge(client: TestClient, two_nodes_and_edge) -> None:
    _, _, edge = two_nodes_and_edge
    resp = client.put(
        f"/api/views/cld/attributes/{edge.id}/polarity",
        json={"value": "+"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["target_id"] == edge.id
    assert len(data["commit_sha"]) == 40


def test_set_polarity_negative(client: TestClient, two_nodes_and_edge) -> None:
    _, _, edge = two_nodes_and_edge
    resp = client.put(
        f"/api/views/cld/attributes/{edge.id}/polarity",
        json={"value": "-"},
    )
    assert resp.status_code == 200
    assert resp.json()["target_id"] == edge.id


# ── Get attributes ────────────────────────────────────────────────────


def test_get_polarity_empty(client: TestClient) -> None:
    resp = client.get("/api/views/cld/attributes/polarity")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)


def test_get_polarity_after_set(client: TestClient, two_nodes_and_edge) -> None:
    _, _, edge = two_nodes_and_edge
    # Set a polarity first
    client.put(
        f"/api/views/cld/attributes/{edge.id}/polarity",
        json={"value": "+"},
    )
    resp = client.get("/api/views/cld/attributes/polarity")
    assert resp.status_code == 200
    data = resp.json()
    # Should contain the edge's polarity
    assert isinstance(data, dict)


# Per-attribute "mature" endpoint was removed when maturity moved to
# the parent Entity/Edge — see docs/design/MATURITY_LADDER.md.
# Use POST /api/maturity/{target}/{level} instead (entity-level chokepoint).
