"""Tests for the commit chokepoint (operations/commit.py).

Every mutation in the system commits through ``auto_commit``.
These tests verify the commit itself, Provenance trailers,
no-op on clean tree, batch deferral, and identity enforcement.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations.commit import auto_commit
from latris.operations.init import init_project
from latris.repo import git


@pytest.fixture
def project(tmp_path: Path, git_identity):
    root = tmp_path / "proj"
    init_project(root, statement="Q?")
    return root


def _commit_count(root: Path) -> int:
    return int(git.run_git(["rev-list", "--count", "HEAD"], cwd=root).stdout.strip())


def _last_commit_body(root: Path) -> str:
    return git.run_git(["log", "-1", "--format=%B"], cwd=root).stdout


def _touch(project: Path, name: str = "scratch.txt", content: str = "changed") -> Path:
    """Create/overwrite a tracked file to produce a real git diff."""
    p = project / name
    p.write_text(content, encoding="utf-8")
    return p


# ── Normal commit ───────────────────���───────────────────────────────


def test_auto_commit_creates_commit(project: Path) -> None:
    before = _commit_count(project)
    _touch(project)
    sha = auto_commit(project, subject="Test commit")
    assert len(sha) == 40
    assert _commit_count(project) == before + 1


def test_provenance_trailer_human(project: Path) -> None:
    _touch(project)
    auto_commit(project, subject="Human change", provenance="human-authored")
    body = _last_commit_body(project)
    assert "Provenance: human-authored" in body


def test_provenance_trailer_ai(project: Path) -> None:
    _touch(project)
    auto_commit(project, subject="AI change", provenance="ai-proposed")
    body = _last_commit_body(project)
    assert "Provenance: ai-proposed" in body


def test_subject_and_body(project: Path) -> None:
    _touch(project)
    auto_commit(project, subject="Title", body="Extra detail here")
    body = _last_commit_body(project)
    assert "Title" in body
    assert "Extra detail here" in body


# ── No-op when tree is clean ────��─────────────────────────���─────────


def test_no_op_when_nothing_changed(project: Path) -> None:
    """If nothing changed since last commit, return HEAD SHA — no new commit."""
    before = _commit_count(project)
    sha = auto_commit(project, subject="Should be no-op")
    assert _commit_count(project) == before  # no new commit
    assert sha == git.head_sha(project)


# ── Explicit paths vs add-all ─────────��─────────────────���───────────


def test_explicit_paths_stages_only_those(project: Path) -> None:
    """When paths are given, only those files are staged."""
    file_a = _touch(project, "file_a.txt", "aaa")
    _touch(project, "file_b.txt", "bbb")

    before = _commit_count(project)
    auto_commit(project, subject="Only file_a", paths=[file_a])
    assert _commit_count(project) == before + 1

    # file_b should still be untracked/modified
    status = git.run_git(["status", "--porcelain"], cwd=project).stdout.strip()
    assert "file_b.txt" in status


# ── Batch deferral ────────��─────────────────────────────────────────


def test_batch_deferral_returns_empty_string(project: Path) -> None:
    """When a batch is active, auto_commit defers and returns ''."""
    from latris.operations.batch import batch

    f = _touch(project)
    before = _commit_count(project)
    with batch(project, subject="Batch"):
        sha = auto_commit(project, subject="Deferred", paths=[f])
        assert sha == ""
    # The batch exit creates the commit
    assert _commit_count(project) == before + 1


def test_auto_commit_marks_mutation_signal(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A successful commit must stamp the watcher suppression window
    so the file watcher doesn't broadcast a redundant ``state_changed``
    event that would trigger a double reload in the GUI."""
    import latris._mutation_signal as sig

    # Reset the signal so the test is deterministic.
    monkeypatch.setattr(sig, "_last_own_mutation", 0.0)
    assert sig.is_suppressed() is False

    _touch(project)
    auto_commit(project, subject="Triggers suppression")
    assert sig.is_suppressed() is True


def test_auto_commit_no_op_does_not_mark_mutation(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A no-op auto_commit (clean tree) must NOT stamp the suppression
    window — there's no broadcast coming and we don't want to mask a
    later real broadcast."""
    import latris._mutation_signal as sig

    monkeypatch.setattr(sig, "_last_own_mutation", 0.0)
    auto_commit(project, subject="Nothing to commit")
    assert sig.is_suppressed() is False


def test_batch_accumulates_paths(project: Path) -> None:
    """Paths passed to auto_commit during a batch are accumulated."""
    from latris.operations.batch import _BATCH_STATE, batch

    f1 = _touch(project, "f1.txt", "one")
    f2 = _touch(project, "f2.txt", "two")
    with batch(project, subject="Accumulate"):
        auto_commit(project, subject="a", paths=[f1])
        auto_commit(project, subject="b", paths=[f2])
        state = _BATCH_STATE.get()
        assert state is not None
        assert f1 in state.touched_paths
        assert f2 in state.touched_paths
        assert not state.use_add_all


def test_batch_none_paths_sets_add_all(project: Path) -> None:
    """Passing paths=None during a batch sets use_add_all."""
    from latris.operations.batch import _BATCH_STATE, batch

    _touch(project)
    with batch(project, subject="AddAll"):
        auto_commit(project, subject="a", paths=None)
        state = _BATCH_STATE.get()
        assert state is not None
        assert state.use_add_all is True
