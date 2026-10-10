"""Coverage for the coherence-check route (``server/routes/checks.py``).

Exercises the empty-project path (no edges → no findings) and a populated
path where an edge's description and CLD polarity tell opposite causal
stories, so the route serialises a finding.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.operations import attributes as attr_ops
from latris.operations import view_attributes as view_attr_ops
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model
from latris.schema import Substrate
from latris.server.app import create_app


@pytest.fixture
def client(two_node_project_root: Path) -> TestClient:
    return TestClient(create_app(project_root=two_node_project_root))


def _edge_id(project: Path) -> str:
    paths = ProjectPaths(project)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    return substrate.edges[0].id


def test_coherence_empty_no_findings(
    two_node_project_root: Path,
) -> None:
    # Edge exists but has neither description nor polarity → no findings.
    client = TestClient(create_app(project_root=two_node_project_root))
    resp = client.get("/api/checks/coherence")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["findings"] == []


def test_coherence_detects_polarity_description_conflict(
    client: TestClient, two_node_project_root: Path
) -> None:
    project = two_node_project_root
    edge_id = _edge_id(project)

    # Description uses a *decrease* verb but polarity is '+': a likely conflict.
    attr_ops.set_attribute(
        edge_id, "description", "Higher price reduces demand", root=project
    )
    view_attr_ops.set_view_attribute(
        edge_id, "cld", "polarity", "+", root=project
    )

    resp = client.get("/api/checks/coherence")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    finding = data["findings"][0]
    assert finding["target_id"] == edge_id
    assert finding["kind"] == "polarity_description_conflict"
    assert finding["polarity"] == "+"
    assert finding["severity"] == "likely"
    assert "decrease" in finding["reason"]


def test_coherence_no_conflict_when_consistent(
    client: TestClient, two_node_project_root: Path
) -> None:
    project = two_node_project_root
    edge_id = _edge_id(project)

    # Decrease verb with '-' polarity is coherent → no finding.
    attr_ops.set_attribute(
        edge_id, "description", "Higher price reduces demand", root=project
    )
    view_attr_ops.set_view_attribute(
        edge_id, "cld", "polarity", "-", root=project
    )

    data = client.get("/api/checks/coherence").json()
    assert data["count"] == 0
