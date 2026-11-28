"""The FCM weight route: a Formalise value, the same write as `latris fcm set-weight`."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.operations import view_attributes as va
from latris.operations.edges import add_edge
from latris.operations.init import init_project
from latris.operations.nodes import add_node
from latris.server.app import create_app


@pytest.fixture
def project(tmp_path: Path, git_identity) -> tuple[Path, str]:
    root = tmp_path / "demo"
    init_project(root, statement="Test Q?")
    a, _ = add_node("Trust", kind="variable", root=root)
    b, _ = add_node("Use", kind="variable", root=root)
    edge, _ = add_edge(a.id, b.id, kind="causal", root=root)
    return root, edge.id


def test_sets_a_weight(project) -> None:
    root, edge_id = project
    client = TestClient(create_app(project_root=root))
    r = client.post("/api/fcm/weight", json={"link": edge_id, "weight": 0.6})
    assert r.status_code == 200
    body = r.json()
    assert body["result"] == {"target_id": edge_id, "weight": 0.6} and body["commit_sha"]
    entry = next(e for e in va.get_view_attributes("fcm", "weight", root=root).entries if e.target_id == edge_id)
    assert float(entry.value) == 0.6


def test_refuses_a_weight_outside_minus_one_to_one(project) -> None:
    root, edge_id = project
    client = TestClient(create_app(project_root=root))
    assert client.post("/api/fcm/weight", json={"link": edge_id, "weight": 1.5}).status_code == 422


def test_its_place_is_a_formalise_value(project) -> None:
    root, _ = project
    spec = create_app(project_root=root).openapi()
    assert spec["paths"]["/api/fcm/weight"]["post"]["x-latris-place"] == "formalise.values"
