"""Unit tests for git.revert_head (T14)."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.repo import git


@pytest.fixture
def repo(tmp_path: Path, git_identity) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git.init(root)
    (root / "file.txt").write_text("initial")
    git.add_all(root)
    git.commit(root, "Initial commit")
    return root


def test_revert_head_succeeds(repo: Path) -> None:
    (repo / "file.txt").write_text("changed")
    git.add_all(repo)
    git.commit(repo, "Change content")

    sha = git.revert_head(repo)
    assert len(sha) == 40
    # Content should be back to "initial"
    assert (repo / "file.txt").read_text() == "initial"


def test_revert_head_on_initial_commit_succeeds(repo: Path) -> None:
    """Modern git can revert even the root commit."""
    sha = git.revert_head(repo)
    assert len(sha) == 40
