"""The lineage index reads each branch's lineage node; one it can't read is skipped, not fatal."""

from __future__ import annotations

from latris.repo import git, lineage_index


def test_an_unreadable_lineage_node_is_skipped(tmp_path, git_identity, monkeypatch):
    monkeypatch.setattr(git, "show_file", lambda root, branch, path: "id: [unclosed")
    assert lineage_index._load_node_at_branch(tmp_path, "main") is None
    monkeypatch.setattr(git, "show_file", lambda root, branch, path: "just: a mapping\n")
    assert lineage_index._load_node_at_branch(tmp_path, "main") is None  # not a lineage node

    def missing(root, branch, path):
        raise git.GitError("no such path")

    monkeypatch.setattr(git, "show_file", missing)
    assert lineage_index._load_node_at_branch(tmp_path, "main") is None
