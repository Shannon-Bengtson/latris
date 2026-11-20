"""The routes that put right what the handover check lists: checking a citation against its source,
removing one, saving what was read, approving factors and links, and removing leftover rows."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.operations import build as build_ops
from latris.operations.handover import handover_check
from latris.operations.init import init_project
from latris.server.app import create_app

SPEC = """
factors:
  - label: Workload
  - label: Burnout
links:
  - {from: Workload, to: Burnout, polarity: "+", sources: [smith2024]}
sources:
  - {key: smith2024, title: Burnout among volunteers, url: "https://example.org/smith"}
"""
LINK = "Workload -> Burnout"


@pytest.fixture
def client(tmp_path: Path, git_identity) -> TestClient:
    root = tmp_path / "p"
    init_project(root, statement="Why do volunteers leave?")
    build_ops.build_from_spec(build_ops.load_spec(SPEC), root=root)
    return TestClient(create_app(project_root=root))


def _kinds(client: TestClient) -> dict[str, dict]:
    return {i["kind"]: i for i in client.get("/api/checks/handover").json()["items"]}


def test_handover_names_the_sources(client: TestClient) -> None:
    assert _kinds(client)["unchecked_citations"]["bibkeys"] == ["smith2024"]
    assert _kinds(client)["unread_sources"]["bibkeys"] == ["smith2024"]


def test_save_what_was_read_then_check_the_citation(client: TestClient) -> None:
    passage = "Volunteers with heavier rosters reported more burnout in the follow-up survey."
    r = client.post("/api/references/smith2024/snapshot",
                    json={"url": "https://example.org/smith", "extract": passage, "kind": "abstract"})
    assert r.status_code == 200, r.text
    assert "unread_sources" not in _kinds(client)

    r = client.post("/api/evidence/check", json={
        "target": LINK, "attribute": "polarity", "bibkey": "smith2024", "verdict": "supports",
        "rationale": "Heavier rosters went with more burnout.", "quote": passage[:60],
    })
    assert r.status_code == 200, r.text
    assert r.json()["result"]["support_verdict"] == "supports"
    assert "unchecked_citations" not in _kinds(client)


def test_remove_a_citation(client: TestClient) -> None:
    r = client.post("/api/evidence/remove", json={"target": LINK, "attribute": "polarity", "bibkey": "smith2024",
                                                  "rationale": "Wrong study"})
    assert r.status_code == 200, r.text
    assert "unsourced_links" in _kinds(client)


def test_review_and_approve_a_factor(client: TestClient) -> None:
    r = client.post("/api/maturity", json={"target": "Workload", "level": "reviewed"})
    assert r.status_code == 200 and r.json()["result"] == "reviewed"
    r = client.post("/api/maturity", json={"target": "Workload", "level": "approved", "role": "Programme lead"})
    assert r.status_code == 200 and r.json()["result"] == "approved"
    signoffs = client.get("/api/state").json()["provenance"]["signoffs"]["entries"]
    assert signoffs[-1]["role"] == "Programme lead"


def test_fix_removes_leftover_rows(client: TestClient, tmp_path: Path) -> None:
    from latris.repo.layout import ProjectPaths
    from latris.repo.yaml_io import dump_raw, load_raw

    paths = ProjectPaths(tmp_path / "p")
    data = load_raw(paths.descriptions_yaml)
    data.setdefault("entries", []).append({"target_id": "node_01GHOST0000000000000000000", "attribute": "description",
                                           "value": "left behind"})
    dump_raw(data, paths.descriptions_yaml)
    assert "integrity" in {i.kind for i in handover_check(root=paths.root).items}
    r = client.post("/api/checks/integrity/fix").json()
    assert r["removed"] >= 1 and r["commit_sha"] and r["remaining"] == []


def test_refreshing_sync_state_of_an_unshared_project_is_quiet(client: TestClient, monkeypatch) -> None:
    """The app refreshes sync state on load; a project with no remote (or signed out) isn't an error."""
    from latris.sync import credentials

    monkeypatch.setattr(credentials, "get_gitea_token", lambda: None)
    r = client.post("/api/lineage/sync/refresh")
    assert r.status_code == 200, r.text
