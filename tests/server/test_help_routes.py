"""Tests for help documentation API endpoints."""

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
    app = create_app(project_root=project)
    return TestClient(app)


# ── List topics ──────────────────────────────────────────────────────


def test_list_topics(client: TestClient) -> None:
    resp = client.get("/api/help/topics")
    assert resp.status_code == 200
    data = resp.json()
    assert "topics" in data
    assert "count" in data
    assert data["count"] == len(data["topics"])
    assert data["count"] >= 2


def test_list_topics_excludes_body(client: TestClient) -> None:
    resp = client.get("/api/help/topics")
    for topic in resp.json()["topics"]:
        assert "body" not in topic


def test_list_topics_has_expected_fields(client: TestClient) -> None:
    resp = client.get("/api/help/topics")
    topic = resp.json()["topics"][0]
    assert "id" in topic
    assert "title" in topic
    assert "category" in topic
    assert "summary" in topic


# ── Get topic ────────────────────────────────────────────────────────


def test_get_topic_welcome(client: TestClient) -> None:
    resp = client.get("/api/help/topics/welcome")
    assert resp.status_code == 200
    data = resp.json()
    assert "topic" in data
    topic = data["topic"]
    assert topic["id"] == "welcome"
    assert topic["title"] == "Welcome to Latris"
    assert topic["category"] == "getting-started"
    assert "body" in topic
    assert len(topic["body"]) > 0


def test_get_topic_not_found(client: TestClient) -> None:
    resp = client.get("/api/help/topics/nonexistent")
    assert resp.status_code == 404
