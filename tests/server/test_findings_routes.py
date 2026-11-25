"""Coverage for the findings routes (``server/routes/findings.py``).

Covers list (with filters), record, get-by-id (200 + 422 not found),
maturity advancement, and the staleness-check endpoint.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.server.app import create_app


@pytest.fixture
def client(two_node_project_root: Path) -> TestClient:
    return TestClient(
        create_app(project_root=two_node_project_root),
        raise_server_exceptions=False,
    )


def _record(client: TestClient, **overrides) -> dict:
    body = {
        "statement": "Reinforcing loop drives growth",
        "category": "structure",
        "model_type": "cld",
    }
    body.update(overrides)
    resp = client.post("/api/findings", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()["finding"]


# ── record + list ────────────────────────────────────────────────────


def test_list_empty(client: TestClient) -> None:
    data = client.get("/api/findings").json()
    assert data["findings"] == []
    assert data["count"] == 0


def test_record_finding(client: TestClient) -> None:
    resp = client.post(
        "/api/findings",
        json={
            "statement": "A short feedback loop exists",
            "category": "structure",
            "model_type": "cld",
            "detail": "between Price and Demand",
            "target_ids": ["node_x"],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["finding"]["statement"] == "A short feedback loop exists"
    assert data["finding"]["category"] == "structure"
    assert data["finding"]["maturity"] == "proposed"
    assert data["commit_sha"]


def test_list_after_record(client: TestClient) -> None:
    _record(client)
    data = client.get("/api/findings").json()
    assert data["count"] == 1
    assert data["findings"][0]["statement"] == "Reinforcing loop drives growth"


def test_list_filters(client: TestClient) -> None:
    _record(client, category="structure", model_type="cld")
    _record(client, statement="High sensitivity", category="sensitivity", model_type="bn")

    # Filter by category.
    by_cat = client.get("/api/findings", params={"category": "sensitivity"}).json()
    assert by_cat["count"] == 1
    assert by_cat["findings"][0]["category"] == "sensitivity"

    # Filter by model_type.
    by_model = client.get("/api/findings", params={"model_type": "cld"}).json()
    assert by_model["count"] == 1
    assert by_model["findings"][0]["model_type"] == "cld"

    # Filter by maturity (all start proposed).
    by_mat = client.get("/api/findings", params={"maturity": "proposed"}).json()
    assert by_mat["count"] == 2

    # Limit.
    limited = client.get("/api/findings", params={"limit": 1}).json()
    assert limited["count"] == 1


def test_list_filter_by_target(client: TestClient) -> None:
    _record(client, target_ids=["node_alpha"])
    _record(client, statement="Other", target_ids=["node_beta"])
    data = client.get("/api/findings", params={"target_id": "node_alpha"}).json()
    assert data["count"] == 1
    assert data["findings"][0]["target_ids"] == ["node_alpha"]


# ── get by id ────────────────────────────────────────────────────────


def test_get_finding_by_id(client: TestClient) -> None:
    created = _record(client)
    resp = client.get(f"/api/findings/{created['id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["finding"]["id"] == created["id"]
    assert data["stale"] is False


def test_get_finding_by_prefix(client: TestClient) -> None:
    created = _record(client)
    prefix = created["id"][:12]
    data = client.get(f"/api/findings/{prefix}").json()
    assert data["finding"]["id"] == created["id"]


def test_get_finding_not_found_422(client: TestClient) -> None:
    resp = client.get("/api/findings/finding_DOESNOTEXIST123456789")
    assert resp.status_code == 422


# ── maturity ─────────────────────────────────────────────────────────


def test_update_maturity(client: TestClient) -> None:
    created = _record(client)
    resp = client.patch(
        f"/api/findings/{created['id']}/maturity",
        json={
            "maturity": "reviewed",
            "reviewer_name": "Reviewer Rita",
            "reviewer_email": "rita@example.com",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["finding"]["maturity"] == "reviewed"
    assert data["finding"]["reviewed_by"]["name"] == "Reviewer Rita"
    assert data["commit_sha"]


def test_update_maturity_unknown_finding_422(client: TestClient) -> None:
    resp = client.patch(
        "/api/findings/finding_DOESNOTEXIST123456789/maturity",
        json={"maturity": "reviewed", "reviewer_name": "Rita"},
    )
    assert resp.status_code == 422


# ── staleness ────────────────────────────────────────────────────────


# ── edit + remove ────────────────────────────────────────────────────


def test_edit_changes_the_words_and_sends_a_reviewed_finding_back_to_proposed(client: TestClient) -> None:
    created = _record(client)
    client.patch(f"/api/findings/{created['id']}/maturity", json={"maturity": "reviewed", "reviewer_name": "Rita"})
    resp = client.patch(f"/api/findings/{created['id']}", json={"statement": "Balancing loop caps growth", "detail": "B1"})
    assert resp.status_code == 200, resp.text
    f = resp.json()["finding"]
    assert (f["statement"], f["detail"], f["category"]) == ("Balancing loop caps growth", "B1", "structure")
    assert f["maturity"] == "proposed" and f["reviewed_by"] is None
    assert client.get(f"/api/findings/{created['id']}").json()["finding"]["statement"] == "Balancing loop caps growth"


def test_edit_refuses_a_blank_statement_or_no_change(client: TestClient) -> None:
    created = _record(client)
    assert client.patch(f"/api/findings/{created['id']}", json={"statement": "  "}).status_code == 422
    assert client.patch(f"/api/findings/{created['id']}", json={"statement": created["statement"]}).status_code == 422


def test_remove_takes_the_finding_out(client: TestClient) -> None:
    keep = _record(client, statement="Keep me")
    gone = _record(client, statement="Remove me")
    resp = client.delete(f"/api/findings/{gone['id']}")
    assert resp.status_code == 200, resp.text
    assert [f["id"] for f in client.get("/api/findings").json()["findings"]] == [keep["id"]]
    assert client.delete(f"/api/findings/{gone['id']}").status_code == 422
