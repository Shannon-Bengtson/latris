"""The ONLY place that creates commits.

Every mutating operation ends by calling ``auto_commit``. This guarantees:
- Identity is checked before a commit is ever attempted.
- Commit messages carry a consistent ``Provenance:`` trailer.
- A single place to evolve commit shape in future (e.g. trailers for
  ai-proposed changes).

When a :func:`~latris.operations.batch.batch` context manager is
active, ``auto_commit`` defers its work: it records touched paths in the
batch state but does **not** stage or commit.  The batch's ``__exit__``
calls ``auto_commit`` once with the accumulated paths.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal

from latris._mutation_signal import mark_own_mutation
from latris.perf import span
from latris.repo import git

if TYPE_CHECKING:
    from latris.operations.batch import _BatchState

Provenance = Literal["human-authored", "ai-proposed", "ai-verified"]


def _get_active_batch() -> _BatchState | None:
    """Lazy import to avoid circular dependency with batch.py."""
    from latris.operations.batch import get_active_batch

    return get_active_batch()


def auto_commit(
    root: Path,
    *,
    subject: str,
    body: str = "",
    provenance: Provenance = "human-authored",
    paths: list[Path] | None = None,
) -> str:
    """Stage changes (all by default) and commit with the conventional message shape.

    Returns the new commit SHA. Raises ``IdentityError`` if the git identity
    guard refuses the current configuration.

    When called inside an active :func:`~latris.operations.batch.batch`,
    paths are accumulated but no commit is created.  Returns ``""`` (empty
    string) in that case.
    """
    batch_state = _get_active_batch()
    if batch_state is not None:
        # Batch mode: accumulate paths, skip stage/commit.
        if paths is None:
            batch_state.use_add_all = True
        else:
            batch_state.touched_paths.extend(paths)
        return ""

    with span("auto_commit", n_paths=len(paths) if paths is not None else None):
        with span("ensure_identity"):
            git.ensure_identity(root)
        with span("git_add", mode="all" if paths is None else "paths"):
            if paths is None:
                git.add_all(root)
            else:
                git.add(root, paths)

        # If nothing was staged (e.g. a re-projection that produced identical
        # bytes), skip the commit and return the current HEAD SHA instead of
        # failing with "nothing to commit".
        with span("git_status"):
            status = git.run_git(["status", "--porcelain"], cwd=root).stdout.strip()
        if not status:
            with span("git_head_sha"):
                return git.head_sha(root)

        trailer = f"Provenance: {provenance}"
        message = f"{subject}\n\n{body.rstrip()}\n\n{trailer}" if body else f"{subject}\n\n{trailer}"
        with span("git_commit"):
            sha = git.commit(root, message)
        # Signal the file watcher that the next ~2s of file events are
        # our own write — the API response has already rehydrated the
        # client, so a redundant broadcast would cause a double reload.
        mark_own_mutation()
        return sha
