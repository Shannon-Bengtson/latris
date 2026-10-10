"""The single chokepoint for all git operations.

Everything that runs ``subprocess`` against ``git`` goes through this module.
Centralising means: one place to add telemetry, one place to stub for tests,
one place to enforce cross-platform quoting rules.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime
from functools import lru_cache
from pathlib import Path

DEFAULT_BRANCH = "main"

# Bound network git operations (clone/fetch/push/pull) so a dead connection
# can't hang the desktop app forever. Local ops (commit/status/log) are fast
# and left unbounded. Generous enough for slow links on text-sized projects.
NETWORK_TIMEOUT = 300.0

GENERIC_NAMES = frozenset({"", "root", "user", "admin", "guest", "you"})
GENERIC_EMAILS = frozenset(
    {
        "",
        "you@example.com",
        "user@example.com",
        "root@localhost",
        "admin@localhost",
    }
)


class GitError(RuntimeError):
    """Raised for any git-related failure."""


class IdentityError(GitError):
    """Git author/committer identity is missing or looks generic."""


def which_git() -> Path | None:
    path = shutil.which("git")
    return Path(path) if path else None


def ensure_git_available() -> Path:
    """Return the git binary path or raise ``GitError`` with a per-OS install hint."""
    git = which_git()
    if git is not None:
        return git
    if os.name == "nt":
        hint = "Install via `winget install --id Git.Git` or https://git-scm.com/"
    elif _is_macos():
        hint = "Install via `xcode-select --install` or `brew install git`."
    else:
        hint = "Install via your package manager (e.g. `apt install git`)."
    raise GitError(f"git binary not found on PATH. {hint}")


def _is_macos() -> bool:
    import sys

    return sys.platform == "darwin"


def run_git(
    args: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    env: dict[str, str] | None = None,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run ``git <args>`` and return the completed process.

    Always uses a list argument (never ``shell=True``). Text mode, UTF-8.

    ``GIT_TERMINAL_PROMPT=0`` is forced so git fails fast instead of blocking
    on an interactive credential/username prompt — in the desktop app there is
    no terminal to answer one, so a prompt would hang forever. ``timeout``
    (seconds) bounds the call and surfaces as ``GitError`` on expiry; callers
    doing network I/O pass :data:`NETWORK_TIMEOUT`.
    """
    ensure_git_available()
    cmd = ["git", *args]
    run_env = dict(env) if env is not None else os.environ.copy()
    run_env.setdefault("GIT_TERMINAL_PROMPT", "0")
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd is not None else None,
            env=run_env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"git {' '.join(args)} timed out after {timeout}s") from exc
    if check and result.returncode != 0:
        raise GitError(
            f"git {' '.join(args)} failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout.strip()}\nstderr: {result.stderr.strip()}"
        )
    return result


def get_effective_identity(cwd: Path | None = None) -> tuple[str, str]:
    """Return the (name, email) git will actually use for a commit.

    Resolution order matches git's own: env vars override config; config is
    read with local-repo precedence over global when ``cwd`` points inside a
    repo.
    """
    name = os.environ.get("GIT_AUTHOR_NAME") or os.environ.get("GIT_COMMITTER_NAME") or ""
    email = os.environ.get("GIT_AUTHOR_EMAIL") or os.environ.get("GIT_COMMITTER_EMAIL") or ""
    if name and email:
        return name, email

    try:
        if cwd is not None and (cwd / ".git").exists():
            got_name = run_git(["config", "user.name"], cwd=cwd, check=False).stdout.strip()
            got_email = run_git(["config", "user.email"], cwd=cwd, check=False).stdout.strip()
        else:
            got_name = run_git(["config", "--global", "user.name"], check=False).stdout.strip()
            got_email = run_git(["config", "--global", "user.email"], check=False).stdout.strip()
    except GitError:
        got_name = got_email = ""

    return name or got_name, email or got_email


def ensure_identity(cwd: Path | None = None) -> tuple[str, str]:
    """Verify a usable identity is available. Raise ``IdentityError`` otherwise."""
    name, email = get_effective_identity(cwd)
    if not name:
        raise IdentityError('git user.name is not set. Run: git config --global user.name "Your Name"')
    if not email:
        raise IdentityError('git user.email is not set. Run: git config --global user.email "you@example.com"')
    if name.strip().lower() in GENERIC_NAMES:
        raise IdentityError(
            f"git user.name '{name}' looks generic. Set a real name: git config --global user.name \"Your Name\""
        )
    if email.strip().lower() in GENERIC_EMAILS:
        raise IdentityError(
            f"git user.email '{email}' looks generic. Set a real email: "
            'git config --global user.email "you@example.com"'
        )
    return name, email


