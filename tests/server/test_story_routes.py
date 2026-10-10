"""Tests for the Story (Communicate phase) API routes.

Mirrors the operation-level tests in ``tests/operations/test_story.py`` but
drives the FastAPI surface via ``TestClient`` — draft, prose (AI + human),
emphasis, reorder, GET, and the HTML export download.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.ai import proposals as p
from latris.ai.adapters.base import ChatResult
from latris.ai.adapters.mock_adapter import MockAdapter
from latris.operations.commit import auto_commit
from latris.operations.edges import add_edge
from latris.operations.findings import record_new_finding
from latris.operations.init import init_project
from latris.operations.nodes import add_node
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import dump_model, load_model
from latris.schema.project import ProjectFoundation
from latris.server.app import create_app


@pytest.fixture
def story_root(tmp_path: Path, git_identity, monkeypatch) -> tuple[Path, object, object, object, object, object]:
    """A CLD project with a reinforcing loop + finding, ready to narrate."""
    monkeypatch.setenv("LATRIS_AI_MOCK", "1")
    MockAdapter.shared().register_default(
        response_cls=p.InterpretProseResult,
        result=ChatResult(
            parsed=p.InterpretProseResult(prose="(mock) Plain-language beat prose."),
            raw="(mock)",
            model_id="mock-model",
        ),
    )
    root = tmp_path / "proj"
    init_project(root, statement="What drives water quality decline?")
    paths = ProjectPaths(root)
    foundation = load_model(ProjectFoundation, paths.project_yaml)
    foundation.selected_model_types = ["cld"]
    foundation.name = "Coastal water quality"
    dump_model(foundation, paths.project_yaml)
    auto_commit(root, subject="Select CLD", paths=[paths.project_yaml])

    a, _ = add_node("Nutrient load", kind="variable", root=root)
    b, _ = add_node("Algal bloom", kind="variable", root=root)
    e1, _ = add_edge(a.id, b.id, kind="causal", root=root)
    e2, _ = add_edge(b.id, a.id, kind="causal", root=root)  # closes the loop
    finding, _ = record_new_finding(
        "Reinforcing loop: Nutrient load to Algal bloom and back",
        category="structure",
        model_type="cld",
        payload={"node_ids": [a.id, b.id], "edge_ids": [e1.id, e2.id], "classification": "R"},
        root=root,
    )
    return root, a, b, e1, e2, finding


@pytest.fixture
def client(story_root) -> TestClient:
    root = story_root[0]
    return TestClient(create_app(project_root=root))


def _draft(client: TestClient) -> dict:
    resp = client.post("/api/story/draft", json={"model_type": "cld"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["commit_sha"]) == 40
    return body["result"]


def test_get_story_null_before_draft(client: TestClient) -> None:
    resp = client.get("/api/story", params={"model_type": "cld"})
    assert resp.status_code == 200
    assert resp.json()["result"] is None


def test_draft_builds_beat_skeleton(client: TestClient) -> None:
    doc = _draft(client)
    kinds = [b["kind"] for b in doc["beats"]]
    assert kinds == ["hook", "system_tour", "answer", "uncertainty", "implication", "closing"]
    assert doc["generation_state"] == "drafted"
    assert doc["title"] == "Coastal water quality"


def test_get_story_after_draft(client: TestClient) -> None:
    _draft(client)
    resp = client.get("/api/story", params={"model_type": "cld"})
    assert resp.status_code == 200
    assert resp.json()["result"]["model_type"] == "cld"


def test_generate_prose_route(client: TestClient) -> None:
    doc = _draft(client)
    answer = next(b for b in doc["beats"] if b["kind"] == "answer")
    resp = client.post(f"/api/story/cld/beats/{answer['id']}/generate-prose")
    assert resp.status_code == 200, resp.text
    beat = resp.json()["result"]
    assert beat["prose"] == "(mock) Plain-language beat prose."
    assert beat["prose_versions"][-1]["source"] == "ai"


def test_set_prose_route(client: TestClient) -> None:
    doc = _draft(client)
    hook = next(b for b in doc["beats"] if b["kind"] == "hook")
    resp = client.patch(
        f"/api/story/cld/beats/{hook['id']}/prose",
        json={"prose": "A human-written hook."},
    )
    assert resp.status_code == 200, resp.text
    beat = resp.json()["result"]
    assert beat["prose"] == "A human-written hook."
    assert beat["prose_versions"][-1]["source"] == "human-edit"


def test_set_emphasis_route_expands_loops(client: TestClient, story_root) -> None:
    _root, a, b, e1, e2, finding = story_root
    doc = _draft(client)
    answer = next(beat for beat in doc["beats"] if beat["kind"] == "answer")
    resp = client.put(
        f"/api/story/cld/beats/{answer['id']}/emphasis",
        json={"loop_ids": [finding.id]},
    )
    assert resp.status_code == 200, resp.text
    emphasis = resp.json()["result"]["emphasis"]
    assert set(emphasis["node_ids"]) == {a.id, b.id}
    assert set(emphasis["edge_ids"]) == {e1.id, e2.id}
    assert emphasis["loop_ids"] == [finding.id]


def test_reorder_route(client: TestClient) -> None:
    doc = _draft(client)
    reversed_ids = [b["id"] for b in reversed(doc["beats"])]
    resp = client.post("/api/story/cld/reorder", json={"ordered_beat_ids": reversed_ids})
    assert resp.status_code == 200, resp.text
    assert [b["id"] for b in resp.json()["result"]["beats"]] == reversed_ids


def test_export_route_streams_html(client: TestClient) -> None:
    _draft(client)
    resp = client.get("/api/story/export", params={"model_type": "cld"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert 'filename="story-cld.html"' in resp.headers["content-disposition"]
    assert resp.text.startswith("<!DOCTYPE html>")
    assert "Coastal water quality" in resp.text
