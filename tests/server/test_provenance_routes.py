"""Tests for the 4 untested provenance endpoints (T10)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.server.app import create_app


@pytest.fixture
def project(empty_project_root: Path) -> Path:
    return empty_project_root


@pytest.fixture
def client(project: Path) -> TestClient:
    return TestClient(create_app(project_root=project))


def test_record_signoff(client: TestClient) -> None:
    resp = client.post(
        "/api/provenance/signoffs",
        json={
            "role": "Lead modeller",
            "scope": "v0.1 structure",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["result"]["role"] == "Lead modeller"


def test_record_session(client: TestClient) -> None:
    resp = client.post(
        "/api/provenance/sessions",
        json={
            "held_at": "2026-04-15",
            "attendees": ["Alice", "Bob"],
            "notes": "Kickoff workshop",
        },
    )
    assert resp.status_code == 201
    assert len(resp.json()["result"]["attendees"]) == 2


def test_add_exclusion(client: TestClient) -> None:
    resp = client.post(
        "/api/provenance/exclusions",
        json={
            "statement": "Indoor air quality excluded",
            "rationale": "Separate regulatory domain",
        },
    )
    assert resp.status_code == 201
    assert "Indoor" in resp.json()["result"]["statement"]


def test_add_prediction(client: TestClient) -> None:
    resp = client.post(
        "/api/provenance/predictions",
        json={
            "statement": "AQI improves 15%",
            "horizon": "3 years",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["result"]["horizon"] == "3 years"
