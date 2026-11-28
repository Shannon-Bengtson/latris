"""Server route tests for /api/markov/*: states and strategies, transitions, rewards, the starting cohort."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.operations import edges as edge_ops
from latris.operations import markov
from latris.operations import nodes as node_ops
from latris.operations.init import init_project
from latris.repo import git
from latris.server.app import create_app


@pytest.fixture
def project(tmp_path: Path, git_identity) -> Path:
    root = tmp_path / "cohort"
    init_project(root, statement="Is the new drug worth its cost?")
    for n in ("Healthy", "Sick", "Dead", "New drug"):
        node_ops.add_node(n, root=root)
    for a, b in (("Healthy", "Sick"), ("Healthy", "Dead"), ("Sick", "Dead")):
        edge_ops.add_edge(a, b, root=root)
    return root


@pytest.fixture
def client(project: Path) -> TestClient:
    return TestClient(create_app(project_root=project))


@pytest.fixture
def staged(client: TestClient) -> TestClient:
    """Three states and one strategy."""
    for s in ("Healthy", "Sick", "Dead"):
        assert client.post("/api/markov/element", json={"node": s, "element": "state"}).status_code == 200
    assert client.post("/api/markov/element", json={"node": "New drug", "element": "strategy"}).status_code == 200
    return client


def _id(root: Path, label: str) -> str:
    return next(e.id for e in node_ops.list_nodes(root=root) if e.label == label)


def test_element_marks_a_state(client: TestClient, project: Path) -> None:
    r = client.post("/api/markov/element", json={"node": "Healthy", "element": "state"})
    assert r.status_code == 200
    body = r.json()
    assert body["result"] == {"target_id": _id(project, "Healthy"), "element": "state"}
    assert body["commit_sha"] == git.head_sha(project)
    assert markov.get_elements(root=project) == {_id(project, "Healthy"): "state"}


def test_element_errors(client: TestClient, project: Path) -> None:
    bad = client.post("/api/markov/element", json={"node": "Healthy", "element": "bogus"})
    assert bad.status_code == 422 and "not a Markov element" in bad.json()["detail"]
    assert client.post("/api/markov/element", json={"node": "Nope", "element": "state"}).status_code == 404
    assert client.post("/api/markov/element", json={"node": "Healthy"}).status_code == 422
    assert markov.get_elements(root=project) == {}


def test_transition(staged: TestClient, project: Path) -> None:
    r = staged.post("/api/markov/transition", json={"link": "Healthy -> Sick", "probability": 0.1,
                                                     "source_id": "registry"})
    assert r.status_code == 200
    body = r.json()
    assert body["result"]["probability"] == 0.1 and body["result"]["source_id"] == "registry"
    assert body["commit_sha"] == git.head_sha(project)
    r = staged.post("/api/markov/transition", json={"link": "Healthy -> Sick", "probability": 0.06,
                                                     "strategy": "New drug"})
    assert r.status_code == 200 and r.json()["result"]["strategy"] == _id(project, "New drug")
    on_disk = markov.get_transitions(root=project).entries
    assert sorted(e.probability for e in on_disk) == [0.06, 0.1]


def test_transition_errors(staged: TestClient, project: Path) -> None:
    assert staged.post("/api/markov/transition", json={"link": "Healthy -> Sick", "probability": 1.5}).status_code == 422
    assert staged.post("/api/markov/transition", json={"link": "Sick -> Healthy", "probability": 0.1}).status_code == 404
    assert staged.post("/api/markov/transition", json={"link": "edge_NOPE", "probability": 0.1}).status_code == 404
    bad = staged.post("/api/markov/transition", json={"link": "Healthy -> Sick", "probability": 0.1,
                                                       "strategy": "Sick"})
    assert bad.status_code == 422 and "not a strategy" in bad.json()["detail"]
    assert staged.post("/api/markov/transition", json={"link": "Healthy -> Sick"}).status_code == 422
    assert markov.get_transitions(root=project).entries == []


def test_reward(staged: TestClient, project: Path) -> None:
    r = staged.post("/api/markov/reward", json={"state": "Healthy", "cost": 100, "utility": 0.9})
    assert r.status_code == 200
    body = r.json()
    assert (body["result"]["cost"], body["result"]["utility"]) == (100, 0.9)
    assert body["commit_sha"] == git.head_sha(project)
    # Only the fields sent change.
    r = staged.post("/api/markov/reward", json={"state": "Healthy", "cost": 200})
    assert r.status_code == 200
    (entry,) = markov.get_rewards(root=project).entries
    assert (entry.cost, entry.utility) == (200, 0.9)


def test_reward_errors(staged: TestClient, project: Path) -> None:
    empty = staged.post("/api/markov/reward", json={"state": "Healthy"})
    assert empty.status_code == 422 and "nothing to set" in empty.json()["detail"]
    assert staged.post("/api/markov/reward", json={"state": "Nope", "cost": 1}).status_code == 404
    not_state = staged.post("/api/markov/reward", json={"state": "New drug", "cost": 1})
    assert not_state.status_code == 422 and "not a state" in not_state.json()["detail"]
    assert markov.get_rewards(root=project).entries == []


def test_start(staged: TestClient, project: Path) -> None:
    r = staged.post("/api/markov/start", json={"state": "Healthy", "proportion": 1})
    assert r.status_code == 200
    body = r.json()
    assert body["result"]["proportion"] == 1 and body["result"]["target_id"] == _id(project, "Healthy")
    assert body["commit_sha"] == git.head_sha(project)
    assert [e.proportion for e in markov.get_start(root=project).entries] == [1]
    assert staged.get("/api/markov/model").json()["start"][0]["proportion"] == 1


def test_start_errors(staged: TestClient, project: Path) -> None:
    assert staged.post("/api/markov/start", json={"state": "Healthy", "proportion": -1}).status_code == 422
    assert staged.post("/api/markov/start", json={"state": "Healthy", "proportion": 2}).status_code == 422
    assert staged.post("/api/markov/start", json={"state": "Nope", "proportion": 1}).status_code == 404
    assert staged.post("/api/markov/start", json={"state": "New drug", "proportion": 1}).status_code == 422
    assert markov.get_start(root=project).entries == []
