from __future__ import annotations

from pathlib import Path

from latris.operations.project import load_foundation, set_question
from latris.repo import git
from latris.repo.project import find_project_root


def test_find_project_root_walks_up(empty_project_root: Path) -> None:
    nested = empty_project_root / "research-base"
    found = find_project_root(nested)
    assert found == empty_project_root


def test_find_project_root_returns_none_outside(tmp_path: Path) -> None:
    assert find_project_root(tmp_path) is None


def test_set_question_updates_yaml_and_commits(empty_project_root: Path) -> None:
    first_sha = git.head_sha(empty_project_root)

    returned_root, new_sha = set_question(empty_project_root, "Will X cause Y?")
    assert returned_root == empty_project_root
    assert new_sha != first_sha

    _, foundation = load_foundation(empty_project_root)
    assert foundation.statement == "Will X cause Y?"

    # Commit log should have exactly 2 commits now.
    count = git.run_git(["rev-list", "--count", "HEAD"], cwd=empty_project_root).stdout.strip()
    assert count == "2"

    # Commit subject should reflect the change.
    subject = git.run_git(["log", "-1", "--format=%s"], cwd=empty_project_root).stdout.strip()
    assert "modelling question" in subject.lower()
