"""Tests for export endpoints (T7)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.operations import nodes as node_ops
from latris.operations.init import init_project
from latris.server.app import create_app


@pytest.fixture
def project(tmp_path: Path, git_identity) -> Path:
    root = tmp_path / "demo"
    init_project(root, statement="What drives air quality?")
    node_ops.add_node("Price", kind="variable", root=root)
    node_ops.add_node("Demand", kind="variable", root=root)
    return root


@pytest.fixture
def client(project: Path) -> TestClient:
    return TestClient(create_app(project_root=project))


def test_export_markdown_returns_text(client: TestClient) -> None:
    resp = client.get("/api/export/markdown")
    assert resp.status_code == 200
    assert "text/markdown" in resp.headers["content-type"]
    assert "Price" in resp.text


def test_export_markdown_with_pack(client: TestClient) -> None:
    resp = client.get("/api/export/markdown?pack=client")
    assert resp.status_code == 200
    assert len(resp.text) > 0


def test_export_dot_contains_digraph(client: TestClient) -> None:
    resp = client.get("/api/export/dot")
    assert resp.status_code == 200
    assert "digraph" in resp.text


def test_export_word_returns_docx(client: TestClient) -> None:
    resp = client.get("/api/export/word")
    assert resp.status_code == 200
    assert "attachment" in resp.headers.get("content-disposition", "")
    assert len(resp.content) > 100  # non-trivial file
