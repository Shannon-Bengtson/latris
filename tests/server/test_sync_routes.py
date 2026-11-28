"""The /api/sync routes over the fake control plane, fake keyring and local bare remotes
(``tests/sync/fake_control_plane.py``). Each route's happy path, and that failures (expired login,
refused request, offline, a diverged remote) come back as a clean 400 with the reason."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.operations import sync as sync_ops
from latris.operations.nodes import add_node, rename_node
from latris.repo import git
from latris.server.app import create_app
from tests.sync.fake_control_plane import GOOD_CODE, SERVER, SyncWorld


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SyncWorld:
    return SyncWorld.install(tmp_path, monkeypatch)


@pytest.fixture
def client(world: SyncWorld, two_node_project_root: Path) -> TestClient:
    return TestClient(create_app(project_root=two_node_project_root))


def _sign_in(client: TestClient, email: str = "alice@example.org") -> dict:
    r = client.post("/api/sync/login/verify", json={"server_url": SERVER, "email": email, "code": GOOD_CODE,
                                                    "device_name": "laptop", "first_name": "Alice"})
    assert r.status_code == 200, r.text
    return r.json()["account"]


def _share(client: TestClient) -> str:
    r = client.post("/api/sync/share", json={"name": "Coastal"})
    assert r.status_code == 200, r.text
    return r.json()["project"]["id"]


def test_login_verify_and_logout(client: TestClient, world: SyncWorld) -> None:
    r = client.post("/api/sync/login/verify", json={"server_url": SERVER, "email": "a@example.org", "code": "999999"})
    assert r.status_code == 400 and "invalid or expired code" in r.json()["detail"]

    acct = _sign_in(client)
    assert acct["email"] == "alice@example.org"
    assert client.get("/api/sync/account").json()["account"]["email"] == "alice@example.org"

    assert client.post("/api/sync/logout").json() == {"ok": True}
    assert client.get("/api/sync/account").json()["account"] is None
    assert world.keyring.store == {}


def test_validate_after_the_login_expires(client: TestClient, world: SyncWorld) -> None:
    _sign_in(client)
    assert client.post("/api/sync/validate").json()["allowed"] is True
    world.plane.expire_sessions()
    assert client.post("/api/sync/validate").json() == {"state": "revoked", "allowed": False, "account": None}


def test_profile(client: TestClient, world: SyncWorld) -> None:
    r = client.patch("/api/sync/profile", json={"first_name": "Alice"})
    assert r.status_code == 400 and "not connected" in r.json()["detail"]
    _sign_in(client)
    r = client.patch("/api/sync/profile", json={"first_name": "Alice", "last_name": "Ng", "organisation": "Lab"})
    assert r.status_code == 200 and r.json()["account"]["display_name"] == "Alice Ng"
    world.plane.offline = True
    r = client.patch("/api/sync/profile", json={"first_name": "Al"})
    assert r.status_code == 400 and "could not reach" in r.json()["detail"]


def test_projects_and_share(client: TestClient, world: SyncWorld) -> None:
    r = client.post("/api/sync/share", json={"name": "Coastal"})
    assert r.status_code == 400 and "not connected" in r.json()["detail"]
    _sign_in(client)
    assert client.get("/api/sync/projects").json() == {"projects": []}
    pid = _share(client)
    assert [p["id"] for p in client.get("/api/sync/projects").json()["projects"]] == [pid]
    status = client.get("/api/sync/status").json()
    assert status["shared"] and status["project_id"] == pid

    world.plane.fail("/api/me", 503)
    r = client.get("/api/sync/projects")
    assert r.status_code == 400 and "HTTP 503" in r.json()["detail"]


def test_share_refused(client: TestClient, world: SyncWorld) -> None:
    _sign_in(client)
    world.plane.fail("/api/projects$", 403, detail="project limit reached")
    r = client.post("/api/sync/share", json={"name": "Coastal"})
    assert r.status_code == 400 and r.json()["detail"] == "project limit reached"


def test_push_and_pull(client: TestClient, world: SyncWorld, two_node_project_root: Path) -> None:
    _sign_in(client)
    pid = _share(client)
    bob = world.collaborator_clone(pid)
    add_node("Widget", root=bob)
    sync_ops.push(root=bob)

    # The remote moved ahead: push is refused with git's reason, pull brings it in.
    add_node("Gadget", root=two_node_project_root)
    r = client.post("/api/sync/push")
    assert r.status_code == 400
    git.run_git(["reset", "--hard", "HEAD~1"], cwd=two_node_project_root)
    r = client.post("/api/sync/pull")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    add_node("Gadget", root=two_node_project_root)
    r = client.post("/api/sync/push")
    assert r.status_code == 200 and r.json()["head"] == git.head_sha(two_node_project_root)


def test_push_and_pull_signed_out(client: TestClient) -> None:
    for path in ("/api/sync/push", "/api/sync/pull"):
        r = client.post(path)
        assert r.status_code == 400


def _conflict(client: TestClient, world: SyncWorld, root: Path) -> None:
    _sign_in(client)
    pid = _share(client)
    bob = world.collaborator_clone(pid)
    rename_node("Price", "Charge", root=bob)
    sync_ops.push(root=bob)
    rename_node("Price", "Cost", root=root)
    assert client.post("/api/sync/pull").json() == {"status": "conflict"}


def test_diverged_pull_then_resolve(client: TestClient, world: SyncWorld, two_node_project_root: Path) -> None:
    r = client.post("/api/sync/resolve", json={"strategy": "theirs"})
    assert r.status_code == 400 and "no conflict" in r.json()["detail"]
    _conflict(client, world, two_node_project_root)
    assert client.get("/api/sync/status").json()["has_conflict"] is True
    r = client.post("/api/sync/resolve", json={"strategy": "theirs"})
    assert r.status_code == 200 and r.json()["head"] == git.head_sha(two_node_project_root)
    assert not git.has_conflicts(two_node_project_root)


def test_diverged_pull_then_abort(client: TestClient, world: SyncWorld, two_node_project_root: Path) -> None:
    _conflict(client, world, two_node_project_root)
    assert client.post("/api/sync/abort").json() == {"ok": True}
    assert not git.has_conflicts(two_node_project_root)


def test_members(client: TestClient, world: SyncWorld) -> None:
    r = client.post("/api/sync/members", json={"email": "bob@example.org"})
    assert r.status_code == 400 and "not shared yet" in r.json()["detail"]
    _sign_in(client)
    _share(client)
    assert [m["role"] for m in client.get("/api/sync/members").json()["members"]] == ["owner"]

    r = client.post("/api/sync/members", json={"email": "bob@example.org", "role": "collaborator"})
    assert r.status_code == 200, r.text
    bob_id = r.json()["member"]["account_id"]
    assert len(client.get("/api/sync/members").json()["members"]) == 2

    r = client.patch(f"/api/sync/members/{bob_id}", json={"role": "reviewer"})
    assert r.status_code == 200 and r.json()["member"]["role"] == "reviewer"
    roles = {m["actor"]["email"]: m["role"] for m in client.get("/api/sync/members").json()["members"]}
    assert roles["bob@example.org"] == "reviewer"

    r = client.delete("/api/sync/members/acct_nobody")
    assert r.status_code == 400 and r.json()["detail"] == "not a member"
    r = client.delete(f"/api/sync/members/{bob_id}")
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert len(client.get("/api/sync/members").json()["members"]) == 1


def test_members_refused_for_a_collaborator(client: TestClient, world: SyncWorld) -> None:
    _sign_in(client)
    _share(client)
    bob_id = client.post("/api/sync/members", json={"email": "bob@example.org"}).json()["member"]["account_id"]
    _sign_in(client, "bob@example.org")
    r = client.patch(f"/api/sync/members/{bob_id}", json={"role": "owner"})
    assert r.status_code == 400 and "only the owner" in r.json()["detail"]


def test_report_link(client: TestClient, world: SyncWorld) -> None:
    assert client.get("/api/sync/report-link").json() == {"report_url": None, "report_pack": None}
    r = client.post("/api/sync/report-link", json={"enabled": True})
    assert r.status_code == 400 and "not shared yet" in r.json()["detail"]
    _sign_in(client)
    _share(client)
    r = client.post("/api/sync/report-link", json={"enabled": True, "pack": "review"})
    assert r.status_code == 200 and r.json()["report_pack"] == "review"
    url = r.json()["report_url"]
    assert client.get("/api/sync/report-link").json()["report_url"] == url
    world.plane.expire_sessions()
    r = client.get("/api/sync/report-link")
    assert r.status_code == 400 and "session expired" in r.json()["detail"]


def test_clone(client: TestClient, world: SyncWorld, tmp_path: Path) -> None:
    _sign_in(client)
    pid = _share(client)
    dest = tmp_path / "copy"
    r = client.post("/api/sync/clone", json={"project_id": pid, "dest": str(dest)})
    assert r.status_code == 200 and r.json() == {"path": str(dest)}
    assert sync_ops.project_id(root=dest) == pid

    # Cloning onto an existing folder is git's refusal, as a 400.
    r = client.post("/api/sync/clone", json={"project_id": pid, "dest": str(dest)})
    assert r.status_code == 400
    r = client.post("/api/sync/clone", json={"project_id": "proj_missing", "dest": str(tmp_path / "x")})
    assert r.status_code == 400 and "project not found" in r.json()["detail"]
    world.plane.offline = True
    r = client.post("/api/sync/clone", json={"project_id": pid, "dest": str(tmp_path / "y")})
    assert r.status_code == 400 and "could not reach" in r.json()["detail"]
