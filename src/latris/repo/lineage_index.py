"""Materialise the lineage tree from git topology.

The schema's ``LineageNode`` carries only workflow-level fields
(``id``, ``name``, ``maturity``, ``relationship``, ``notes``,
``created_by``). Branch parentage is recovered from git on demand —
that's the "lean on git" half of the schema-rubric contract.

The cost is a few extra ``git`` invocations per tree build; commits
are immutable, so callers can cache the result freely.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from latris.repo import git
from latris.repo.yaml_io import load_model_from_string
from latris.schema import LineageNode


@dataclass(frozen=True)
class LineageIndex:
    """Materialised lineage tree: nodes + derived edges."""

    nodes: dict[str, LineageNode] = field(default_factory=dict)
    """branch name → LineageNode."""

    edges: list[tuple[str, str]] = field(default_factory=list)
    """List of ``(parent_node_id, child_node_id)`` pairs."""

    branch_for_node: dict[str, str] = field(default_factory=dict)
    """node id → branch name."""


def build_lineage_index(root: Path) -> LineageIndex:
    """Walk lineage branches and reconstruct the tree from git topology."""
    branches = ["main", *git.list_branches(root, pattern="lineage/*")]

    nodes: dict[str, LineageNode] = {}
    branch_for_node: dict[str, str] = {}
    for branch in branches:
        node = _load_node_at_branch(root, branch)
        if node is not None:
            nodes[branch] = node
            branch_for_node[node.id] = branch

    edges: list[tuple[str, str]] = []
    all_branches = list(nodes.keys())
    forks = {b: _fork_point(root, b, nodes[b].id) for b in all_branches if b != "main"}
    own = {b: _own_commits(root, b, forks.get(b)) for b in all_branches}
    for branch, node in nodes.items():
        if node.relationship == "original" or branch == "main":
            continue
        parent_branch = _owner(forks[branch], branch, own) if forks[branch] else None
        if parent_branch is None:
            parent_branch = _derive_parent_branch(root, branch, all_branches)
        if parent_branch is not None and parent_branch in nodes:
            edges.append((nodes[parent_branch].id, node.id))

    return LineageIndex(nodes=nodes, edges=edges, branch_for_node=branch_for_node)


def _fork_point(root: Path, branch: str, version_id: str) -> str | None:
    """The commit *branch*'s version was made from: the parent of the commit that first wrote its id into
    ``lineage-node.yaml`` (renaming a version keeps its id). ``None`` when that can't be found."""
    out = git.run_git(
        ["log", "--first-parent", "--reverse", "--format=%H %P", f"-S{version_id}", branch,
         "--", ".graph-tooling/lineage-node.yaml"],
        cwd=root, check=False,
    )
    lines = out.stdout.split("\n") if out.returncode == 0 else []
    parts = lines[0].split() if lines and lines[0].strip() else []
    return parts[1] if len(parts) > 1 else None


def _own_commits(root: Path, branch: str, fork: str | None) -> set[str]:
    """The commits made on *branch* itself: its first-parent line, after its fork point for an alternative.
    Work merged in from another version (getting the latest) is that version's, not this one's."""
    args = ["rev-list", "--first-parent", branch] + ([f"^{fork}"] if fork else [])
    out = git.run_git(args, cwd=root, check=False)
    return set(out.stdout.split()) if out.returncode == 0 else set()


def _owner(commit: str, branch: str, own: dict[str, set[str]]) -> str | None:
    """The version whose own line *commit* was made on (an alternative's before the original's)."""
    owners = [b for b, commits in own.items() if b != branch and commit in commits]
    lineage = [b for b in owners if b != "main"]
    return (lineage or owners or [None])[0]


def _load_node_at_branch(root: Path, branch: str) -> LineageNode | None:
    try:
        text = git.show_file(root, branch, ".graph-tooling/lineage-node.yaml")
    except git.GitError:
        return None
    try:
        return load_model_from_string(LineageNode, text)
    except Exception:
        return None


def _derive_parent_branch(
    root: Path,
    branch: str,
    all_branches: list[str],
) -> str | None:
    """Return the branch *branch* was created from, or ``None`` — the fallback when its creation commit
    can't be found (see :func:`_fork_point`).

    Strategy: find the first commit unique to *branch* (not reachable
    from any other lineage branch), take its first parent commit, then
    pick whichever other branch reaches that parent.
    """
    others = [b for b in all_branches if b != branch]
    if not others:
        return None

    log_args = ["log", branch, "--reverse", "--format=%H"]
    for other in others:
        log_args += [f"^{other}"]
    out = git.run_git(log_args, cwd=root, check=False)
    if out.returncode != 0 or not out.stdout.strip():
        return None
    first_unique_sha = out.stdout.splitlines()[0].strip()

    parent_out = git.run_git(
        ["log", "-1", "--format=%P", first_unique_sha], cwd=root, check=False
    )
    parents = parent_out.stdout.strip().split()
    if not parents:
        return None
    parent_sha = parents[0]

    # Prefer the most-specific branch (lineage branches before main).
    candidates = [b for b in others if b != "main"] + (["main"] if "main" in others else [])
    for cand in candidates:
        check = git.run_git(
            ["merge-base", "--is-ancestor", parent_sha, cand], cwd=root, check=False
        )
        if check.returncode == 0:
            return cand
    return None
