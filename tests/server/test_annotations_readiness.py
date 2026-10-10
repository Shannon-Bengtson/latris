"""Tests for annotation summary and readiness endpoints (T9)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.operations import attributes as attr_ops
from latris.operations import challenges as ch_ops
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
def client(project: Path) -> TestClient:
    return TestClient(create_app(project_root=project))


# ── Annotations ───────────────────────────────────────────────────────


def test_annotation_summary_empty(client: TestClient) -> None:
    resp = client.get("/api/annotations/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["per_target"] == {}
    # Empty project has no annotations, so global counts dict is empty
    assert data["global"] == {}


def test_annotation_summary_with_challenge(client: TestClient, project: Path) -> None:
    a, _ = node_ops.add_node("X", root=project)
    b, _ = node_ops.add_node("Y", root=project)
    edge, _ = edge_ops.add_edge(a.id, b.id, root=project)
    ch_ops.open_challenge(edge.id, "Direction is wrong", root=project)

    data = client.get("/api/annotations/summary").json()
    assert edge.id in data["per_target"]
    assert data["per_target"][edge.id]["challenge"] >= 1


# ── Readiness ─────────────────────────────────────────────────────────


def test_readiness_empty_project(client: TestClient) -> None:
    resp = client.get("/api/readiness")
    assert resp.status_code == 200
    data = resp.json()
    assert "scores" in data
    assert "gaps" in data


def test_readiness_after_descriptions(client: TestClient, project: Path) -> None:
    a, _ = node_ops.add_node("X", root=project)
    b, _ = node_ops.add_node("Y", root=project)

    # Before descriptions: workshop score should be 0
    data = client.get("/api/readiness").json()
    assert data["scores"]["workshop"] == 0

    # Add descriptions to both
    attr_ops.set_attribute(a.id, "description", "Desc A", root=project)
    attr_ops.set_attribute(b.id, "description", "Desc B", root=project)

    data = client.get("/api/readiness").json()
    assert data["scores"]["workshop"] == 100
