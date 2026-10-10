"""Conflict resolution on the hot file (substrate/conceptual.yaml) via a bare remote."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import sync
from latris.operations.nodes import list_nodes, rename_node
from latris.repo import git


def _diverged(two_node_project_root: Path, tmp_path: Path) -> Path:
    """Alice renames Price->Cost and pushes; Bob renames Price->Charge locally. Returns Bob's root."""
    bare = tmp_path / "remote.git"
    git.init_bare(bare)
    sync.set_remote(str(bare), root=two_node_project_root)
    sync.push(root=two_node_project_root)

    bob = tmp_path / "bob"
    git.clone(str(bare), bob)

    rename_node("Price", "Cost", root=two_node_project_root)
    sync.push(root=two_node_project_root)
    rename_node("Price", "Charge", root=bob)
    return bob


def test_resolve_conflict_theirs(two_node_project_root: Path, tmp_path: Path) -> None:
    bob = _diverged(two_node_project_root, tmp_path)
    with pytest.raises(sync.SyncError):
        sync.pull(root=bob)
    assert git.has_conflicts(bob)

    sync.resolve_conflict("theirs", root=bob)
    assert not git.has_conflicts(bob)
    labels = {n.label for n in list_nodes(root=bob)}
    assert "Cost" in labels and "Charge" not in labels


def test_resolve_conflict_ours(two_node_project_root: Path, tmp_path: Path) -> None:
    bob = _diverged(two_node_project_root, tmp_path)
    with pytest.raises(sync.SyncError):
        sync.pull(root=bob)

    sync.resolve_conflict("ours", root=bob)
    assert not git.has_conflicts(bob)
    labels = {n.label for n in list_nodes(root=bob)}
    assert "Charge" in labels and "Cost" not in labels


def test_resolve_without_conflict_errors(two_node_project_root: Path) -> None:
    with pytest.raises(sync.SyncError):
        sync.resolve_conflict("ours", root=two_node_project_root)
