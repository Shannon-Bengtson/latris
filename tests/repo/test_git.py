from __future__ import annotations

from pathlib import Path

import pytest

from latris.repo import git


def test_ensure_git_available_returns_path() -> None:
    path = git.ensure_git_available()
    assert path.exists()


def test_ensure_identity_accepts_env(git_identity: tuple[str, str]) -> None:
    name, email = git.ensure_identity()
    assert name == git_identity[0]
    assert email == git_identity[1]


def test_ensure_identity_rejects_generic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_AUTHOR_NAME", "root")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "you@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "root")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "you@example.com")
    with pytest.raises(git.IdentityError, match="generic"):
        git.ensure_identity()


def test_init_add_commit_roundtrip(tmp_path: Path, git_identity: tuple[str, str]) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    git.init(repo)
    assert (repo / ".git").is_dir()

    (repo / "hello.txt").write_text("hi\n", encoding="utf-8", newline="")
    git.add_all(repo)
    sha = git.commit(repo, "Add hello")
    assert len(sha) == 40  # full SHA-1
    assert git.head_sha(repo) == sha

    name, email = git.head_author(repo)
    assert name == git_identity[0]
    assert email == git_identity[1]


def test_is_repo_true_and_false(tmp_path: Path, git_identity: tuple[str, str]) -> None:
    assert git.is_repo(tmp_path / "missing") is False
    (tmp_path / ".gitkeep").touch()  # unrelated file
    git.init(tmp_path)
    assert git.is_repo(tmp_path) is True


def test_commit_timestamp_returns_aware_datetime(
    tmp_path: Path,
    git_identity: tuple[str, str],
) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    git.init(repo)
    (repo / "f.txt").write_text("x\n", encoding="utf-8", newline="")
    git.add_all(repo)
    sha = git.commit(repo, "Initial")

    ts = git.commit_timestamp(sha, repo)
    assert ts.tzinfo is not None


def test_commit_timestamp_many_batches(
    tmp_path: Path,
    git_identity: tuple[str, str],
) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    git.init(repo)
    shas: list[str] = []
    for i in range(3):
        (repo / f"f{i}.txt").write_text(str(i), encoding="utf-8", newline="")
        git.add_all(repo)
        shas.append(git.commit(repo, f"Commit {i}"))

    out = git.commit_timestamp_many(shas, repo)
    assert set(out) == set(shas)
    assert all(ts.tzinfo is not None for ts in out.values())
    # Empty input returns empty dict, not error.
    assert git.commit_timestamp_many([], repo) == {}
