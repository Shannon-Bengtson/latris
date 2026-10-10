"""Error path and edge case tests for API endpoints (T11-T14)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.operations import challenges as ch_ops
from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.server.app import create_app


@pytest.fixture
def project(empty_project_root: Path) -> Path:
    return empty_project_root


@pytest.fixture
def client(project: Path) -> TestClient:
    return TestClient(create_app(project_root=project), raise_server_exceptions=False)


@pytest.fixture
def project_with_edge(project: Path):
    """Adds nodes+edge to the (shared) ``project`` so ``client`` sees them."""
    a, _ = node_ops.add_node("A", root=project)
    b, _ = node_ops.add_node("B", root=project)
    edge, _ = edge_ops.add_edge(a.id, b.id, root=project)
    return project, a, b, edge


# ── T11: Edge error cases ────────────────────────────────────────────


def test_add_edge_nonexistent_source_404(client: TestClient, project: Path) -> None:
    b, _ = node_ops.add_node("B", root=project)
    resp = client.post(
        "/api/edges",
        json={
            "from_query": "node_DOESNOTEXIST12345678ABCDE",
            "to_query": b.id,
        },
    )
    assert resp.status_code == 404


def test_add_edge_nonexistent_target_404(client: TestClient, project: Path) -> None:
    a, _ = node_ops.add_node("A", root=project)
    resp = client.post(
        "/api/edges",
        json={
            "from_query": a.id,
            "to_query": "node_DOESNOTEXIST12345678ABCDE",
        },
    )
    assert resp.status_code == 404


def test_remove_nonexistent_edge_404(client: TestClient) -> None:
    resp = client.delete("/api/edges/edge_DOESNOTEXIST12345678ABCDE")
    assert resp.status_code == 404


# ── T12: Attribute error cases ───────────────────────────────────────


def test_attributes_mature_endpoint_removed(client: TestClient, project: Path) -> None:
    """Per-attribute mature endpoint was removed when maturity moved to
    the parent Entity/Edge — see docs/design/MATURITY_LADDER.md.
    Hitting the old path should return 404.
    """
    a, _ = node_ops.add_node("X", root=project)
    resp = client.post(f"/api/attributes/{a.id}/description/mature")
    assert resp.status_code == 404


def test_set_invalid_polarity_rejected(project: Path) -> None:
    """Polarity is now a CLD view attribute — invalid values are rejected
    by ``view_attributes.set_view_attribute``.  (Route not yet created;
    test exercises the operations layer directly.)"""
    from latris.operations import view_attributes as view_attr_ops

    a, _ = node_ops.add_node("X", root=project)
    with pytest.raises(ValueError, match="polarity must be"):
        view_attr_ops.set_view_attribute(a.id, "cld", "polarity", "maybe", root=project)


# ── T13: Evidence + challenge error cases ────────────────────────────


def test_evidence_unknown_bibkey_422(client: TestClient, project: Path) -> None:
    a, _ = node_ops.add_node("X", root=project)
    resp = client.post(
        "/api/evidence",
        json={
            "target": a.id,
            "attribute": "description",
            "bibkey": "no_such_ref",
        },
    )
    assert resp.status_code == 422


def test_challenge_nonexistent_target_404(client: TestClient) -> None:
    resp = client.post(
        "/api/challenges",
        json={
            "target": "node_DOESNOTEXIST12345678ABCDE",
            "argument": "This is wrong",
        },
    )
    assert resp.status_code == 404


def test_add_turn_to_resolved_challenge_422(client: TestClient, project_with_edge) -> None:
    project, _, _, edge = project_with_edge
    ch, _ = ch_ops.open_challenge(edge.id, "Wrong direction", root=project)
    ch_ops.resolve_challenge(ch.id, "retained-unchanged", root=project)
    resp = client.post(f"/api/challenges/{ch.id}/turns", json={"message": "But..."})
    assert resp.status_code == 422


# ── T14: Undo edge cases ────────────────────────────────────────────


def test_undo_on_initial_commit_succeeds(client: TestClient) -> None:
    """Modern git can revert even the root commit."""
    resp = client.post("/api/history/undo")
    assert resp.status_code == 200


def test_double_undo_restores_state(client: TestClient, project: Path) -> None:
    """Undo twice should restore the original state."""
    client.post("/api/nodes", json={"label": "Ghost"})
    assert len(client.get("/api/nodes").json()) == 1

    client.post("/api/history/undo")  # undo the add
    assert len(client.get("/api/nodes").json()) == 0

    client.post("/api/history/undo")  # undo the undo
    assert len(client.get("/api/nodes").json()) == 1
