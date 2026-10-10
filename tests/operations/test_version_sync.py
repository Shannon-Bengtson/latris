"""Per-version sync state — publish/get-latest/ghost/add against a bare remote.

Hermetic: a local bare repo stands in for Gitea; no credentials needed, so the
core (env-threaded) functions are called directly. "Shared" is simulated by
setting the ``latris.projectid`` git config the real share/clone flow writes.
"""

from __future__ import annotations

from pathlib import Path

from latris.operations import lineage, sync
from latris.operations.nodes import add_node, list_nodes
from latris.repo import git


def _bare(tmp_path: Path, name: str = "remote.git") -> Path:
    bare = tmp_path / name
    git.init_bare(bare)
    return bare


def _mark_shared(root: Path) -> None:
    git.set_config(root, sync.SYNC_PROJECT_ID_KEY, "proj_test")


def _state(root: Path) -> dict:
    return sync.version_sync_states(root=root)


def test_unshared_project_is_all_local(two_node_project_root: Path) -> None:
    info = sync.version_sync_states(root=two_node_project_root)
    assert info["shared"] is False
    assert info["ghosts"] == []
    assert info["sync_state"]  # root version present
    assert all(s["state"] == "local_only" for s in info["sync_state"].values())


def test_publish_makes_version_in_sync(two_node_project_root: Path, tmp_path: Path) -> None:
    root = two_node_project_root
    sync.set_remote(str(_bare(tmp_path)), root=root)
    _mark_shared(root)
    # Before publishing, main is local-only.
    before = _state(root)
    assert all(s["state"] == "local_only" for s in before["sync_state"].values())

    result = sync.publish_version("main", root=root)
    assert result["branch"] == "main"

    after = _state(root)
    main_id = next(iter(after["sync_state"]))
    assert after["sync_state"][main_id]["published"] is True
    assert after["sync_state"][main_id]["state"] == "in_sync"


def test_alternative_publish_then_ghost_and_add(two_node_project_root: Path, tmp_path: Path) -> None:
    alice = two_node_project_root
    bare = _bare(tmp_path)
    sync.set_remote(str(bare), root=alice)
    _mark_shared(alice)
    sync.publish_version("main", root=alice)

    # Alice explores an alternative and publishes it.
    node, branch = lineage.create_alternative("Alt A", root=alice)
    assert branch.startswith("lineage/")
    st = _state(alice)
    assert st["sync_state"][node.id]["state"] == "local_only"
    sync.publish_version("Alt A", root=alice)
    assert _state(alice)["sync_state"][node.id]["state"] == "in_sync"

    # Bob clones — the alternative is a ghost (remote-only) for him.
    bob = tmp_path / "bob"
    git.clone(str(bare), bob)
    _mark_shared(bob)
    bob_state = _state(bob)
    ghost_branches = {g["branch"] for g in bob_state["ghosts"]}
    assert branch in ghost_branches
    ghost = next(g for g in bob_state["ghosts"] if g["branch"] == branch)
    assert ghost["name"] == "Alt A"
    assert ghost["version_id"] == node.id

    # Bob adds it to his workspace; it stops being a ghost.
    added = sync.add_to_workspace(branch, root=bob)
    assert added["version_id"] == node.id
    after = _state(bob)
    assert all(g["branch"] != branch for g in after["ghosts"])
    assert after["sync_state"][node.id]["state"] == "in_sync"


def test_updates_available_then_get_latest(two_node_project_root: Path, tmp_path: Path) -> None:
    alice = two_node_project_root
    bare = _bare(tmp_path)
    sync.set_remote(str(bare), root=alice)
    _mark_shared(alice)
    sync.publish_version("main", root=alice)

    bob = tmp_path / "bob"
    git.clone(str(bare), bob)
    _mark_shared(bob)

    # Alice changes main and publishes.
    add_node("Widget", root=alice)
    sync.publish_version("main", root=alice)

    # Bob refreshes (fetch) and sees "updates available" on main.
    refreshed = sync.refresh_sync(root=bob)
    main_id = next(iter(refreshed["sync_state"]))
    assert refreshed["sync_state"][main_id]["state"] == "updates"
    assert refreshed["sync_state"][main_id]["behind"] >= 1

    # Get latest fast-forwards Bob's main.
    result = sync.get_latest("main", root=bob)
    assert result["status"] == "ok"
    assert "Widget" in {n.label for n in list_nodes(root=bob)}
    assert _state(bob)["sync_state"][main_id]["state"] == "in_sync"
