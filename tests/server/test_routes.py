"""Tests for CRUD API endpoints (G2)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.repo import git
from latris.server.app import create_app


@pytest.fixture
def project(empty_project_root: Path) -> Path:
    return empty_project_root


@pytest.fixture
def client(project: Path) -> TestClient:
    app = create_app(project_root=project)
    return TestClient(app)


def _commit_count(root: Path) -> int:
    return int(git.run_git(["rev-list", "--count", "HEAD"], cwd=root).stdout.strip())


# ── Nodes ─────────────────────────────────────────────────────────────


def test_add_and_list_nodes(client: TestClient) -> None:
    resp = client.post("/api/nodes", json={"label": "Price", "kind": "variable"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["result"]["label"] == "Price"
    assert data["result"]["kind"] == "variable"
    assert len(data["commit_sha"]) == 40

    nodes = client.get("/api/nodes").json()
    assert len(nodes) == 1
    assert nodes[0]["label"] == "Price"


def test_get_node_by_query(client: TestClient) -> None:
    resp = client.post("/api/nodes", json={"label": "Demand"})
    node_id = resp.json()["result"]["id"]

    got = client.get(f"/api/nodes/{node_id}")
    assert got.status_code == 200
    assert got.json()["label"] == "Demand"


def test_rename_node(client: TestClient) -> None:
    resp = client.post("/api/nodes", json={"label": "Price"})
    node_id = resp.json()["result"]["id"]

    renamed = client.patch(f"/api/nodes/{node_id}", json={"new_label": "Retail Price"})
    assert renamed.status_code == 200
    assert renamed.json()["result"]["label"] == "Retail Price"


def test_remove_node_cascades_edges(client: TestClient) -> None:
    a = client.post("/api/nodes", json={"label": "A"}).json()["result"]["id"]
    b = client.post("/api/nodes", json={"label": "B"}).json()["result"]["id"]
    client.post("/api/edges", json={"from_query": a, "to_query": b})

    resp = client.delete(f"/api/nodes/{a}")
    assert resp.status_code == 200
    assert len(resp.json()["removed_edge_ids"]) == 1
    assert client.get("/api/edges").json() == []


def test_get_nonexistent_node_404(client: TestClient) -> None:
    resp = client.get("/api/nodes/node_DOESNOTEXIST1234567890ABC")
    assert resp.status_code == 404


# ── Edges ─────────────────────────────────────────────────────────────


def test_add_and_list_edges(client: TestClient) -> None:
    a = client.post("/api/nodes", json={"label": "X"}).json()["result"]["id"]
    b = client.post("/api/nodes", json={"label": "Y"}).json()["result"]["id"]

    resp = client.post("/api/edges", json={"from_query": a, "to_query": b, "kind": "causal"})
    assert resp.status_code == 201
    edge = resp.json()["result"]
    assert edge["from_id"] == a
    assert edge["to_id"] == b

    edges = client.get("/api/edges").json()
    assert len(edges) == 1


def test_remove_edge(client: TestClient) -> None:
    a = client.post("/api/nodes", json={"label": "X"}).json()["result"]["id"]
    b = client.post("/api/nodes", json={"label": "Y"}).json()["result"]["id"]
    edge_id = client.post("/api/edges", json={"from_query": a, "to_query": b}).json()["result"]["id"]

    resp = client.delete(f"/api/edges/{edge_id}")
    assert resp.status_code == 200
    assert client.get("/api/edges").json() == []


def test_self_loop_rejected(client: TestClient) -> None:
    a = client.post("/api/nodes", json={"label": "X"}).json()["result"]["id"]
    resp = client.post("/api/edges", json={"from_query": a, "to_query": a})
    assert resp.status_code == 422


# ── Attributes ────────────────────────────────────────────────────────


def test_set_attribute(client: TestClient, project: Path) -> None:
    """Per-attribute mature endpoint was removed when maturity moved to
    the parent Entity/Edge — see docs/design/MATURITY_LADDER.md."""
    node_id = client.post("/api/nodes", json={"label": "Price"}).json()["result"]["id"]

    resp = client.put(f"/api/attributes/{node_id}/description", json={"value": "Retail price level"})
    assert resp.status_code == 200
    assert resp.json()["target_id"] == node_id


# ── References ────────────────────────────────────────────────────────


def test_add_reference(client: TestClient) -> None:
    resp = client.post(
        "/api/references",
        json={
            "bibkey": "smith2022",
            "title": "A Study",
            "year": 2022,
        },
    )
    assert resp.status_code == 201
    assert resp.json()["result"]["bibkey"] == "smith2022"

    refs = client.get("/api/references").json()
    assert len(refs) == 1


def test_duplicate_bibkey_rejected(client: TestClient) -> None:
    client.post("/api/references", json={"bibkey": "dup", "title": "First"})
    resp = client.post("/api/references", json={"bibkey": "dup", "title": "Second"})
    assert resp.status_code == 422


# ── Evidence ──────────────────────────────────────────────────────────


def test_attach_evidence(client: TestClient) -> None:
    node_id = client.post("/api/nodes", json={"label": "Price"}).json()["result"]["id"]
    client.put(f"/api/attributes/{node_id}/description", json={"value": "A desc"})
    client.post("/api/references", json={"bibkey": "ref1", "title": "Ref"})

    resp = client.post(
        "/api/evidence",
        json={
            "target": node_id,
            "attribute": "description",
            "bibkey": "ref1",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["result"]["bibkey"] == "ref1"


# ── Provenance ────────────────────────────────────────────────────────


def test_add_assumption(client: TestClient) -> None:
    resp = client.post(
        "/api/provenance/assumptions",
        json={
            "statement": "Market is liquid",
            "rationale": "Industry norm",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["result"]["statement"] == "Market is liquid"


def test_add_question(client: TestClient) -> None:
    resp = client.post("/api/provenance/questions", json={"question": "Is this causal?"})
    assert resp.status_code == 201
    assert "causal" in resp.json()["result"]["question"]


def test_log_decision(client: TestClient) -> None:
    resp = client.post(
        "/api/provenance/decisions",
        json={
            "statement": "Use CLD",
            "rationale": "Best for this scope",
        },
    )
    assert resp.status_code == 201


# ── Challenges ────────────────────────────────────────────────────────


def test_challenge_lifecycle(client: TestClient) -> None:
    a = client.post("/api/nodes", json={"label": "A"}).json()["result"]["id"]
    b = client.post("/api/nodes", json={"label": "B"}).json()["result"]["id"]
    edge_id = client.post("/api/edges", json={"from_query": a, "to_query": b}).json()["result"]["id"]

    # Open
    resp = client.post(
        "/api/challenges",
        json={
            "target": edge_id,
            "argument": "Direction may be wrong",
        },
    )
    assert resp.status_code == 201
    ch_id = resp.json()["result"]["id"]

    # Add turn
    resp = client.post(f"/api/challenges/{ch_id}/turns", json={"message": "Good point"})
    assert resp.status_code == 201

    # Resolve
    resp = client.post(
        f"/api/challenges/{ch_id}/resolve",
        json={
            "state": "retained-with-caveat",
            "rationale": "Noted as caveat",
        },
    )
    assert resp.status_code == 200

    # List
    challenges = client.get("/api/challenges").json()
    assert len(challenges) == 1
    assert challenges[0]["state"] == "retained-with-caveat"


# ── Undo ──────────────────────────────────────────────────────────────


def test_undo_reverts_last_commit(client: TestClient, project: Path) -> None:
    client.post("/api/nodes", json={"label": "Ghost"})
    assert len(client.get("/api/nodes").json()) == 1

    resp = client.post("/api/history/undo")
    assert resp.status_code == 200
    assert len(resp.json()["commit_sha"]) == 40

    # Node should be gone after undo
    assert len(client.get("/api/nodes").json()) == 0


# ── Commit counting ──────────────────────────────────────────────────


def test_mutation_creates_commit(client: TestClient, project: Path) -> None:
    before = _commit_count(project)
    client.post("/api/nodes", json={"label": "CommitTest"})
    assert _commit_count(project) == before + 1
