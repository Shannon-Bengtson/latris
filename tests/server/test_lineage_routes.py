"""Tests for lineage API endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.operations.init import init_project
from latris.repo import git
from latris.server.app import create_app


@pytest.fixture
def project(tmp_path: Path, git_identity) -> Path:
    root = tmp_path / "demo"
    init_project(root, statement="Test Q?")
    return root


@pytest.fixture
def client(project: Path) -> TestClient:
    app = create_app(project_root=project)
    return TestClient(app)


# -- GET /api/lineage/tree --


def test_get_tree_fresh_project(client: TestClient) -> None:
    resp = client.get("/api/lineage/tree")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["nodes"]) == 1
    assert data["nodes"][0]["relationship"] == "original"
    assert data["current_branch"] == "main"


# -- GET /api/lineage/current --


def test_get_current_version(client: TestClient) -> None:
    resp = client.get("/api/lineage/current")
    assert resp.status_code == 200
    data = resp.json()
    assert data["relationship"] == "original"
    assert data["id"].startswith("version_")


# -- POST /api/lineage/milestone --


def test_create_milestone(client: TestClient) -> None:
    resp = client.post("/api/lineage/milestone", json={"name": "Draft 1"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["result"]["name"] == "Draft 1"
    assert data["result"]["maturity"] == "proposed"
    assert len(data["commit_sha"]) == 40


def test_create_approved_milestone(client: TestClient) -> None:
    resp = client.post(
        "/api/lineage/milestone",
        json={"name": "v1", "maturity": "approved"},
    )
    assert resp.status_code == 201
    assert resp.json()["result"]["maturity"] == "approved"


# -- POST /api/lineage/alternative --


def test_create_alternative(client: TestClient, project: Path) -> None:
    resp = client.post(
        "/api/lineage/alternative",
        json={"name": "What-if scenario"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["result"]["relationship"] == "alternative"
    assert data["branch"].startswith("lineage/")
    # Server should now be on the new branch.
    assert git.current_branch(project) == data["branch"]


# -- POST /api/lineage/switch --


def test_switch_version(client: TestClient, project: Path) -> None:
    # Create an alternative.
    alt = client.post("/api/lineage/alternative", json={"name": "Alt"})
    assert alt.status_code == 201
    assert git.current_branch(project) != "main"

    # Switch back to main.
    resp = client.post("/api/lineage/switch", json={"version_query": "main"})
    assert resp.status_code == 200
    assert git.current_branch(project) == "main"


# -- PATCH /api/lineage/version --


def test_update_version(client: TestClient) -> None:
    # Ensure lineage exists first.
    client.get("/api/lineage/current")

    resp = client.patch(
        "/api/lineage/version",
        json={"name": "Renamed", "maturity": "approved"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["result"]["name"] == "Renamed"
    assert data["result"]["maturity"] == "approved"


# -- Undo boundary --


def test_undo_blocked_at_branch_root(client: TestClient, project: Path) -> None:
    # Create an alternative (this is the branch root commit).
    client.post("/api/lineage/alternative", json={"name": "Alt"})

    # Undo should be blocked — HEAD is the branch creation commit.
    resp = client.post("/api/history/undo")
    assert resp.status_code == 409
    assert "Nothing more to undo" in resp.json()["detail"]


def test_undo_works_after_mutation_on_alternative(
    client: TestClient,
    project: Path,
) -> None:
    client.post("/api/lineage/alternative", json={"name": "Alt"})

    # Add a node — this creates a commit we CAN undo.
    client.post("/api/nodes", json={"label": "Price", "kind": "variable"})

    resp = client.post("/api/history/undo")
    assert resp.status_code == 200


# -- GET /api/lineage/tree includes milestones --


def test_set_preferred(client: TestClient) -> None:
    # Create an alternative.
    alt = client.post("/api/lineage/alternative", json={"name": "Alt"})
    alt_id = alt.json()["result"]["id"]

    # Set the alternative as preferred.
    resp = client.post("/api/lineage/preferred", json={"version_query": alt_id})
    assert resp.status_code == 200
    assert resp.json()["version_id"] == alt_id

    # Verify the tree shows it as preferred.
    tree = client.get("/api/lineage/tree").json()
    assert tree["preferred_version_id"] == alt_id


def test_preferred_defaults_to_original(client: TestClient) -> None:
    tree = client.get("/api/lineage/tree").json()
    # The original version should be implicitly preferred.
    assert tree["preferred_version_id"] is not None
    original = [n for n in tree["nodes"] if n["relationship"] == "original"]
    assert tree["preferred_version_id"] == original[0]["id"]


def test_tree_includes_milestones(client: TestClient) -> None:
    client.post("/api/lineage/milestone", json={"name": "M1"})
    client.post("/api/lineage/milestone", json={"name": "M2"})

    resp = client.get("/api/lineage/tree")
    data = resp.json()

    # Milestones should be keyed by the current version ID.
    assert len(data["milestones"]) == 1  # one version, one key
    milestones = list(data["milestones"].values())[0]
    assert len(milestones) == 2
    names = [m["name"] for m in milestones]
    assert "M1" in names
    assert "M2" in names


# -- POST /api/lineage/restore --


def test_restore_from_milestone(client: TestClient, project: Path) -> None:
    from latris.operations import lineage
    from latris.operations.nodes import add_node, list_nodes

    add_node("Kept", root=project)
    assert client.post("/api/lineage/milestone", json={"name": "M1"}).status_code == 201
    add_node("Later", root=project)

    resp = client.post("/api/lineage/restore", json={"milestone_query": "M1", "name": "Back to M1",
                                                     "notes": "try again"})
    assert resp.status_code == 201
    body = resp.json()
    assert (body["result"]["name"], body["result"]["notes"]) == ("Back to M1", "try again")
    assert body["branch"].startswith("lineage/") and git.current_branch(project) == body["branch"]
    # The working tree is the milestone's state, on a new version.
    assert {n.label for n in list_nodes(root=project)} == {"Kept"}
    assert lineage.ensure_root_lineage(project).id == body["result"]["id"]


def test_restore_unknown_milestone(client: TestClient, project: Path) -> None:
    head, branch = git.head_sha(project), git.current_branch(project)
    resp = client.post("/api/lineage/restore", json={"milestone_query": "nope", "name": "R"})
    assert resp.status_code == 404
    client.post("/api/lineage/milestone", json={"name": "M1"})
    resp = client.post("/api/lineage/restore", json={"milestone_query": "nope", "name": "R"})
    assert resp.status_code == 404
    assert git.current_branch(project) == branch
    assert client.post("/api/lineage/restore", json={"name": "R"}).status_code == 422
    assert head != git.head_sha(project)  # only the milestone was committed


# -- Per-version sync (a local bare repo stands in for the shared remote) --


def _shared(root: Path, tmp_path: Path) -> Path:
    from latris.operations import sync

    bare = tmp_path / "remote.git"
    git.init_bare(bare)
    sync.set_remote(str(bare), root=root)
    git.set_config(root, sync.SYNC_PROJECT_ID_KEY, "proj_test")
    return bare


@pytest.fixture
def signed_in(monkeypatch: pytest.MonkeyPatch) -> None:
    """Credentials for the remote: a local bare repo needs none, so the git environment as it is."""
    import os

    from latris.operations import sync

    monkeypatch.setattr(sync, "_authed_env", lambda: os.environ.copy())


@pytest.mark.parametrize(("route", "body"), [
    ("/api/lineage/publish", {"version_query": "main"}),
    ("/api/lineage/get-latest", {"version_query": "main"}),
    ("/api/lineage/add-to-workspace", {"branch": "lineage/x"}),
    ("/api/lineage/reconcile", {"version_query": "main", "keep": "mine"}),
])
def test_sync_routes_signed_out(client: TestClient, project: Path, tmp_path: Path, route: str, body: dict) -> None:
    _shared(project, tmp_path)
    head = git.head_sha(project)
    resp = client.post(route, json=body)
    assert resp.status_code == 400 and "not signed in" in resp.json()["detail"]
    assert git.head_sha(project) == head


def test_publish(client: TestClient, project: Path, tmp_path: Path, signed_in: None) -> None:
    bare = _shared(project, tmp_path)
    resp = client.post("/api/lineage/publish", json={"version_query": "main"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["branch"] == "main" and body["head"] == git.head_sha(project)
    assert git.resolve_commit(bare, "main") == git.head_sha(project)
    tree = client.get("/api/lineage/tree").json()
    assert body["version_id"] == next(n["id"] for n in tree["nodes"] if n["relationship"] == "original")


def test_publish_errors(client: TestClient, project: Path, tmp_path: Path, signed_in: None) -> None:
    no_remote = client.post("/api/lineage/publish", json={"version_query": "main"})
    assert no_remote.status_code == 400 and "no 'origin' remote" in no_remote.json()["detail"]
    _shared(project, tmp_path)
    assert client.post("/api/lineage/publish", json={"version_query": "nope"}).status_code == 404
    assert client.post("/api/lineage/publish", json={}).status_code == 422


def test_get_latest_and_add_to_workspace(two_node_project_root: Path, tmp_path: Path, signed_in: None) -> None:
    from latris.operations import lineage, sync
    from latris.operations.nodes import add_node, list_nodes

    alice = two_node_project_root
    bare = _shared(alice, tmp_path)
    sync.publish_version("main", root=alice)
    bob = tmp_path / "bob"
    git.clone(str(bare), bob)
    git.set_config(bob, sync.SYNC_PROJECT_ID_KEY, "proj_test")

    # Alice moves main on and publishes an alternative.
    add_node("AliceNode", root=alice)
    sync.publish_version("main", root=alice)
    node, branch = lineage.create_alternative("Alt A", root=alice)
    sync.publish_version("Alt A", root=alice)

    bob_client = TestClient(create_app(project_root=bob))
    resp = bob_client.post("/api/lineage/get-latest", json={"version_query": "main"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok" and resp.json()["head"] == git.head_sha(bob)
    assert "AliceNode" in {n.label for n in list_nodes(root=bob)}

    resp = bob_client.post("/api/lineage/add-to-workspace", json={"branch": branch})
    assert resp.status_code == 200 and resp.json() == {"branch": branch, "version_id": node.id}
    assert branch in git.list_branches(bob) and git.current_branch(bob) == "main"  # no checkout
    # Idempotent.
    assert bob_client.post("/api/lineage/add-to-workspace", json={"branch": branch}).status_code == 200

    missing = bob_client.post("/api/lineage/add-to-workspace", json={"branch": "lineage/nope"})
    assert missing.status_code == 400
    assert bob_client.post("/api/lineage/get-latest", json={"version_query": "nope"}).status_code == 404


def test_reconcile_preview_and_reconcile(two_node_project_root: Path, tmp_path: Path, signed_in: None) -> None:
    from latris.operations.nodes import list_nodes
    from tests.operations.test_reconcile import _diverge

    bob, _ = _diverge(two_node_project_root, tmp_path)
    c = TestClient(create_app(project_root=bob))

    preview = c.post("/api/lineage/reconcile/preview", json={"version_query": "main"})
    assert preview.status_code == 200
    assert any("AliceNode" in (e.get("summary") or "") for e in preview.json())

    bad = c.post("/api/lineage/reconcile", json={"version_query": "main", "keep": "sideways"})
    assert bad.status_code == 422 and "keep must be" in bad.json()["detail"]
    assert c.post("/api/lineage/reconcile/preview", json={"version_query": "nope"}).status_code == 404

    resp = c.post("/api/lineage/reconcile", json={"version_query": "main", "keep": "theirs"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["archived_branch"] in git.list_branches(bob)
    labels = {n.label for n in list_nodes(root=bob)}
    assert "AliceNode" in labels and "BobNode" not in labels


def test_reconcile_preview_unshared(client: TestClient) -> None:
    resp = client.post("/api/lineage/reconcile/preview", json={"version_query": "main"})
    assert resp.status_code == 400
