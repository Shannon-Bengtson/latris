"""The sync broker end to end: login, share, clone, members, authed git — against a fake control
plane, a fake keyring and local bare remotes (``tests/sync/fake_control_plane.py``).

Covers the happy paths and the failures a person meets: an expired login (401), a refused request
(403/404/5xx), being offline, and a remote that has moved ahead or diverged.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import lineage, sync
from latris.operations.init import init_project
from latris.operations.nodes import add_node, list_nodes, rename_node
from latris.repo import git
from latris.repo.layout import ProjectPaths
from latris.sync import credentials
from tests.sync.fake_control_plane import GOOD_CODE, SERVER, SyncWorld


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SyncWorld:
    return SyncWorld.install(tmp_path, monkeypatch)


@pytest.fixture
def shared(world: SyncWorld, two_node_project_root: Path) -> tuple[Path, str]:
    """Alice signed in and shared the two-node project. Returns (root, project id)."""
    world.sign_in("alice@example.org")
    proj = sync.share("Coastal", root=two_node_project_root)
    return two_node_project_root, proj["id"]


def _labels(root: Path) -> set[str]:
    return {n.label for n in list_nodes(root=root)}


def _remote_head(bare: Path, branch: str = "main") -> str:
    return git.run_git(["rev-parse", branch], cwd=bare).stdout.strip()


# -- login / logout / validate -------------------------------------------------


def test_login_stores_credentials_in_the_latris_sync_keyring(world: SyncWorld) -> None:
    acct = world.sign_in("alice@example.org")
    assert acct["email"] == "alice@example.org"
    # Everything lives under the frozen service name, nothing else.
    assert {svc for svc, _ in world.keyring.store} == {"latris-sync"}
    assert {"server_url", "session", "gitea_token", "gitea_username", "account", "last_validated"} <= world.keyring.keys()
    assert credentials.get_server_url() == SERVER
    assert sync.current_account() == acct
    assert ("POST", "/api/auth/request-code") in world.plane.requests


def test_login_with_a_wrong_code_stores_nothing_secret(world: SyncWorld) -> None:
    with pytest.raises(sync.SyncError, match="invalid or expired code"):
        sync.login_verify(SERVER, "alice@example.org", "000000")
    assert not credentials.is_logged_in()
    assert sync.current_account() is None


def test_login_request_offline(world: SyncWorld) -> None:
    world.plane.offline = True
    with pytest.raises(sync.SyncError, match="could not reach the sync server"):
        sync.login_request_code(SERVER, "alice@example.org")


def test_validate_access_against_the_plane(world: SyncWorld) -> None:
    assert sync.validate_access()["state"] == "anon"
    world.sign_in()
    assert sync.validate_access()["state"] == "valid"

    world.plane.offline = True
    res = sync.validate_access()
    assert res["state"] == "offline_ok" and res["account"]["email"] == "alice@example.org"
    world.plane.offline = False

    # A server error isn't a revocation: it is treated like being offline (grace applies).
    world.plane.fail("/api/auth/validate", 503, times=1)
    assert sync.validate_access()["state"] == "offline_ok"
    assert credentials.is_logged_in()

    # An expired login is: the credentials go.
    world.plane.expire_sessions()
    assert sync.validate_access() == {"state": "revoked", "account": None}
    assert world.keyring.store == {}


def test_validate_access_refused_403_revokes(world: SyncWorld) -> None:
    world.sign_in()
    world.plane.fail("/api/auth/validate", 403, detail="account suspended")
    assert sync.validate_access()["state"] == "revoked"
    assert not credentials.is_logged_in()


def test_validate_access_with_a_token_but_no_server_is_anon(world: SyncWorld) -> None:
    world.sign_in()
    world.keyring.delete_password("latris-sync", "server_url")
    assert sync.validate_access()["state"] == "anon"


def test_update_profile_refreshes_the_cached_account(world: SyncWorld) -> None:
    world.sign_in()
    acct = sync.update_profile("Alice", "Ng", "Harbour Lab")
    assert acct["display_name"] == "Alice Ng"
    assert credentials.get_account()["organisation"] == "Harbour Lab"


def test_update_profile_with_expired_login(world: SyncWorld) -> None:
    world.sign_in()
    world.plane.expire_sessions()
    with pytest.raises(sync.SyncError, match="session expired"):
        sync.update_profile("A", None, None)


def test_update_profile_signed_out(world: SyncWorld) -> None:
    with pytest.raises(sync.SyncError, match="not connected"):
        sync.update_profile("A", None, None)


def test_logout_ends_the_session_and_clears_the_keyring(world: SyncWorld) -> None:
    world.sign_in()
    assert len(world.plane.sessions) == 1
    sync.logout()
    assert world.plane.sessions == {}
    assert world.keyring.store == {}


def test_logout_offline_or_signed_out_still_clears(world: SyncWorld) -> None:
    sync.logout()  # signed out: nothing to do, no error
    world.sign_in()
    world.plane.offline = True
    sync.logout()
    assert world.keyring.store == {}


def test_list_remote_projects(shared: tuple[Path, str], world: SyncWorld) -> None:
    _, pid = shared
    assert [p["id"] for p in sync.list_remote_projects()] == [pid]
    world.plane.fail("/api/me", 502)
    with pytest.raises(sync.SyncError, match="HTTP 502"):
        sync.list_remote_projects()


def test_list_remote_projects_signed_out(world: SyncWorld) -> None:
    with pytest.raises(sync.SyncError, match="not connected"):
        sync.list_remote_projects()
    credentials.set_server_url(SERVER)
    with pytest.raises(sync.SyncError, match="not signed in"):
        sync.list_remote_projects()


# -- share / clone ---------------------------------------------------------------


def test_share_wires_the_remote_records_ownership_and_pushes(shared: tuple[Path, str], world: SyncWorld) -> None:
    root, pid = shared
    assert sync.project_id(root=root) == pid
    assert git.get_config(root, sync.SYNC_SERVER_KEY) == SERVER
    assert sync.remote_url(root=root) == str(world.bare(pid))
    members = sync.read_members(root=root)
    assert [(m.role, m.actor.email) for m in members] == [("owner", "alice@example.org")]
    assert members[0].account_id == world.plane.accounts["alice@example.org"]["id"]
    # The ownership commit is what reached the remote.
    assert _remote_head(world.bare(pid)) == git.head_sha(root)
    assert "Shared project" in git.recent_commits(root, 1)[0]["subject"]
    st = sync.sync_status(root=root)
    assert st["shared"] and st["logged_in"] and st["ahead"] == 0 and not st["has_conflict"]


def test_share_refused_or_offline_changes_nothing(world: SyncWorld, two_node_project_root: Path) -> None:
    root = two_node_project_root
    with pytest.raises(sync.SyncError, match="not connected"):
        sync.share("Coastal", root=root)
    world.sign_in()
    world.plane.fail("/api/projects$", 403, detail="project limit reached", times=1)
    with pytest.raises(sync.SyncError, match="project limit reached"):
        sync.share("Coastal", root=root)
    world.plane.offline = True
    with pytest.raises(sync.SyncError, match="could not reach"):
        sync.share("Coastal", root=root)
    assert sync.remote_url(root=root) is None
    assert sync.project_id(root=root) is None
    assert sync.read_members(root=root) == []


def test_share_with_an_expired_login(world: SyncWorld, two_node_project_root: Path) -> None:
    world.sign_in()
    world.plane.expire_sessions()
    with pytest.raises(sync.SyncError, match="session expired"):
        sync.share("Coastal", root=two_node_project_root)


def test_record_project_link_keeps_a_report_url(shared: tuple[Path, str]) -> None:
    root, pid = shared
    sync._record_project_link(ProjectPaths(root), {"id": pid, "report_url": f"{SERVER}/r/x"})
    assert sync.report_url(root=root) == f"{SERVER}/r/x"


def test_clone_project_as_a_member(shared: tuple[Path, str], world: SyncWorld, tmp_path: Path) -> None:
    _, pid = shared
    sync.add_member("bob@example.org", "collaborator", root=shared[0])
    world.sign_in("bob@example.org")
    dest = sync.clone_project(pid, tmp_path / "bob")
    assert _labels(dest) >= {"Price", "Demand"}
    assert sync.project_id(root=dest) == pid
    assert git.get_config(dest, sync.SYNC_SERVER_KEY) == SERVER
    assert git.get_config(dest, "user.email") == "bob@example.org"


def test_clone_project_not_a_member_or_unknown(shared: tuple[Path, str], world: SyncWorld, tmp_path: Path) -> None:
    _, pid = shared
    world.sign_in("eve@example.org")
    with pytest.raises(sync.SyncError, match="project not found"):
        sync.clone_project(pid, tmp_path / "eve")
    with pytest.raises(sync.SyncError, match="project not found"):
        sync.clone_project("proj_missing", tmp_path / "eve")
    assert not (tmp_path / "eve").exists()


def test_clone_project_offline(world: SyncWorld, tmp_path: Path) -> None:
    world.sign_in()
    world.plane.offline = True
    with pytest.raises(sync.SyncError, match="could not reach"):
        sync.clone_project("proj_1", tmp_path / "x")


# -- members ---------------------------------------------------------------------


def test_member_ops_mirror_membership_into_members_yaml(shared: tuple[Path, str], world: SyncWorld) -> None:
    root, _ = shared
    member = sync.add_member("bob@example.org", "collaborator", root=root)
    bob_id = member["account_id"]
    assert {(m.actor.email, m.role) for m in sync.read_members(root=root)} == {
        ("alice@example.org", "owner"),
        ("bob@example.org", "collaborator"),
    }
    assert git.recent_commits(root, 1)[0]["subject"] == "Updated project membership"
    assert not git.has_uncommitted_changes(root)

    assert sync.update_member(bob_id, "reviewer", root=root)["role"] == "reviewer"
    assert ("bob@example.org", "reviewer") in {(m.actor.email, m.role) for m in sync.read_members(root=root)}

    assert sync.remove_member(bob_id, root=root) == {"ok": True}
    assert [m.actor.email for m in sync.read_members(root=root)] == ["alice@example.org"]


def test_mirror_refresh_skips_members_without_email(
    shared: tuple[Path, str], world: SyncWorld
) -> None:
    root, pid = shared
    world.plane.projects[pid]["members"].append(
        {"account_id": "acct_x", "email": None, "display_name": "Pending", "role": "reviewer"}
    )
    sync._refresh_members_mirror(ProjectPaths(root), sync._client(), pid)
    # The invite without an email is skipped; the mirror is committed, nothing left over.
    assert [m.actor.email for m in sync.read_members(root=root)] == ["alice@example.org"]
    assert not git.has_uncommitted_changes(root)


def test_mirror_refresh_failure_keeps_the_old_mirror(shared: tuple[Path, str], world: SyncWorld) -> None:
    root, pid = shared
    world.plane.fail(f"/api/projects/{pid}$", 500, method="GET")
    sync.add_member("bob@example.org", "collaborator", root=root)  # the add itself succeeds
    assert [m.actor.email for m in sync.read_members(root=root)] == ["alice@example.org"]


def test_member_ops_refused(shared: tuple[Path, str], world: SyncWorld) -> None:
    root, _ = shared
    member = sync.add_member("bob@example.org", "collaborator", root=root)
    with pytest.raises(sync.SyncError, match="not a member"):
        sync.remove_member("acct_nobody", root=root)
    # Bob, a collaborator, can't manage members on Alice's project.
    world.sign_in("bob@example.org")
    with pytest.raises(sync.SyncError, match="only the owner"):
        sync.update_member(member["account_id"], "owner", root=root)
    world.plane.expire_sessions()
    with pytest.raises(sync.SyncError, match="session expired"):
        sync.add_member("carol@example.org", root=root)


def test_member_ops_need_a_shared_project(world: SyncWorld, two_node_project_root: Path) -> None:
    world.sign_in()
    with pytest.raises(sync.SyncError, match="not shared yet"):
        sync.add_member("bob@example.org", root=two_node_project_root)


# -- report link -----------------------------------------------------------------


def test_report_link_through_the_plane(shared: tuple[Path, str], world: SyncWorld) -> None:
    root, _ = shared
    on = sync.set_report_link(True, pack="review", root=root)
    assert on["report_url"].startswith(f"{SERVER}/r/") and on["report_pack"] == "review"
    assert sync.get_report_link(root=root)["report_url"] == on["report_url"]
    world.plane.fail("/report$", 403, detail="only the owner can do that")
    with pytest.raises(sync.SyncError, match="only the owner"):
        sync.set_report_link(False, root=root)
    world.plane.offline = True
    with pytest.raises(sync.SyncError, match="could not reach"):
        sync.get_report_link(root=root)
    # Signed out, the last recorded link is the answer.
    world.plane.offline = False
    sync.logout()
    assert sync.get_report_link(root=root) == {"report_url": on["report_url"], "report_pack": None}


# -- authed git: push / pull / fetch / get latest ----------------------------------


def test_authed_pull_gets_a_collaborators_change(shared: tuple[Path, str], world: SyncWorld) -> None:
    root, pid = shared
    bob = world.collaborator_clone(pid)
    add_node("Widget", root=bob)
    sync.push(root=bob)

    res = sync.authed_pull(root=root)
    assert res["status"] == "ok" and res["head"] == git.head_sha(root)
    assert "Widget" in _labels(root)


def test_authed_pull_diverged_reports_conflict_then_abort(shared: tuple[Path, str], world: SyncWorld) -> None:
    root, pid = shared
    bob = world.collaborator_clone(pid)
    rename_node("Price", "Charge", root=bob)
    sync.push(root=bob)
    rename_node("Price", "Cost", root=root)

    assert sync.authed_pull(root=root) == {"status": "conflict"}
    assert sync.sync_status(root=root)["has_conflict"]
    sync.abort_conflict(root=root)
    assert not git.has_conflicts(root)
    assert "Cost" in _labels(root)


def test_authed_push_when_the_remote_moved_ahead_is_rejected(shared: tuple[Path, str], world: SyncWorld) -> None:
    root, pid = shared
    bob = world.collaborator_clone(pid)
    add_node("Widget", root=bob)
    sync.push(root=bob)
    add_node("Gadget", root=root)
    bob_head = _remote_head(world.bare(pid))
    with pytest.raises(git.GitError):
        sync.authed_push(root=root)
    assert _remote_head(world.bare(pid)) == bob_head  # nothing overwritten


def test_authed_push_after_a_clean_pull(shared: tuple[Path, str], world: SyncWorld) -> None:
    root, pid = shared
    bob = world.collaborator_clone(pid)
    add_node("Widget", root=bob)
    sync.push(root=bob)
    assert sync.authed_pull(root=root)["status"] == "ok"
    add_node("Gadget", root=root)
    assert sync.authed_push(root=root) == _remote_head(world.bare(pid))


def test_authed_git_signed_out(shared: tuple[Path, str]) -> None:
    root, _ = shared
    sync.logout()
    for call in (sync.authed_push, sync.authed_pull):
        with pytest.raises(sync.SyncError, match="not signed in"):
            call(root=root)
    with pytest.raises(sync.SyncError, match="not signed in"):
        sync.authed_get_latest("main", root=root)


def test_pull_failure_without_conflict_is_a_git_error(shared: tuple[Path, str], world: SyncWorld) -> None:
    root, pid = shared
    git.remote_set_url(root, "origin", str(world.tmp_path / "gone.git"))  # remote unreachable
    with pytest.raises(git.GitError):
        sync.pull(root=root)


def _unshared(tmp_path: Path) -> Path:
    root = tmp_path / "unshared"
    init_project(root, statement="Q?")
    return root


def test_fetch_needs_a_remote_and_updates_tracking_refs(shared: tuple[Path, str], world: SyncWorld) -> None:
    with pytest.raises(sync.SyncError, match="no 'origin' remote"):
        sync.fetch(root=_unshared(world.tmp_path))
    root, pid = shared
    bob = world.collaborator_clone(pid)
    add_node("Widget", root=bob)
    sync.push(root=bob)
    sync.fetch(root=root)
    assert sync.status(root=root)["behind"] == 1
    assert "Widget" not in _labels(root)  # fetch doesn't merge


def test_get_latest_current_branch(shared: tuple[Path, str], world: SyncWorld) -> None:
    root, pid = shared
    bob = world.collaborator_clone(pid)
    add_node("Widget", root=bob)
    sync.push(root=bob)
    res = sync.authed_get_latest("main", root=root)
    assert res["status"] == "ok" and res["branch"] == "main"
    assert "Widget" in _labels(root)


def test_get_latest_current_branch_conflict(shared: tuple[Path, str], world: SyncWorld) -> None:
    root, pid = shared
    bob = world.collaborator_clone(pid)
    rename_node("Price", "Charge", root=bob)
    sync.push(root=bob)
    rename_node("Price", "Cost", root=root)
    assert sync.authed_get_latest("main", root=root)["status"] == "conflict"
    sync.abort_conflict(root=root)


def test_get_latest_current_branch_unreachable_remote(shared: tuple[Path, str], world: SyncWorld) -> None:
    root, _ = shared
    git.remote_set_url(root, "origin", str(world.tmp_path / "gone.git"))
    with pytest.raises(git.GitError):
        sync.authed_get_latest("main", root=root)


def _alt_published(root: Path) -> tuple[str, str]:
    node, branch = lineage.create_alternative("Alt A", root=root)
    sync.authed_publish_version("Alt A", root=root)
    lineage.switch_version("main", root=root)
    return node.id, branch


def test_get_latest_other_branch_fast_forwards_or_refuses_divergence(
    shared: tuple[Path, str], world: SyncWorld
) -> None:
    root, pid = shared
    _, branch = _alt_published(root)
    bob = world.collaborator_clone(pid)
    git.run_git(["checkout", branch], cwd=bob)
    add_node("Widget", root=bob)
    sync.push(root=bob, branch=branch)

    res = sync.authed_get_latest("Alt A", root=root)
    assert res["status"] == "ok" and res["branch"] == branch
    assert res["head"] == _remote_head(world.bare(pid), branch)
    assert git.current_branch(root) == "main"  # working tree untouched

    # Now both sides move on the alternative: a fast-forward is impossible.
    add_node("Gizmo", root=bob)
    sync.push(root=bob, branch=branch)
    lineage.switch_version("Alt A", root=root)
    add_node("Gadget", root=root)
    lineage.switch_version("main", root=root)
    with pytest.raises(sync.SyncError, match="diverged"):
        sync.authed_get_latest("Alt A", root=root)


def test_get_latest_needs_a_remote(empty_project_root: Path) -> None:
    with pytest.raises(sync.SyncError, match="no 'origin' remote"):
        sync.get_latest("main", root=empty_project_root)


# -- per-version authed wrappers -------------------------------------------------


def test_authed_refresh_sync_paths(shared: tuple[Path, str], world: SyncWorld) -> None:
    # No remote: local states, no fetch.
    assert sync.authed_refresh_sync(root=_unshared(world.tmp_path))["shared"] is False
    root, pid = shared
    bob = world.collaborator_clone(pid)
    git.set_config(bob, sync.SYNC_PROJECT_ID_KEY, pid)
    _, branch = _alt_published(root)

    # Bob has no credentials (signed out): his last-known state, no fetch.
    sync.logout()
    assert all(g["branch"] != branch for g in sync.authed_refresh_sync(root=bob)["ghosts"])
    # Signed in, the refresh fetches and the published alternative shows up as a ghost.
    world.sign_in("bob@example.org")
    ghosts = sync.authed_refresh_sync(root=bob)["ghosts"]
    assert any(g["branch"] == branch and g["name"] == "Alt A" for g in ghosts)

    added = sync.authed_add_to_workspace(branch, root=bob)
    assert added["branch"] == branch and added["version_id"]


def test_ghost_and_add_without_lineage_metadata(
    shared: tuple[Path, str], world: SyncWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, pid = shared
    _, branch = _alt_published(root)
    bob = world.collaborator_clone(pid)
    git.set_config(bob, sync.SYNC_PROJECT_ID_KEY, pid)

    def no_file(*_a, **_k):
        raise git.GitError("no such path")

    monkeypatch.setattr(sync.git, "show_file", no_file)
    ghost = next(g for g in sync.version_sync_states(root=bob)["ghosts"] if g["branch"] == branch)
    assert ghost == {"branch": branch, "version_id": None, "name": branch, "maturity": "proposed", "created_by": None}
    assert sync.add_to_workspace(branch, root=bob) == {"branch": branch, "version_id": None}


def test_authed_reconcile_keep_mine_publishes(shared: tuple[Path, str], world: SyncWorld) -> None:
    root, pid = shared
    bob = world.collaborator_clone(pid)
    add_node("BobNode", root=bob)
    sync.push(root=bob)
    add_node("AliceNode", root=root)
    sync.authed_refresh_sync(root=root)
    result = sync.authed_reconcile("main", "mine", root=root)
    assert "AliceNode" in _labels(root) and "BobNode" not in _labels(root)
    assert _remote_head(world.bare(pid)) == git.head_sha(root)
    assert result["archived_branch"]


def test_login_code_constant_is_what_the_plane_accepts(world: SyncWorld) -> None:
    # Guards the fixture itself: the code it signs in with is the one the plane accepts.
    assert sync.login_verify(SERVER, "x@example.org", GOOD_CODE)["email"] == "x@example.org"
