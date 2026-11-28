"""Server route tests for /api/ach/*: hypotheses and evidence items, and the matrix."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.operations import ach
from latris.operations import nodes as node_ops
from latris.operations.init import init_project
from latris.repo import git
from latris.server.app import create_app


@pytest.fixture
def project(tmp_path: Path, git_identity) -> Path:
    root = tmp_path / "breach"
    init_project(root, statement="Who caused the breach?")
    for n in ("Insider", "Outsider", "Log gap"):
        node_ops.add_node(n, root=root)
    return root


@pytest.fixture
def client(project: Path) -> TestClient:
    return TestClient(create_app(project_root=project))


def _id(root: Path, label: str) -> str:
    return next(e.id for e in node_ops.list_nodes(root=root) if e.label == label)


def test_element(client: TestClient, project: Path) -> None:
    r = client.post("/api/ach/element", json={"node": "Insider", "element": "hypothesis"})
    assert r.status_code == 200
    assert r.json()["result"] == {"target_id": _id(project, "Insider"), "element": "hypothesis"}
    assert r.json()["commit_sha"] == git.head_sha(project)
    assert ach.get_elements(root=project) == {_id(project, "Insider"): "hypothesis"}


def test_element_errors(client: TestClient, project: Path) -> None:
    bad = client.post("/api/ach/element", json={"node": "Insider", "element": "bogus"})
    assert bad.status_code == 422 and "not an ACH element" in bad.json()["detail"]
    assert client.post("/api/ach/element", json={"node": "Nope", "element": "hypothesis"}).status_code == 404
    assert ach.get_elements(root=project) == {}


def test_item_and_matrix(client: TestClient, project: Path) -> None:
    client.post("/api/ach/element", json={"node": "Insider", "element": "hypothesis"})
    client.post("/api/ach/element", json={"node": "Log gap", "element": "evidence_item"})
    r = client.post("/api/ach/item", json={"node": "Log gap", "credibility": "high", "relevance": "low"})
    assert r.status_code == 200
    assert (r.json()["result"]["credibility"], r.json()["result"]["relevance"]) == ("high", "low")
    assert r.json()["commit_sha"] == git.head_sha(project)
    # Only the fields sent change.
    r = client.post("/api/ach/item", json={"node": "Log gap", "notes": "seen twice"})
    assert r.status_code == 200
    (item,) = ach.get_items(root=project).entries
    assert (item.credibility, item.relevance, item.notes) == ("high", "low", "seen twice")

    assert client.post("/api/ach/rating", json={"item": "Log gap", "hypothesis": "Insider",
                                                "rating": "c"}).status_code == 200
    m = client.get("/api/ach/matrix").json()
    assert m["elements"] == {_id(project, "Insider"): "hypothesis", _id(project, "Log gap"): "evidence_item"}
    assert [i["notes"] for i in m["items"]] == ["seen twice"]
    assert [x["rating"] for x in m["ratings"]] == ["C"]


def test_item_errors(client: TestClient, project: Path) -> None:
    client.post("/api/ach/element", json={"node": "Insider", "element": "hypothesis"})
    client.post("/api/ach/element", json={"node": "Log gap", "element": "evidence_item"})
    assert client.post("/api/ach/item", json={"node": "Log gap", "credibility": "bogus"}).status_code == 422
    empty = client.post("/api/ach/item", json={"node": "Log gap"})
    assert empty.status_code == 422 and "nothing to set" in empty.json()["detail"]
    hyp = client.post("/api/ach/item", json={"node": "Insider", "credibility": "high"})
    assert hyp.status_code == 422 and "is a hypothesis" in hyp.json()["detail"]
    assert client.post("/api/ach/item", json={"node": "Nope", "credibility": "high"}).status_code == 404
    assert ach.get_items(root=project).entries == []
    assert client.get("/api/ach/matrix").json()["items"] == []
