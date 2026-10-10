"""Tests for the two-step AI preview → apply/reject flow."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.ai import proposals as P
from latris.ai.adapters.base import ChatResult
from latris.ai.adapters.mock_adapter import MockAdapter
from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations.init import init_project
from latris.server.app import create_app


@pytest.fixture(autouse=True)
def _mock_mode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LATRIS_AI_MOCK", "1")
    MockAdapter.reset_shared()
    yield
    MockAdapter.reset_shared()


@pytest.fixture
def project(tmp_path: Path, git_identity) -> Path:
    root = tmp_path / "demo"
    init_project(root, statement="Q?")
    node_ops.add_node("Price", kind="variable", root=root)
    node_ops.add_node("Demand", kind="variable", root=root)
    return root


@pytest.fixture
def client(project: Path) -> TestClient:
    return TestClient(create_app(project_root=project), raise_server_exceptions=False)


def _register_draft(project: Path):
    """Register a DraftModelProposal mock with two framings."""
    MockAdapter.shared().register_default(
        response_cls=P.DraftModelProposal,
        result=ChatResult(
            parsed=P.DraftModelProposal(
                framings=[
                    P.DraftFraming(
                        name="Framing A",
                        entities=[P.DraftEntity(label="Supply", kind="variable")],
                        edges=[P.DraftEdge(from_label="Supply", to_label="Demand")],
                        rationale="Supply-side.",
                    ),
                    P.DraftFraming(
                        name="Framing B",
                        entities=[P.DraftEntity(label="Cost", kind="variable")],
                        edges=[P.DraftEdge(from_label="Cost", to_label="Price")],
                        rationale="Cost-driven.",
                    ),
                ],
            ),
            raw="(raw)",
            model_id="mock-model",
            token_usage={"input_tokens": 50, "output_tokens": 100},
            cost_usd=0.002,
        ),
    )


def _register_connections(project: Path):
    """Register a NewConnectionsProposal mock."""
    nodes = node_ops.list_nodes(project)
    id_map = {n.label: n.id for n in nodes}
    MockAdapter.shared().register_default(
        response_cls=P.NewConnectionsProposal,
        result=ChatResult(
            parsed=P.NewConnectionsProposal(
                proposals=[
                    P.EdgeProposal(
                        from_id=id_map["Demand"], to_id=id_map["Price"], kind="causal", rationale="Feedback."
                    ),
                    P.EdgeProposal(from_id=id_map["Price"], to_id=id_map["Demand"], kind="temporal", rationale="Lag."),
                ],
            ),
            raw="(raw)",
            model_id="mock-model",
        ),
    )


def _register_explain():
    """Register a read-only ExplainThisElement mock."""
    MockAdapter.shared().register_default(
        response_cls=P.ExplanationResult,
        result=ChatResult(
            parsed=P.ExplanationResult(explanation="Test explanation.", referenced_ids=[]),
            raw="(mock)",
            model_id="mock-model",
            token_usage={"input_tokens": 10, "output_tokens": 20},
            cost_usd=0.001,
        ),
    )


# ── Preview returns pending proposal ─────────────────────────────────


def test_preview_draft_returns_pending_with_proposal(client: TestClient, project: Path) -> None:
    _register_draft(project)
    resp = client.post(
        "/api/ai/call",
        json={
            "prompt_name": "DraftConceptualModel",
            "inputs": {"focus": "pricing"},
            "auto_apply": False,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["adoption"] == "pending"
    assert data["applied_ids"] == []
    assert data["proposal"] is not None
    assert len(data["proposal"]["framings"]) == 2
    assert data["interaction_id"]

    # Substrate unchanged — still only Price + Demand
    nodes = node_ops.list_nodes(project)
    assert {n.label for n in nodes} == {"Price", "Demand"}


def test_preview_connections_returns_pending(client: TestClient, project: Path) -> None:
    _register_connections(project)
    resp = client.post(
        "/api/ai/call",
        json={
            "prompt_name": "FindNewConnections",
            "inputs": {},
            "auto_apply": False,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["adoption"] == "pending"
    assert data["proposal"] is not None
    assert len(data["proposal"]["proposals"]) == 2

    # No new edges created
    edges = edge_ops.list_edges(project)
    assert len(edges) == 0


# ── Read-only prompts ignore auto_apply ──────────────────────────────


def test_preview_read_only_still_auto_approves(client: TestClient, project: Path) -> None:
    _register_explain()
    nodes = client.get("/api/nodes").json()
    resp = client.post(
        "/api/ai/call",
        json={
            "prompt_name": "ExplainThisElement",
            "inputs": {"target_id": nodes[0]["id"]},
            "auto_apply": False,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["adoption"] == "approved"
    assert data["proposal"] is not None
    assert data["proposal"]["explanation"] == "Test explanation."


# ── Apply endpoint ───────────────────────────────────────────────────


def test_apply_draft_creates_nodes_and_edges(client: TestClient, project: Path) -> None:
    _register_draft(project)

    # Preview
    resp = client.post(
        "/api/ai/call",
        json={
            "prompt_name": "DraftConceptualModel",
            "inputs": {"focus": "pricing"},
            "auto_apply": False,
        },
    )
    interaction_id = resp.json()["interaction_id"]

    # Apply framing index 1 (Cost-driven)
    resp = client.post(f"/api/ai/apply/{interaction_id}", json={"selected_index": 1})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["applied_ids"]) > 0

    # Verify substrate changed
    nodes = node_ops.list_nodes(project)
    labels = {n.label for n in nodes}
    assert "Cost" in labels  # framing B
    assert "Supply" not in labels  # framing A was NOT applied


def test_apply_connections_with_indices(client: TestClient, project: Path) -> None:
    _register_connections(project)

    # Preview
    resp = client.post(
        "/api/ai/call",
        json={
            "prompt_name": "FindNewConnections",
            "inputs": {},
            "auto_apply": False,
        },
    )
    interaction_id = resp.json()["interaction_id"]

    # Apply only the first proposal
    resp = client.post(f"/api/ai/apply/{interaction_id}", json={"approved_indices": [0]})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["applied_ids"]) == 1

    edges = edge_ops.list_edges(project)
    assert len(edges) == 1
    assert edges[0].kind == "causal"  # only the first proposal (causal)


# ── Reject endpoint ──────────────────────────────────────────────────


def test_reject_marks_interaction_rejected(client: TestClient, project: Path) -> None:
    _register_draft(project)

    resp = client.post(
        "/api/ai/call",
        json={
            "prompt_name": "DraftConceptualModel",
            "inputs": {"focus": "pricing"},
            "auto_apply": False,
        },
    )
    interaction_id = resp.json()["interaction_id"]

    resp = client.post(f"/api/ai/reject/{interaction_id}")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # Substrate unchanged
    nodes = node_ops.list_nodes(project)
    assert {n.label for n in nodes} == {"Price", "Demand"}

    # Interaction marked as rejected
    interactions = client.get("/api/ai/interactions").json()
    assert interactions[0]["adoption"] == "rejected"


# ── Error cases ──────────────────────────────────────────────────────


def test_apply_already_approved_returns_409(client: TestClient, project: Path) -> None:
    _register_draft(project)

    resp = client.post(
        "/api/ai/call",
        json={
            "prompt_name": "DraftConceptualModel",
            "inputs": {"focus": "pricing"},
            "auto_apply": False,
        },
    )
    interaction_id = resp.json()["interaction_id"]

    # Apply once
    client.post(f"/api/ai/apply/{interaction_id}", json={"selected_index": 0})

    # Try to apply again
    resp = client.post(f"/api/ai/apply/{interaction_id}", json={"selected_index": 0})
    assert resp.status_code == 409


def test_reject_already_rejected_returns_409(client: TestClient, project: Path) -> None:
    _register_draft(project)

    resp = client.post(
        "/api/ai/call",
        json={
            "prompt_name": "DraftConceptualModel",
            "inputs": {"focus": "pricing"},
            "auto_apply": False,
        },
    )
    interaction_id = resp.json()["interaction_id"]

    client.post(f"/api/ai/reject/{interaction_id}")
    resp = client.post(f"/api/ai/reject/{interaction_id}")
    assert resp.status_code == 409


# ── Auto-apply still works (backward compat) ────────────────────────


def test_auto_apply_true_applies_immediately(client: TestClient, project: Path) -> None:
    _register_draft(project)

    resp = client.post(
        "/api/ai/call",
        json={
            "prompt_name": "DraftConceptualModel",
            "inputs": {"focus": "pricing"},
            "auto_apply": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["adoption"] == "approved"
    assert len(data["applied_ids"]) > 0
    assert data["proposal"] is None  # no proposal in auto-apply mode

    # Substrate changed — framing 0 applied by default
    nodes = node_ops.list_nodes(project)
    labels = {n.label for n in nodes}
    assert "Supply" in labels
