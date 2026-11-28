"""Server route tests for /api/dt/*: node types, payoffs, uncertainties and settings."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.operations import decision_tree as dt
from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations.init import init_project
from latris.repo import git
from latris.server.app import create_app


@pytest.fixture
def project(tmp_path: Path, git_identity) -> Path:
    root = tmp_path / "launch"
    init_project(root, statement="Should we launch?")
    for n in ("Launch", "Market", "Good", "Bad"):
        node_ops.add_node(n, root=root)
    for a, b in (("Launch", "Market"), ("Market", "Good"), ("Market", "Bad")):
        edge_ops.add_edge(a, b, root=root)
    return root


@pytest.fixture
def client(project: Path) -> TestClient:
    return TestClient(create_app(project_root=project))


@pytest.fixture
def staged(client: TestClient) -> TestClient:
    for node, element in (("Launch", "decision"), ("Market", "chance"), ("Good", "terminal"), ("Bad", "terminal")):
        assert client.post("/api/dt/element", json={"node": node, "element": element}).status_code == 200
    return client


def _id(root: Path, label: str) -> str:
    return next(e.id for e in node_ops.list_nodes(root=root) if e.label == label)


def test_element(client: TestClient, project: Path) -> None:
    r = client.post("/api/dt/element", json={"node": "Launch", "element": "decision"})
    assert r.status_code == 200
    assert r.json()["result"] == {"target_id": _id(project, "Launch"), "element": "decision"}
    assert r.json()["commit_sha"] == git.head_sha(project)
    assert dt.get_elements(root=project) == {_id(project, "Launch"): "decision"}
    assert client.get("/api/dt/tree").json()["elements"] == {_id(project, "Launch"): "decision"}


def test_element_errors(client: TestClient, project: Path) -> None:
    bad = client.post("/api/dt/element", json={"node": "Launch", "element": "bogus"})
    assert bad.status_code == 422 and "not a decision-tree node type" in bad.json()["detail"]
    assert client.post("/api/dt/element", json={"node": "Nope", "element": "decision"}).status_code == 404
    # A node type belongs to a factor, never to a link.
    link = client.post("/api/dt/element", json={"node": "Launch -> Market", "element": "decision"})
    assert link.status_code == 422 and "is a link" in link.json()["detail"]
    assert dt.get_elements(root=project) == {}


def test_payoff(staged: TestClient, project: Path) -> None:
    r = staged.post("/api/dt/payoff", json={"node": "Good", "value": 100, "source_id": "forecast"})
    assert r.status_code == 200
    body = r.json()
    assert body["result"]["value"] == 100 and body["result"]["source_id"] == "forecast"
    assert body["commit_sha"] == git.head_sha(project)
    (entry,) = dt.get_payoffs(root=project).entries
    assert (entry.target_id, entry.value) == (_id(project, "Good"), 100)


def test_payoff_errors(staged: TestClient, project: Path) -> None:
    chance = staged.post("/api/dt/payoff", json={"node": "Market", "value": 100})
    assert chance.status_code == 422 and "not a terminal node" in chance.json()["detail"]
    assert staged.post("/api/dt/payoff", json={"node": "Nope", "value": 100}).status_code == 404
    assert staged.post("/api/dt/payoff", json={"node": "Good", "value": "x"}).status_code == 422
    # JSON NaN / Infinity aren't payoffs (stored, NaN would read back as null).
    for bad in ("NaN", "Infinity", "-Infinity"):
        r = staged.post("/api/dt/payoff", content='{"node": "Good", "value": ' + bad + "}",
                        headers={"content-type": "application/json"})
        assert r.status_code == 422, bad
    assert dt.get_payoffs(root=project).entries == []


def test_uncertainty(staged: TestClient, project: Path) -> None:
    r = staged.post("/api/dt/uncertainty", json={"node": "Market", "uncertainty": " Demand "})
    assert r.status_code == 200 and r.json()["result"]["uncertainty"] == "Demand"
    assert r.json()["commit_sha"] == git.head_sha(project)
    assert [(e.target_id, e.uncertainty) for e in dt.get_chances(root=project).entries] == [
        (_id(project, "Market"), "Demand")]


def test_uncertainty_errors(staged: TestClient, project: Path) -> None:
    blank = staged.post("/api/dt/uncertainty", json={"node": "Market", "uncertainty": "  "})
    assert blank.status_code == 422 and "give the uncertainty a name" in blank.json()["detail"]
    assert staged.post("/api/dt/uncertainty", json={"node": "Good", "uncertainty": "Demand"}).status_code == 422
    assert staged.post("/api/dt/uncertainty", json={"node": "Nope", "uncertainty": "Demand"}).status_code == 404
    assert staged.post("/api/dt/uncertainty", json={"node": "Market"}).status_code == 422
    assert dt.get_chances(root=project).entries == []


def test_settings(client: TestClient, project: Path) -> None:
    r = client.post("/api/dt/settings", json={"objective": "minimise", "units": "£"})
    assert r.status_code == 200 and r.json()["result"] == {"objective": "minimise", "units": "£"}
    assert r.json()["commit_sha"] == git.head_sha(project)
    # Only what's sent changes; an empty units clears them.
    r = client.post("/api/dt/settings", json={"units": ""})
    assert r.json()["result"] == {"objective": "minimise", "units": None}
    s = dt.get_settings(root=project)
    assert (s.objective, s.units) == ("minimise", None)


def test_settings_errors(client: TestClient, project: Path) -> None:
    bad = client.post("/api/dt/settings", json={"objective": "bogus"})
    assert bad.status_code == 422 and "maximise" in bad.json()["detail"]
    assert dt.get_settings(root=project).objective == "maximise"
