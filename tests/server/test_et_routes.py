"""Server route tests for /api/et/*: elements, heading order and the initiating event's frequency."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.operations import event_tree as et
from latris.operations import nodes as node_ops
from latris.operations.init import init_project
from latris.repo import git
from latris.server.app import create_app
from tests.operations.test_event_tree import ELEMENTS


@pytest.fixture
def project(tmp_path: Path, git_identity) -> Path:
    root = tmp_path / "release"
    init_project(root, statement="How often does a gas release end in a fire?")
    for label in ELEMENTS:
        node_ops.add_node(label, kind="event", root=root)
    return root


@pytest.fixture
def client(project: Path) -> TestClient:
    return TestClient(create_app(project_root=project))


@pytest.fixture
def staged(client: TestClient) -> TestClient:
    for label, element in ELEMENTS.items():
        assert client.post("/api/et/element", json={"node": label, "element": element}).status_code == 200
    return client


def _id(root: Path, label: str) -> str:
    return next(e.id for e in node_ops.list_nodes(root=root) if e.label == label)


def test_element(client: TestClient, project: Path) -> None:
    r = client.post("/api/et/element", json={"node": "Gas release", "element": "initiating_event"})
    assert r.status_code == 200
    assert r.json()["result"] == {"target_id": _id(project, "Gas release"), "element": "initiating_event"}
    assert r.json()["commit_sha"] == git.head_sha(project)
    assert et.get_elements(root=project) == {_id(project, "Gas release"): "initiating_event"}


def test_element_errors(client: TestClient, project: Path) -> None:
    bad = client.post("/api/et/element", json={"node": "Gas release", "element": "bogus"})
    assert bad.status_code == 422 and "not an event-tree element" in bad.json()["detail"]
    assert client.post("/api/et/element", json={"node": "Nope", "element": "end_state"}).status_code == 404
    assert et.get_elements(root=project) == {}


def test_order(staged: TestClient, project: Path) -> None:
    r = staged.post("/api/et/order", json={"headings": ["Gas detected", "Ignition"]})
    assert r.status_code == 200
    ids = [_id(project, "Gas detected"), _id(project, "Ignition")]
    assert r.json()["result"]["headings"] == ids
    assert r.json()["commit_sha"] == git.head_sha(project)
    assert et.get_structure(root=project).headings == ids
    assert staged.get("/api/et/tree").json()["structure"]["headings"] == ids


@pytest.mark.parametrize(("headings", "status", "detail"), [
    (["Gas detected", "Gas detected"], 422, "listed twice"),
    (["Fire"], 422, "not a heading"),
    (["Nope"], 404, "Nope"),
])
def test_order_errors(staged: TestClient, project: Path, headings: list[str], status: int, detail: str) -> None:
    r = staged.post("/api/et/order", json={"headings": headings})
    assert r.status_code == status and detail in r.json()["detail"]
    assert et.get_structure(root=project).headings == []


def test_order_must_be_a_list(staged: TestClient) -> None:
    assert staged.post("/api/et/order", json={"headings": "Fire"}).status_code == 422


def test_frequency(staged: TestClient, project: Path) -> None:
    r = staged.post("/api/et/frequency", json={"node": "Gas release", "frequency": 0.02, "source_id": "log"})
    assert r.status_code == 200
    assert (r.json()["result"]["frequency"], r.json()["result"]["source_id"]) == (0.02, "log")
    assert r.json()["commit_sha"] == git.head_sha(project)
    (entry,) = et.get_frequencies(root=project).entries
    assert (entry.target_id, entry.frequency) == (_id(project, "Gas release"), 0.02)


@pytest.mark.parametrize(("body", "status", "detail"), [
    ({"node": "Gas release", "frequency": -1}, 422, "greater than or equal to 0"),
    ({"node": "Fire", "frequency": 0.02}, 422, "not an initiating event"),
    ({"node": "Nope", "frequency": 0.02}, 404, "Nope"),
])
def test_frequency_errors(staged: TestClient, project: Path, body: dict, status: int, detail: str) -> None:
    r = staged.post("/api/et/frequency", json=body)
    assert r.status_code == status and detail in r.json()["detail"]
    assert et.get_frequencies(root=project).entries == []
