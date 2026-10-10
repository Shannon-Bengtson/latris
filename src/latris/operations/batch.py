"""Batch context manager for grouping multiple mutations into a single commit.

Usage::

    from latris.operations.batch import batch

    with batch(root, subject="Add Price node and connect to Demand"):
        node_ops.add_node("Price", root=root)
        edge_ops.add_edge("Price", "Demand", root=root)
    # → one git commit instead of two

Inside a batch, ``auto_commit`` defers staging and committing.  On
successful exit the batch stages all touched paths and creates a single
commit.  On exception the working tree is reverted to HEAD and no commit
is created.

Nesting is not supported — entering a batch while one is already active
raises ``RuntimeError``.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path

from latris.operations.commit import Provenance, auto_commit

_BATCH_STATE: ContextVar[_BatchState | None] = ContextVar("_batch_state", default=None)


@dataclass
class _BatchState:
    """Mutable accumulator carried through a batch scope."""

    root: Path
    subject: str
    provenance: Provenance
    touched_paths: list[Path] = field(default_factory=list)
    use_add_all: bool = False


def get_active_batch() -> _BatchState | None:
    """Return the active batch state, or ``None`` if no batch is in progress."""
    return _BATCH_STATE.get()


@contextmanager
def batch(
    root: Path,
    *,
    subject: str,
    provenance: Provenance = "human-authored",
) -> Iterator[None]:
    """Group multiple mutations into a single git commit.

    Parameters
    ----------
    root:
        Project root directory.
    subject:
        Commit message subject line for the combined commit.
    provenance:
        Provenance trailer value (default ``"human-authored"``).

    Raises
    ------
    RuntimeError
        If a batch is already active (nesting not supported).
    """
    if _BATCH_STATE.get() is not None:
        raise RuntimeError("Nested batch() is not supported")

    state = _BatchState(root=root, subject=subject, provenance=provenance)
    token = _BATCH_STATE.set(state)
    try:
        yield
    except BaseException:
        # Revert any uncommitted working-tree changes back to HEAD.
        from latris.repo import git

        git.run_git(["checkout", "--", "."], cwd=root, check=False)
        _BATCH_STATE.reset(token)
        raise
    else:
        # Clear the batch state BEFORE calling auto_commit so it sees
        # "no active batch" and actually stages + commits.
        _BATCH_STATE.reset(token)
        if state.use_add_all or state.touched_paths:
            paths = state.touched_paths if not state.use_add_all else None
            auto_commit(
                root,
                subject=state.subject,
                provenance=state.provenance,
                paths=paths if paths else None,
            )
