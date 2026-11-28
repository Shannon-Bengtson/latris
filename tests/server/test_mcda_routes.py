"""Server route tests for /api/mcda/*: options and criteria, and the model read."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.operations import mcda
from latris.operations import nodes as node_ops
from latris.operations.init import init_project
from latris.repo import git
from latris.server.app import create_app


@pytest.fixture
def project(tmp_path: Path, git_identity) -> Path:
    root = tmp_path / "supplier"
    init_project(root, statement="Which supplier?")
    for n in ("Supplier A", "Supplier B", "Cost"):
        node_ops.add_node(n, root=root)
    return root


@pytest.fixture
def client(project: Path) -> TestClient:
    return TestClient(create_app(project_root=project))


def _id(root: Path, label: str) -> str:
    return next(e.id for e in node_ops.list_nodes(root=root) if e.label == label)


def test_element(client: TestClient, project: Path) -> None:
    r = client.post("/api/mcda/element", json={"node": "Supplier A", "element": "option"})
    assert r.status_code == 200
    assert r.json()["result"] == {"target_id": _id(project, "Supplier A"), "element": "option"}
    assert r.json()["commit_sha"] == git.head_sha(project)
    assert mcda.get_elements(root=project) == {_id(project, "Supplier A"): "option"}


def test_element_errors(client: TestClient, project: Path) -> None:
    bad = client.post("/api/mcda/element", json={"node": "Cost", "element": "bogus"})
    assert bad.status_code == 422 and "not an MCDA element" in bad.json()["detail"]
    assert client.post("/api/mcda/element", json={"node": "Nope", "element": "option"}).status_code == 404
    assert client.post("/api/mcda/element", json={"element": "option"}).status_code == 422
    assert mcda.get_elements(root=project) == {}


def test_model(client: TestClient, project: Path) -> None:
    assert client.get("/api/mcda/model").json() == {"elements": {}, "criteria": [], "scores": []}
    client.post("/api/mcda/element", json={"node": "Supplier A", "element": "option"})
    client.post("/api/mcda/element", json={"node": "Cost", "element": "criterion"})
    assert client.post("/api/mcda/criterion", json={"node": "Cost", "weight": 1, "direction": "lower"}).status_code == 200
    assert client.post("/api/mcda/score", json={"option": "Supplier A", "criterion": "Cost",
                                                "value": 3}).status_code == 200
    m = client.get("/api/mcda/model").json()
    assert m["elements"] == {_id(project, "Supplier A"): "option", _id(project, "Cost"): "criterion"}
    assert [(c["weight"], c["direction"]) for c in m["criteria"]] == [(1, "lower")]
    assert [(s["target_id"], s["criterion"], s["value"]) for s in m["scores"]] == [
        (_id(project, "Supplier A"), _id(project, "Cost"), 3)]
