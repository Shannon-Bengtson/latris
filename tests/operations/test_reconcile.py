"""Reconcile a diverged version — keep one line, archive the other, lose nothing.

Hermetic: a local bare repo stands in for the shared remote. Divergence is
created by two clones editing and publishing the same version without pulling.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import lineage, sync
from latris.operations.nodes import add_node, list_nodes
from latris.repo import git


def _bare(tmp_path: Path) -> Path:
    bare = tmp_path / "remote.git"
    git.init_bare(bare)
    return bare


def _diverge(alice: Path, tmp_path: Path) -> tuple[Path, str]:
    """Return (bob_root, bob_pre_reconcile_sha) with main diverged on Bob."""
    bare = _bare(tmp_path)
    sync.set_remote(str(bare), root=alice)
    git.set_config(alice, sync.SYNC_PROJECT_ID_KEY, "proj_test")
    sync.publish_version("main", root=alice)

    bob = tmp_path / "bob"
    git.clone(str(bare), bob)
    git.set_config(bob, sync.SYNC_PROJECT_ID_KEY, "proj_test")

    # Alice changes main and publishes; Bob changes main without pulling.
    add_node("AliceNode", root=alice)
    sync.publish_version("main", root=alice)
    add_node("BobNode", root=bob)
    bob_sha = git.head_sha(bob)

    refreshed = sync.refresh_sync(root=bob)
    main_id = next(iter(refreshed["sync_state"]))
    assert refreshed["sync_state"][main_id]["state"] == "diverged"
    return bob, bob_sha


def _labels(root: Path) -> set[str]:
    return {n.label for n in list_nodes(root=root)}


def test_reconcile_preview_lists_their_changes(two_node_project_root: Path, tmp_path: Path) -> None:
    bob, _ = _diverge(two_node_project_root, tmp_path)
    events = lineage.reconcile_preview("main", root=bob)
    # The shared side added AliceNode relative to Bob's line.
    assert any("AliceNode" in (e.get("summary") or "") for e in events)


def test_reconcile_keep_mine_publishes_my_line_and_archives_theirs(
    two_node_project_root: Path, tmp_path: Path
) -> None:
    bob, _ = _diverge(two_node_project_root, tmp_path)
    result = lineage.reconcile("main", "mine", root=bob)

    # Bob's line wins: his node stays, theirs is not applied to main.
    assert "BobNode" in _labels(bob)
    assert "AliceNode" not in _labels(bob)

    # The losing (shared) line is retained as an archived version — nothing deleted.
    full = lineage.get_lineage_tree(bob, include_archived=True)
    archived = [n for n in full["nodes"] if n.get("archived")]
    assert len(archived) == 1
    assert archived[0]["superseded_by"] == result["version_id"]
    # ...and it still contains AliceNode.
    git.checkout(bob, result["archived_branch"])
    assert "AliceNode" in _labels(bob)
    git.checkout(bob, "main")

    # Archived versions are hidden by default.
    assert all(not n.get("archived") for n in lineage.get_lineage_tree(bob)["nodes"])
    # Main is now in sync (the publish fast-forwarded the remote).
    assert sync.version_sync_states(root=bob)["sync_state"][result["version_id"]]["state"] == "in_sync"


def test_reconcile_keep_theirs_adopts_shared_and_preserves_my_line(
    two_node_project_root: Path, tmp_path: Path
) -> None:
    bob, bob_sha = _diverge(two_node_project_root, tmp_path)
    result = lineage.reconcile("main", "theirs", root=bob)

    # The shared line wins on main.
    assert "AliceNode" in _labels(bob)
    assert "BobNode" not in _labels(bob)

    # Nothing deleted: Bob's pre-reconcile commit still resolves...
    assert git.run_git(["rev-parse", "--verify", bob_sha], cwd=bob, check=False).returncode == 0
    # ...and his line survives on the archived branch.
    git.checkout(bob, result["archived_branch"])
    assert "BobNode" in _labels(bob)
    git.checkout(bob, "main")


def test_reconcile_rejects_bad_keep(two_node_project_root: Path, tmp_path: Path) -> None:
    bob, _ = _diverge(two_node_project_root, tmp_path)
    with pytest.raises(ValueError):
        lineage.reconcile("main", "sideways", root=bob)
