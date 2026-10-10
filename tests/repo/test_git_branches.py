"""Tests for branch-related git operations used by the lineage system."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.repo import git


@pytest.fixture
def repo(tmp_path: Path, git_identity: tuple[str, str]) -> Path:
    """An initialised git repo with one commit on main."""
    r = tmp_path / "r"
    r.mkdir()
    git.init(r)
    (r / "hello.txt").write_text("hi\n", encoding="utf-8", newline="")
    git.add_all(r)
    git.commit(r, "Initial commit")
    return r


def test_current_branch_returns_main(repo: Path) -> None:
    assert git.current_branch(repo) == "main"


def test_create_and_list_branches(repo: Path) -> None:
    git.create_branch(repo, "lineage/AAAAA")
    git.create_branch(repo, "lineage/BBBBB")
    git.create_branch(repo, "feature/unrelated")

    lineage = git.list_branches(repo, pattern="lineage/*")
    assert sorted(lineage) == ["lineage/AAAAA", "lineage/BBBBB"]

    all_branches = git.list_branches(repo)
    assert "main" in all_branches
    assert "feature/unrelated" in all_branches


def test_checkout_switches_branch(repo: Path) -> None:
    git.create_branch(repo, "lineage/TEST")
    git.checkout(repo, "lineage/TEST")
    assert git.current_branch(repo) == "lineage/TEST"

    git.checkout(repo, "main")
    assert git.current_branch(repo) == "main"


def test_create_branch_from_specific_commit(repo: Path) -> None:
    first_sha = git.head_sha(repo)

    (repo / "second.txt").write_text("2\n", encoding="utf-8", newline="")
    git.add_all(repo)
    git.commit(repo, "Second commit")

    # Branch from the first commit, not HEAD
    git.create_branch(repo, "lineage/FROM_FIRST", start=first_sha)
    git.checkout(repo, "lineage/FROM_FIRST")

    # second.txt should not exist on this branch
    assert not (repo / "second.txt").exists()
    assert git.head_sha(repo) == first_sha


def test_show_file_reads_from_other_branch(repo: Path) -> None:
    # Write a file on main
    (repo / "data.yaml").write_text("key: main\n", encoding="utf-8", newline="")
    git.add_all(repo)
    git.commit(repo, "Add data on main")

    # Create branch and modify the file
    git.create_branch(repo, "lineage/ALT")
    git.checkout(repo, "lineage/ALT")
    (repo / "data.yaml").write_text("key: alt\n", encoding="utf-8", newline="")
    git.add_all(repo)
    git.commit(repo, "Modify data on alt")

    # Read from main without checkout
    content = git.show_file(repo, "main", "data.yaml")
    assert "key: main" in content

    # Read from current branch
    content_alt = git.show_file(repo, "lineage/ALT", "data.yaml")
    assert "key: alt" in content_alt


def test_show_file_raises_for_missing(repo: Path) -> None:
    with pytest.raises(git.GitError):
        git.show_file(repo, "main", "nonexistent.yaml")


def test_show_file_normalises_backslashes(repo: Path) -> None:
    """Windows paths with backslashes should work."""
    (repo / "sub").mkdir()
    (repo / "sub" / "file.txt").write_text("ok\n", encoding="utf-8", newline="")
    git.add_all(repo)
    git.commit(repo, "Add nested file")

    # Use backslash path — should be normalised internally
    content = git.show_file(repo, "main", "sub\\file.txt")
    assert "ok" in content


def test_has_uncommitted_changes_clean(repo: Path) -> None:
    assert git.has_uncommitted_changes(repo) is False


def test_has_uncommitted_changes_dirty(repo: Path) -> None:
    (repo / "hello.txt").write_text("changed\n", encoding="utf-8", newline="")
    assert git.has_uncommitted_changes(repo) is True


def test_has_uncommitted_changes_staged(repo: Path) -> None:
    (repo / "new.txt").write_text("staged\n", encoding="utf-8", newline="")
    git.add(repo, [repo / "new.txt"])
    assert git.has_uncommitted_changes(repo) is True
