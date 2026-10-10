"""Git remote transport wrappers — exercised against local bare repos (no network)."""

from __future__ import annotations

from pathlib import Path

from latris.repo import git


def _commit(repo: Path, name: str, content: str) -> None:
    (repo / name).write_text(content, encoding="utf-8")
    git.add_all(repo)
    git.commit(repo, f"write {name}")


def test_init_bare_remote_clone_roundtrip(tmp_path: Path, git_identity) -> None:
    src = tmp_path / "src"
    src.mkdir()
    git.init(src)
    _commit(src, "a.txt", "hi")

    bare = tmp_path / "remote.git"
    git.init_bare(bare)
    assert not git.has_remote(src, "origin")
    git.remote_add(src, "origin", str(bare))
    assert git.has_remote(src, "origin")
    assert git.list_remotes(src)["origin"] == str(bare)

    git.push(src, "origin", "main", set_upstream=True)

    dest = tmp_path / "dest"
    git.clone(str(bare), dest)
    assert (dest / "a.txt").read_text(encoding="utf-8") == "hi"


def test_remote_set_url(tmp_path: Path, git_identity) -> None:
    src = tmp_path / "src"
    src.mkdir()
    git.init(src)
    git.remote_add(src, "origin", str(tmp_path / "one.git"))
    git.remote_set_url(src, "origin", str(tmp_path / "two.git"))
    assert git.list_remotes(src)["origin"] == str(tmp_path / "two.git")


def test_ahead_behind(tmp_path: Path, git_identity) -> None:
    src = tmp_path / "src"
    src.mkdir()
    git.init(src)
    _commit(src, "a.txt", "1")
    bare = tmp_path / "remote.git"
    git.init_bare(bare)
    git.remote_add(src, "origin", str(bare))
    git.push(src, "origin", "main", set_upstream=True)

    assert git.ahead_behind(src) == (0, 0)
    _commit(src, "a.txt", "2")
    assert git.ahead_behind(src) == (1, 0)


def test_ahead_behind_no_upstream(tmp_path: Path, git_identity) -> None:
    src = tmp_path / "src"
    src.mkdir()
    git.init(src)
    _commit(src, "a.txt", "1")
    assert git.ahead_behind(src) is None


def test_has_conflicts_clean_tree(tmp_path: Path, git_identity) -> None:
    src = tmp_path / "src"
    src.mkdir()
    git.init(src)
    _commit(src, "a.txt", "1")
    assert git.has_conflicts(src) is False


def test_local_identity_and_config(tmp_path: Path, git_identity) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    git.init(repo)
    git.set_local_identity(repo, "Jane Doe", "jane@example.com")
    assert git.get_config(repo, "user.name") == "Jane Doe"
    assert git.get_config(repo, "user.email") == "jane@example.com"
    assert git.get_config(repo, "nonexistent.key") is None
    git.set_config(repo, "latris.projectid", "proj_1")
    assert git.get_config(repo, "latris.projectid") == "proj_1"