def set_local_identity(cwd: Path, name: str, email: str) -> None:
    """Set repo-local ``user.name``/``user.email`` (used per-clone for sync)."""
    run_git(["config", "user.name", name], cwd=cwd)
    run_git(["config", "user.email", email], cwd=cwd)


def get_config(cwd: Path, key: str) -> str | None:
    """Read a git config value, or ``None`` if unset."""
    res = run_git(["config", "--get", key], cwd=cwd, check=False)
    if res.returncode != 0:
        return None
    return res.stdout.strip() or None


def set_config(cwd: Path, key: str, value: str) -> None:
    run_git(["config", key, value], cwd=cwd)


def init(cwd: Path) -> None:
    """Initialise a git repository at ``cwd`` with ``main`` as the default branch."""
    run_git(["init", f"--initial-branch={DEFAULT_BRANCH}"], cwd=cwd)


def add_all(cwd: Path) -> None:
    run_git(["add", "--all"], cwd=cwd)


def add(cwd: Path, paths: list[Path]) -> None:
    if not paths:
        return
    rel = [str(p.relative_to(cwd)) if p.is_absolute() else str(p) for p in paths]
    run_git(["add", "--", *rel], cwd=cwd)


def commit(cwd: Path, message: str) -> str:
    """Create a commit with ``message``. Returns the new commit SHA."""
    run_git(["commit", "-m", message], cwd=cwd)
    return run_git(["rev-parse", "HEAD"], cwd=cwd).stdout.strip()


def head_sha(cwd: Path) -> str:
    return run_git(["rev-parse", "HEAD"], cwd=cwd).stdout.strip()


def head_author(cwd: Path) -> tuple[str, str]:
    """Return (name, email) of the HEAD commit's author."""
    fmt = "%an%n%ae"
    out = run_git(["log", "-1", f"--format={fmt}"], cwd=cwd).stdout.splitlines()
    if len(out) < 2:
        raise GitError("could not parse git log output for HEAD author")
    return out[0], out[1]


def revert_head(cwd: Path) -> str:
    """Revert the HEAD commit (creates a new commit). Returns the new SHA."""
    run_git(["revert", "HEAD", "--no-edit"], cwd=cwd)
    return run_git(["rev-parse", "HEAD"], cwd=cwd).stdout.strip()


def is_repo(cwd: Path) -> bool:
    """True iff ``cwd`` is inside a git working tree."""
    if not cwd.exists():
        return False
    res = run_git(["rev-parse", "--is-inside-work-tree"], cwd=cwd, check=False)
    return res.returncode == 0 and res.stdout.strip() == "true"


# -- Branch operations (lineage) -----------------------------------------------


def current_branch(cwd: Path) -> str:
    """Return the name of the currently checked-out branch."""
    return run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd).stdout.strip()


def list_branches(cwd: Path, *, pattern: str | None = None) -> list[str]:
    """List local branches, optionally filtered by glob pattern."""
    args = ["branch", "--list", "--format=%(refname:short)"]
    if pattern is not None:
        args.append(pattern)
    out = run_git(args, cwd=cwd).stdout
    return [b for b in out.splitlines() if b.strip()]


def create_branch(cwd: Path, name: str, *, start: str | None = None) -> None:
    """Create a new branch at *start* (default: HEAD). Does not checkout."""
    args = ["branch", name]
    if start is not None:
        args.append(start)
    run_git(args, cwd=cwd)


def checkout(cwd: Path, branch: str) -> None:
    """Switch the working tree to *branch*. Raises ``GitError`` on failure."""
    run_git(["checkout", branch], cwd=cwd)


def show_file(cwd: Path, ref: str, path: str) -> str:
    """Read a file's contents from any ref without checkout.

    Raises ``GitError`` if the file does not exist at that ref.
    """
    # git requires forward slashes even on Windows.
    normalised = path.replace("\\", "/")
    return run_git(["show", f"{ref}:{normalised}"], cwd=cwd).stdout


