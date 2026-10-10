"""Tests for AI call + interactions endpoints (T8)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.ai.adapters.base import ChatResult
from latris.ai.adapters.mock_adapter import MockAdapter
from latris.ai.proposals import ExplanationResult
from latris.operations import nodes as node_ops
from latris.operations.init import init_project
from latris.repo.layout import ProjectPaths
from latris.server.app import create_app


@pytest.fixture(autouse=True)
def _mock_mode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LATRIS_AI_MOCK", "1")
    MockAdapter.reset_shared()
    MockAdapter.shared().register_default(
        response_cls=ExplanationResult,
        result=ChatResult(
            parsed=ExplanationResult(
                explanation="Test explanation of the element.",
                referenced_ids=[],
            ),
            raw="(mock)",
            model_id="mock-model",
            token_usage={"input_tokens": 10, "output_tokens": 20},
            cost_usd=0.001,
        ),
    )
    yield
    MockAdapter.reset_shared()


@pytest.fixture
def project(tmp_path: Path, git_identity) -> Path:
    root = tmp_path / "demo"
    init_project(root, statement="Q?")
    node_ops.add_node("Price", kind="variable", root=root)
    return root


@pytest.fixture
def client(project: Path) -> TestClient:
    return TestClient(create_app(project_root=project), raise_server_exceptions=False)


def test_ai_call_explain_returns_outcome(client: TestClient, project: Path) -> None:
    nodes = client.get("/api/nodes").json()
    node_id = nodes[0]["id"]
    resp = client.post(
        "/api/ai/call",
        json={
            "prompt_name": "ExplainThisElement",
            "inputs": {"target_id": node_id},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["prompt_name"] == "ExplainThisElement"
    assert data["adoption"] == "approved"
    assert "explanation" in data["rendered"].lower() or len(data["rendered"]) > 0


def test_ai_interactions_populated_after_call(client: TestClient) -> None:
    nodes = client.get("/api/nodes").json()
    node_id = nodes[0]["id"]

    # Initially empty
    assert client.get("/api/ai/interactions").json() == []

    # After a call, there should be at least 1
    client.post(
        "/api/ai/call",
        json={
            "prompt_name": "ExplainThisElement",
            "inputs": {"target_id": node_id},
        },
    )
    interactions = client.get("/api/ai/interactions").json()
    assert len(interactions) >= 1


def test_ai_call_unknown_prompt_returns_422(client: TestClient) -> None:
    resp = client.post(
        "/api/ai/call",
        json={
            "prompt_name": "NoSuchPrompt",
            "inputs": {},
        },
    )
    assert resp.status_code == 422


def test_ai_call_tolerates_missing_cld_polarity_file(client: TestClient, project: Path) -> None:
    """Legacy projects may predate views/parameters/cld-polarity.yaml."""
    paths = ProjectPaths(project)
    paths.view_attribute_path("cld", "polarity").unlink()

    nodes = client.get("/api/nodes").json()
    node_id = nodes[0]["id"]
    resp = client.post(
        "/api/ai/call",
        json={
            "prompt_name": "ExplainThisElement",
            "inputs": {"target_id": node_id},
        },
    )

    assert resp.status_code == 200
