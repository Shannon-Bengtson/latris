"""Undo and redo, as steps through what a person did.

History is append-only: an undo is a new commit that reverts a person's action
(and the bookkeeping commits that followed from it); a redo is a new commit
that reverts that undo. Nothing is reset or rewritten.

Where the steps are is read from the log, so it needs no state of its own and
survives a restart:

- An **undo commit** carries ``Undo-Of: <sha>``; a **redo commit** carries
  ``Redo-Of: <undo sha>``.
- A **bookkeeping commit** (``Bookkeeping: derived`` — a view re-projected, the
  model's elements mapped into a model type when it opens) is never a step by
  itself: it belongs to the action before it and is undone with it.
- Any other commit is an action. A new action clears what could be redone.
- A merge, the commit that created an alternative, and the first commit are
  floors: undo doesn't go past them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from latris.operations.commit import BOOKKEEPING_TRAILER, auto_commit
from latris.repo import git
from latris.repo.project import require_project

UNDO_TRAILER = "Undo-Of"
REDO_TRAILER = "Redo-Of"
_WALK_LIMIT = 300
_SEP = "\x1f"
_END = "\x1e"


class NothingToUndo(ValueError):
    """There is no step to undo (or redo) from here."""


class CannotUndo(ValueError):
    """The step can't be reverted cleanly (later changes build on it)."""


@dataclass
class _Commit:
    sha: str
    parents: list[str]
    subject: str
    undo_of: str
    redo_of: str
    bookkeeping: bool


@dataclass
class _Step:
    sha: str
    subject: str
    bookkeeping: list[str] = field(default_factory=list)  # oldest first


@dataclass
class HistoryStatus:
    """What undo and redo would do next: the action's subject, or None when there is none."""

    undo: str | None
    redo: str | None


def _plain(subject: str) -> str:
    """The action's own subject, whatever undo/redo wrapped it in."""
    while True:
        for prefix in ("Undo: ", "Redo: "):
            if subject.startswith(prefix):
                subject = subject[len(prefix):]
                break
        else:
            return subject


def _log(root: Path) -> list[_Commit]:
    """The first-parent log from HEAD, newest first."""
    fmt = _SEP.join(
        [
            "%H",
            "%P",
            "%s",
            f"%(trailers:key={UNDO_TRAILER},valueonly,separator=%x20)",
            f"%(trailers:key={REDO_TRAILER},valueonly,separator=%x20)",
            f"%(trailers:key={BOOKKEEPING_TRAILER},valueonly,separator=%x20)",
        ]
    ) + _END
    out = git.run_git(["log", "--first-parent", f"-n{_WALK_LIMIT}", f"--format={fmt}"], cwd=root).stdout
    commits: list[_Commit] = []
    for record in out.split(_END):
        record = record.strip("\n")
        if not record:
            continue
        sha, parents, subject, undo_of, redo_of, bookkeeping = record.split(_SEP)
        commits.append(
            _Commit(sha, parents.split(), subject, undo_of.strip(), redo_of.strip(), bool(bookkeeping.strip()))
        )
    return commits


def _stacks(root: Path) -> tuple[list[_Step], list[_Step]]:
    """(what can be undone, what can be redone), each with the next step last."""
    log = _log(root)
    on_alternative = git.current_branch(root) != git.DEFAULT_BRANCH
    since_floor: list[_Commit] = []
    for c in log:
        if len(c.parents) != 1 or (on_alternative and c.subject.startswith("Created alternative:")):
            break
        since_floor.append(c)
    undo: list[_Step] = []
    redo: list[_Step] = []
    for c in reversed(since_floor):
        if c.undo_of:
            if undo:
                undo.pop()
            redo.append(_Step(c.sha, _plain(c.subject)))
        elif c.redo_of:
            if redo:
                redo.pop()
            undo.append(_Step(c.sha, _plain(c.subject)))
        elif c.bookkeeping:
            if undo:
                undo[-1].bookkeeping.append(c.sha)
        else:
            undo.append(_Step(c.sha, c.subject))
            redo.clear()
    return undo, redo


def status(root: Path | None = None) -> HistoryStatus:
    paths = require_project(root)
    undo, redo = _stacks(paths.root)
    return HistoryStatus(undo=undo[-1].subject if undo else None, redo=redo[-1].subject if redo else None)


def _revert(root: Path, shas: list[str], *, subject: str, trailer: str) -> str:
    """Revert ``shas`` (given newest first) as one commit."""
    try:
        git.run_git(["revert", "--no-commit", *shas], cwd=root)
    except git.GitError as exc:
        git.run_git(["revert", "--abort"], cwd=root, check=False)
        raise CannotUndo("This change can't be taken back by itself: later changes build on it.") from exc
    try:
        return auto_commit(root, subject=subject, paths=[], trailers=[trailer], allow_empty=True)
    finally:
        # ``revert --no-commit`` leaves a sequencer state behind; the commit above ends it.
        git.run_git(["revert", "--quit"], cwd=root, check=False)


def undo(root: Path | None = None) -> tuple[str, str]:
    """Take back the last action. Returns (new commit sha, the action's subject)."""
    paths = require_project(root)
    steps, _ = _stacks(paths.root)
    if not steps:
        raise NothingToUndo("Nothing more to undo on this version.")
    step = steps[-1]
    sha = _revert(
        paths.root,
        [*reversed(step.bookkeeping), step.sha],
        subject=f"Undo: {step.subject}",
        trailer=f"{UNDO_TRAILER}: {step.sha}",
    )
    return sha, step.subject


def redo(root: Path | None = None) -> tuple[str, str]:
    """Put back the last action undone. Returns (new commit sha, the action's subject)."""
    paths = require_project(root)
    _, steps = _stacks(paths.root)
    if not steps:
        raise NothingToUndo("Nothing to redo.")
    step = steps[-1]
    sha = _revert(
        paths.root,
        [step.sha],
        subject=f"Redo: {step.subject}",
        trailer=f"{REDO_TRAILER}: {step.sha}",
    )
    return sha, step.subject
