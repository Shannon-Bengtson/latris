"""Cross-stack integration test — exercises the full GUI↔API↔Python↔Git flow.

Uses httpx + FastAPI TestClient to test the actual HTTP contract between
the GUI and the server, without a browser.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.operations.init import init_project
from latris.server.app import create_app


@pytest.fixture
def client(tmp_path: Path, git_identity) -> TestClient:
    root = tmp_path / "proj"
    init_project(root, statement="What drives demand?")
    app = create_app(project_root=root)
    return TestClient(app)


def test_add_node_and_verify_in_state(client: TestClient) -> None:
    """Add a node via API and verify it appears in the full state."""
    resp = client.post("/api/nodes", json={"label": "Price", "kind": "variable"})
    assert resp.status_code in (200, 201)
    node_id = resp.json()["result"]["id"]
    assert node_id.startswith("node_")

    state = client.get("/api/state").json()
    entity_ids = [e["id"] for e in state["substrate"]["entities"]]
    assert node_id in entity_ids


def test_add_edge_and_verify(client: TestClient) -> None:
    """Add two nodes and an edge, verify the edge appears in state."""
    r1 = client.post("/api/nodes", json={"label": "A", "kind": "concept"})
    r2 = client.post("/api/nodes", json={"label": "B", "kind": "concept"})
    id_a = r1.json()["result"]["id"]
    id_b = r2.json()["result"]["id"]

    r3 = client.post("/api/edges", json={"from_query": id_a, "to_query": id_b, "kind": "causal"})
    assert r3.status_code in (200, 201)
    edge_id = r3.json()["result"]["id"]

    state = client.get("/api/state").json()
    edge_ids = [e["id"] for e in state["substrate"]["edges"]]
    assert edge_id in edge_ids


def test_set_attribute_and_verify(client: TestClient) -> None:
    """Set a description attribute and verify it appears in state."""
    r = client.post("/api/nodes", json={"label": "Demand"})
    node_id = r.json()["result"]["id"]

    client.put(
        f"/api/attributes/{node_id}/description",
        json={"value": "Consumer demand for the product"},
    )

    state = client.get("/api/state").json()
    entries = state["attributes"]["descriptions"]["entries"]
    target_entries = [e for e in entries if e["target_id"] == node_id]
    assert len(target_entries) == 1
    assert target_entries[0]["value"] == "Consumer demand for the product"


def test_full_workflow_node_edge_challenge(client: TestClient) -> None:
    """Exercise a realistic workflow: nodes → edge → challenge → resolve."""
    # Create nodes
    r1 = client.post("/api/nodes", json={"label": "Emissions", "kind": "variable"})
    r2 = client.post("/api/nodes", json={"label": "Air Quality", "kind": "variable"})
    n1 = r1.json()["result"]["id"]
    n2 = r2.json()["result"]["id"]

    # Create edge
    r3 = client.post("/api/edges", json={"from_query": n1, "to_query": n2, "kind": "causal"})
    edge_id = r3.json()["result"]["id"]

    # Open challenge on the edge
    r4 = client.post(
        "/api/challenges",
        json={
            "target": edge_id,
            "argument": "This link may be indirect via atmospheric chemistry",
        },
    )
    assert r4.status_code in (200, 201)
    ch_id = r4.json()["result"]["id"]

    # Verify challenge in state
    state = client.get("/api/state").json()
    challenges = state["challenges"]["entries"]
    assert any(c["id"] == ch_id for c in challenges)

    # Resolve the challenge
    r5 = client.post(
        f"/api/challenges/{ch_id}/resolve",
        json={
            "state": "retained-with-caveat",
            "rationale": "Accepted as simplification; noted in assumptions",
        },
    )
    assert r5.status_code == 200
    assert r5.json()["result"]["state"] == "retained-with-caveat"


def test_undo_reverts_last_operation(client: TestClient) -> None:
    """Undo should revert the last mutation."""
    # Add a node
    r = client.post("/api/nodes", json={"label": "Temporary"})
    node_id = r.json()["result"]["id"]

    # Verify it exists
    state = client.get("/api/state").json()
    assert any(e["id"] == node_id for e in state["substrate"]["entities"])

    # Undo
    r_undo = client.post("/api/history/undo")
    assert r_undo.status_code == 200

    # Verify it's gone
    state2 = client.get("/api/state").json()
    assert not any(e["id"] == node_id for e in state2["substrate"]["entities"])


def test_error_returns_detail(client: TestClient) -> None:
    """API should return structured error detail for bad entity references."""
    r = client.post(
        "/api/edges",
        json={
            "from_query": "nonexistent_a",
            "to_query": "nonexistent_b",
        },
    )
    assert r.status_code == 404
    body = r.json()
    assert "detail" in body
    assert "nonexistent_a" in body["detail"]