def recent_commits(cwd: Path, limit: int = 20) -> list[dict[str, str]]:
    """Return the *limit* most recent commits as dicts.

    Each dict has keys: ``sha``, ``author_name``, ``author_email``,
    ``timestamp`` (ISO-8601), ``subject``.
    """
    sep = "%x00"  # NUL byte separator within a record
    fmt = f"%H{sep}%an{sep}%ae{sep}%aI{sep}%s"
    result = run_git(
        ["log", f"-{limit}", f"--format={fmt}"],
        cwd=cwd,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return []
    entries: list[dict[str, str]] = []
    for line in result.stdout.strip().splitlines():
        parts = line.split("\x00")
        if len(parts) < 5:
            continue
        entries.append(
            {
                "sha": parts[0],
                "author_name": parts[1],
                "author_email": parts[2],
                "timestamp": parts[3],
                "subject": parts[4],
            }
        )
    return entries


def has_uncommitted_changes(cwd: Path) -> bool:
    """True if the working tree or index has uncommitted changes."""
    out = run_git(["status", "--porcelain"], cwd=cwd).stdout
    return bool(out.strip())


def has_conflicts(cwd: Path) -> bool:
    """True if the working tree has unmerged (conflicted) paths."""
    out = run_git(["diff", "--name-only", "--diff-filter=U"], cwd=cwd).stdout
    return bool(out.strip())


# -- Remote operations (sync) -------------------------------------------------
#
# Every remote function accepts an optional ``env`` so callers can inject a
# credential-providing environment (e.g. ``GIT_ASKPASS`` + a one-shot token)
# at push/pull time without persisting secrets in the remote URL or git config.


def init_bare(path: Path) -> None:
    """Initialise a bare repository at *path* (a push/pull target)."""
    run_git(["init", "--bare", f"--initial-branch={DEFAULT_BRANCH}", str(path)])


def list_remotes(cwd: Path) -> dict[str, str]:
    """Return a mapping of remote name → fetch URL."""
    out = run_git(["remote", "-v"], cwd=cwd).stdout
    remotes: dict[str, str] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[-1] == "(fetch)":
            remotes[parts[0]] = parts[1]
    return remotes


def has_remote(cwd: Path, name: str = "origin") -> bool:
    return name in list_remotes(cwd)


def remote_add(cwd: Path, name: str, url: str) -> None:
    """Add a remote named *name* pointing at *url*."""
    run_git(["remote", "add", name, url], cwd=cwd)


def remote_set_url(cwd: Path, name: str, url: str) -> None:
    """Point an existing remote at a new URL."""
    run_git(["remote", "set-url", name, url], cwd=cwd)


def clone(url: str, dest: Path, *, env: dict[str, str] | None = None) -> None:
    """Clone *url* into *dest* (which must not already exist)."""
    run_git(["clone", url, str(dest)], env=env, timeout=NETWORK_TIMEOUT)


def fetch(cwd: Path, remote: str = "origin", *, env: dict[str, str] | None = None) -> None:
    run_git(["fetch", remote], cwd=cwd, env=env, timeout=NETWORK_TIMEOUT)


def fetch_branch(
    cwd: Path,
    remote: str,
    refspec: str,
    *,
    env: dict[str, str] | None = None,
) -> None:
    """Fetch a single *refspec* from *remote* (e.g. ``"lineage/X:lineage/X"``).

    Used to fast-forward or materialise a non-checked-out local branch without
    touching the working tree. A bare ``src:dst`` refspec only updates ``dst``
    if it can fast-forward; git refuses a non-ff update unless forced.
    """
    run_git(["fetch", remote, refspec], cwd=cwd, env=env, timeout=NETWORK_TIMEOUT)


def list_remote_branches(
    cwd: Path,
    remote: str = "origin",
    *,
    pattern: str | None = None,
) -> list[str]:
    """List remote-tracking branches for *remote* as short names.

    Reads ``refs/remotes/<remote>/*`` from the local ref store — reflects the
    last fetch, no network. Returns short names (``main``, ``lineage/<ULID>``);
    excludes the symbolic ``HEAD`` ref. *pattern* is a trailing glob applied to
    the short name.
    """
    base = f"refs/remotes/{remote}/"
    args = ["for-each-ref", "--format=%(refname:short)", base + (pattern or "")]
    out = run_git(args, cwd=cwd).stdout
    prefix = f"{remote}/"
    names: list[str] = []
    for line in out.splitlines():
        short = line.strip()
        if not short or short == f"{remote}/HEAD":
            continue
        names.append(short[len(prefix):] if short.startswith(prefix) else short)
    return names


def push(
    cwd: Path,
    remote: str = "origin",
    branch: str | None = None,
    *,
    set_upstream: bool = False,
    env: dict[str, str] | None = None,
) -> None:
    args = ["push"]
    if set_upstream:
        args.append("--set-upstream")
    args.append(remote)
    if branch:
        args.append(branch)
    run_git(args, cwd=cwd, env=env, timeout=NETWORK_TIMEOUT)


def pull(
    cwd: Path,
    remote: str = "origin",
    branch: str | None = None,
    *,
    env: dict[str, str] | None = None,
) -> None:
    """Fetch and merge from *remote* (never rebases — preserves shared history)."""
    args = ["pull", "--no-rebase", remote]
    if branch:
        args.append(branch)
    run_git(args, cwd=cwd, env=env, timeout=NETWORK_TIMEOUT)


def complete_merge_with(cwd: Path, side: str) -> str:
    """Finish a conflicted merge by taking one side wholesale.

    *side* is ``"ours"`` (keep local) or ``"theirs"`` (keep remote). Resolves
    every conflicted path to that side, stages, and commits the merge. Returns
    the new HEAD sha.
    """
    if side not in ("ours", "theirs"):
        raise GitError(f"merge side must be 'ours' or 'theirs', got {side!r}")
    run_git(["checkout", f"--{side}", "--", "."], cwd=cwd)
    run_git(["add", "--all"], cwd=cwd)
    run_git(["commit", "--no-edit"], cwd=cwd)
    return head_sha(cwd)


def abort_merge(cwd: Path) -> None:
    """Abort an in-progress merge, restoring the pre-merge state."""
    run_git(["merge", "--abort"], cwd=cwd)


def merge_ours(cwd: Path, ref: str, *, env: dict[str, str] | None = None) -> str:
    """Merge *ref* into the current branch keeping our tree entirely (``-s ours``).

    Records *ref* as a merged ancestor without changing a single file, so a
    later push fast-forwards the remote while the working tree stays as-is.
    Returns the new HEAD sha. Used by Reconcile (keep mine).
    """
    run_git(["merge", "-s", "ours", "--no-edit", ref], cwd=cwd, env=env)
    return head_sha(cwd)


def reset_hard(cwd: Path, ref: str) -> str:
    """Move the current branch (and working tree) to *ref* (``reset --hard``).

    Destructive to the current branch's tip, so callers must snapshot anything
    worth keeping onto another branch first. Returns the new HEAD sha. Used by
    Reconcile (keep theirs), after the local line is preserved on an archived
    branch.
    """
    run_git(["reset", "--hard", ref], cwd=cwd)
    return head_sha(cwd)


def _count_left_right(cwd: Path, range_expr: str) -> tuple[int, int] | None:
    """Parse ``rev-list --left-right --count <range>`` into ``(ahead, behind)``.

    The range is ``<left>...<right>``; git prints ``<behind> <ahead>`` (left
    count, right count). ``None`` if the command fails or output is malformed.
    """
    res = run_git(["rev-list", "--left-right", "--count", range_expr], cwd=cwd, check=False)
    if res.returncode != 0:
        return None
    parts = res.stdout.split()
    if len(parts) != 2:
        return None
    behind, ahead = int(parts[0]), int(parts[1])
    return ahead, behind


def ahead_behind(cwd: Path, upstream: str | None = None) -> tuple[int, int] | None:
    """Return ``(ahead, behind)`` commit counts vs *upstream*, or ``None``.

    ``None`` means no upstream is configured (or the ref is unknown). Counts
    reflect the last fetch — this does not touch the network.
    """
    ref = upstream or "@{upstream}"
    return _count_left_right(cwd, f"{ref}...HEAD")


def branch_ahead_behind(cwd: Path, branch: str, upstream: str) -> tuple[int, int] | None:
    """Return ``(ahead, behind)`` of *branch* vs *upstream*, or ``None``.

    Unlike :func:`ahead_behind` (which is hard-wired to ``HEAD``), this compares
    any local *branch* against any *upstream* ref (typically
    ``origin/<branch>``) without a checkout. Counts reflect the last fetch — no
    network. ``None`` if either ref is unknown.
    """
    return _count_left_right(cwd, f"{upstream}...{branch}")


# -- Commit metadata (for ULID-redundant timestamp replacement) ---------------


@lru_cache(maxsize=4096)
def _commit_timestamp_cached(cwd_str: str, sha: str) -> datetime:
    iso = run_git(["log", "-1", "--format=%aI", sha], cwd=Path(cwd_str)).stdout.strip()
    return datetime.fromisoformat(iso)


def commit_timestamp(sha: str, cwd: Path) -> datetime:
    """Return the author timestamp of *sha* as a timezone-aware datetime.

    Commits are immutable, so the result is LRU-cached per (cwd, sha).
    """
    return _commit_timestamp_cached(str(cwd), sha)


def commit_timestamp_many(shas: list[str], cwd: Path) -> dict[str, datetime]:
    """Batch variant of :func:`commit_timestamp` — one git invocation for many shas.

    Useful for Milestone log renders where every milestone references a sha.
    Cache-warms ``_commit_timestamp_cached`` for subsequent single lookups.
    """
    if not shas:
        return {}
    result: dict[str, datetime] = {}
    uncached: list[str] = []
    for sha in shas:
        try:
            result[sha] = _commit_timestamp_cached(str(cwd), sha)
        except (GitError, ValueError):
            uncached.append(sha)
    if uncached:
        out = run_git(
            ["log", "--no-walk", "--format=%H %aI", *uncached],
            cwd=cwd,
        ).stdout
        for line in out.splitlines():
            sha, _, iso = line.partition(" ")
            if sha and iso:
                result[sha] = datetime.fromisoformat(iso)
    return result
