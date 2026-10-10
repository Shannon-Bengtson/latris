"""Server-side tests for ``/api/completeness/*`` routes (AI interrogation Phase 2c).

Exercises every endpoint in
:mod:`latris.server.routes.completeness`: report fetch, gate
``check`` (AI-mocked), and the three disposition transitions
(``override`` / ``dismiss`` / ``mark-added``) on both their happy path
and their 404 (unknown missing-variable id) path.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.ai.adapters import MockAdapter
from latris.ai.adapters.base import ChatResult
from latris.ai.proposals import (
    CompletenessGateResult,
    MissingVariableProposal,
)
from latris.operations.init import init_project
from latris.operations.nodes import add_node
from latris.server.app import create_app


@pytest.fixture(autouse=True)
def _ai_mock_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LATRIS_AI_MOCK", "1")
    MockAdapter.reset_shared()


@pytest.fixture
def project(tmp_path: Path, git_identity) -> Path:
    root = tmp_path / "demo"
    init_project(root, statement="What drives nutrient runoff?")
    add_node("Nutrient load", root=root)
    add_node("Algal bloom", root=root)
    return root


@pytest.fixture
def client(project: Path) -> TestClient:
    return TestClient(create_app(project_root=project))


def _register_gate_response(
    entries: list[MissingVariableProposal], coverage: float = 0.0
) -> None:
    """Stub the shared mock adapter with a CompletenessGateResult."""
    result = CompletenessGateResult(
        coverage_ratio=coverage,
        entries=entries,
        model_type="cld",
    )
    MockAdapter.shared().register_default(
        response_cls=CompletenessGateResult,
        result=ChatResult(parsed=result, raw="(mock gate)", model_id="mock"),
    )


def _rainfall_proposal() -> MissingVariableProposal:
    return MissingVariableProposal(
        name="Rainfall",
        rationale="Drives nutrient washout.",
        required_for=["Sensitivity claim"],
        severity="required",
        confidence="high",
    )


def _seed_one_entry(client: TestClient) -> str:
    """Run the gate via the route to create one open entry; return its id."""
    _register_gate_response([_rainfall_proposal()])
    resp = client.post("/api/completeness/cld/check", json={"claims": []})
    assert resp.status_code == 200
    entries = resp.json()["result"]["entries"]
    assert len(entries) == 1
    return entries[0]["id"]


# ── GET report ──────────────────────────────────────────────────────────


def test_get_report_empty_when_absent(client: TestClient) -> None:
    resp = client.get("/api/completeness/cld")
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert result["model_type"] == "cld"
    assert result["entries"] == []


def test_get_report_returns_persisted_entries(client: TestClient) -> None:
    mv_id = _seed_one_entry(client)
    resp = client.get("/api/completeness/cld")
    assert resp.status_code == 200
    entries = resp.json()["result"]["entries"]
    assert [mv["id"] for mv in entries] == [mv_id]
    assert entries[0]["name"] == "Rainfall"
    assert entries[0]["disposition"] == "open"


# ── POST check ──────────────────────────────────────────────────────────


def test_check_runs_gate_and_creates_entries(client: TestClient) -> None:
    _register_gate_response([_rainfall_proposal()])
    resp = client.post("/api/completeness/cld/check", json={"claims": ["a claim"]})
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert result["model_type"] == "cld"
    assert len(result["entries"]) == 1
    assert result["entries"][0]["name"] == "Rainfall"
    assert result["entries"][0]["disposition"] == "open"


def test_check_accepts_empty_body(client: TestClient) -> None:
    """CheckBody.claims defaults to [] — an empty JSON body is valid."""
    _register_gate_response([_rainfall_proposal()])
    resp = client.post("/api/completeness/cld/check", json={})
    assert resp.status_code == 200
    assert len(resp.json()["result"]["entries"]) == 1


# ── POST override ───────────────────────────────────────────────────────


def test_override_flips_disposition(client: TestClient) -> None:
    mv_id = _seed_one_entry(client)
    resp = client.post(
        f"/api/completeness/cld/{mv_id}/override",
        json={"rationale": "Out of scope for this study."},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["result"]["disposition"] == "excluded"
    assert body["result"]["excluded_via_id"] is not None
    assert body["commit_sha"]


def test_override_unknown_id_returns_404(client: TestClient) -> None:
    _seed_one_entry(client)
    resp = client.post(
        "/api/completeness/cld/missing-var_DOES_NOT_EXIST/override",
        json={"rationale": "x"},
    )
    assert resp.status_code == 404
    assert "no missing-variable" in resp.json()["detail"]


# ── POST dismiss ────────────────────────────────────────────────────────


def test_dismiss_flips_disposition(client: TestClient) -> None:
    mv_id = _seed_one_entry(client)
    resp = client.post(f"/api/completeness/cld/{mv_id}/dismiss")
    assert resp.status_code == 200
    body = resp.json()
    assert body["result"]["disposition"] == "dismissed"
    assert body["commit_sha"]


def test_dismiss_unknown_id_returns_404(client: TestClient) -> None:
    _seed_one_entry(client)
    resp = client.post("/api/completeness/cld/missing-var_NOPE/dismiss")
    assert resp.status_code == 404
    assert "no missing-variable" in resp.json()["detail"]


# ── POST mark-added ─────────────────────────────────────────────────────


def test_mark_added_records_entity(client: TestClient) -> None:
    mv_id = _seed_one_entry(client)
    resp = client.post(
        f"/api/completeness/cld/{mv_id}/mark-added",
        json={"entity_id": "node_RAINFALL"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["result"]["disposition"] == "added_to_model"
    assert body["result"]["added_entity_id"] == "node_RAINFALL"
    assert body["commit_sha"]


def test_mark_added_unknown_id_returns_404(client: TestClient) -> None:
    _seed_one_entry(client)
    resp = client.post(
        "/api/completeness/cld/missing-var_NOPE/mark-added",
        json={"entity_id": "node_X"},
    )
    assert resp.status_code == 404
    assert "no missing-variable" in resp.json()["detail"]
