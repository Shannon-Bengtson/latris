"""Server route tests for /api/ft/*: event types."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.operations import edges as edge_ops
from latris.operations import fault_tree as ft
from latris.operations import nodes as node_ops
from latris.operations.init import init_project
from latris.repo import git
from latris.server.app import create_app


@pytest.fixture
def project(tmp_path: Path, git_identity) -> Path:
    root = tmp_path / "cooling"
    init_project(root, statement="How likely is a loss of cooling?")
    for n in ("Loss of cooling", "Pump fails"):
        node_ops.add_node(n, kind="event", root=root)
    edge_ops.add_edge("Pump fails", "Loss of cooling", kind="logical", root=root)
    return root


@pytest.fixture
def client(project: Path) -> TestClient:
    return TestClient(create_app(project_root=project))


def _roles(root: Path) -> dict[str, str]:
    return ft.get_events(root=root)


def test_event(client: TestClient, project: Path) -> None:
    r = client.post("/api/ft/event", json={"node": "Loss of cooling", "event_type": "top_event"})
    assert r.status_code == 200
    top = next(e.id for e in node_ops.list_nodes(root=project) if e.label == "Loss of cooling")
    assert r.json()["result"] == {"target_id": top, "event_type": "top_event"}
    assert r.json()["commit_sha"] == git.head_sha(project)
    assert _roles(project) == {top: "top_event"}
    assert client.get("/api/ft/tree").json()["top"] == top


@pytest.mark.parametrize(("body", "status", "detail"), [
    ({"node": "Loss of cooling", "event_type": "bogus"}, 422, "not a fault-tree event type"),
    ({"node": "Nope", "event_type": "top_event"}, 404, "Nope"),
    ({"node": "Pump fails -> Loss of cooling", "event_type": "basic_event"}, 422, "is a link"),
])
def test_event_errors(client: TestClient, project: Path, body: dict, status: int, detail: str) -> None:
    r = client.post("/api/ft/event", json=body)
    assert r.status_code == status and detail in r.json()["detail"]
    assert _roles(project) == {}


def test_event_needs_a_type(client: TestClient) -> None:
    assert client.post("/api/ft/event", json={"node": "Loss of cooling"}).status_code == 422
