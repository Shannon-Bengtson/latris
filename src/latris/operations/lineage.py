"""Lineage operations — version tree, milestones, alternatives.

Each "version" is a git branch. Each branch carries a small metadata
file (``.graph-tooling/lineage-node.yaml``). Milestones are named
checkpoints within a version's save history.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from latris.operations._actor import author as _author
from latris.operations._resolve import ResolveError
from latris.operations.commit import auto_commit
from latris.repo import git
from latris.repo.lineage_index import build_lineage_index
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_model, load_model, load_model_from_string
from latris.schema import (
    AssumptionLog,
    ChallengeLog,
    DecisionLog,
    EvidenceLinkSet,
    HumanActor,
    LineageNode,
    Maturity,
    Milestone,
    MilestoneLog,
    ProjectFoundation,
    QuestionLog,
    SignoffLog,
    new_id,
    parse_id,
)

# ---------------------------------------------------------------------------
# Ensure root lineage (compatibility bridge)
# ---------------------------------------------------------------------------


def ensure_root_lineage(root: Path | None = None) -> LineageNode:
    """Ensure the current branch has a ``lineage-node.yaml``. Idempotent.

    For pre-lineage projects, synthesises a root node from ``project.yaml``
    and commits it. Returns the lineage node.
    """
    paths = require_project(root)
    root = paths.root

    if paths.lineage_node_yaml.exists():
        node = _load_lineage_node_compat(paths.lineage_node_yaml)
        return node

    # Synthesise from project metadata.
    foundation = load_model(ProjectFoundation, paths.project_yaml)
    node = LineageNode(
        id=new_id("version"),
        name=foundation.name or foundation.statement[:60],
        relationship="original",
        created_by=_author(root),
    )
    dump_model(node, paths.lineage_node_yaml)

    # Also create empty milestones log if it doesn't exist.
    if not paths.milestones_yaml.exists():
        dump_model(MilestoneLog(), paths.milestones_yaml)

    auto_commit(
        root,
        subject="Initialise lineage metadata",
        paths=[paths.lineage_node_yaml, paths.milestones_yaml],
    )
    return node


# ---------------------------------------------------------------------------
# Create milestone
# ---------------------------------------------------------------------------


def create_milestone(
    name: str,
    *,
    maturity: Maturity = "proposed",
    notes: str | None = None,
    root: Path | None = None,
) -> tuple[Milestone, str]:
    """Mark the current state as a named milestone.

    Returns ``(milestone, commit_sha)``.
    """
    paths = require_project(root)
    root = paths.root
    ensure_root_lineage(root)

    sha = git.head_sha(root)
    milestone = Milestone(
        id=new_id("milestone"),
        name=name,
        commit_sha=sha,
        maturity=maturity,
        created_by=_author(root),
        notes=notes,
    )

    log = load_model(MilestoneLog, paths.milestones_yaml) if paths.milestones_yaml.exists() else MilestoneLog()
    log.entries.append(milestone)
    dump_model(log, paths.milestones_yaml)

    commit_sha = auto_commit(
        root,
        subject=f"Marked milestone: {name}",
        paths=[paths.milestones_yaml],
    )
    return milestone, commit_sha


# ---------------------------------------------------------------------------
# Create alternative
# ---------------------------------------------------------------------------


def create_alternative(
    name: str,
    *,
    from_milestone: str | None = None,
    notes: str | None = None,
    root: Path | None = None,
) -> tuple[LineageNode, str]:
    """Create a new version as an alternative from the current state.

    If *from_milestone* is given (ID or name), the branch starts from that
    milestone's commit. Otherwise it starts from HEAD.

    Creates a new branch, writes lineage metadata, and checks it out.
    Returns ``(lineage_node, branch_name)``.
    """
    return _create_version(
        name,
        from_milestone=from_milestone,
        notes=notes,
        root=root,
    )


# ---------------------------------------------------------------------------
# Restore from milestone
# ---------------------------------------------------------------------------


def restore_milestone(
    milestone_query: str,
    name: str,
    *,
    notes: str | None = None,
    root: Path | None = None,
) -> tuple[LineageNode, str]:
    """Create a new version from a milestone's state.

    Returns ``(lineage_node, branch_name)``.
    """
    return _create_version(
        name,
        from_milestone=milestone_query,
        notes=notes,
        root=root,
    )


def _create_version(
    name: str,
    *,
    from_milestone: str | None = None,
    notes: str | None = None,
    root: Path | None = None,
) -> tuple[LineageNode, str]:
    """Internal: create a branch, write metadata, checkout."""
    paths = require_project(root)
    root = paths.root
    ensure_root_lineage(root)

    # Determine start point.
    start_point: str | None = None
    if from_milestone is not None:
        milestone = _resolve_milestone(from_milestone, root)
        start_point = milestone.commit_sha

    # Generate IDs and branch name.
    version_id = new_id("version")
    _, ulid_part = parse_id(version_id)
    branch_name = f"lineage/{ulid_part}"

    # Create and checkout the new branch.
    git.create_branch(root, branch_name, start=start_point)
    git.checkout(root, branch_name)

    # Write lineage metadata on the new branch. Parent topology is
    # derived from git via repo/lineage_index.py — not persisted here.
    node = LineageNode(
        id=version_id,
        name=name,
        relationship="alternative",
        created_by=_author(root),
        notes=notes,
    )
    dump_model(node, paths.lineage_node_yaml)
    dump_model(MilestoneLog(), paths.milestones_yaml)

    # Commit only the metadata files — paths= prevents add_all.
    auto_commit(
        root,
        subject=f"Created alternative: {name}",
        paths=[paths.lineage_node_yaml, paths.milestones_yaml],
    )
    return node, branch_name


# ---------------------------------------------------------------------------
# Switch version
# ---------------------------------------------------------------------------


def switch_version(
    version_query: str,
    *,
    root: Path | None = None,
) -> LineageNode:
    """Switch the working tree to a different version.

    Resolves by ID prefix or exact name. Auto-saves uncommitted changes.
    """
    paths = require_project(root)
    root = paths.root

    tree = get_lineage_tree(root)
    target = _resolve_version(version_query, tree["nodes"])

    # Auto-save if dirty.
    if git.has_uncommitted_changes(root):
        auto_commit(root, subject="Auto-save before switching version")

    # Find the branch for this version.
    target_branch = _branch_for_version(target, tree)
    git.checkout(root, target_branch)
    return target


# ---------------------------------------------------------------------------
# Get lineage tree
# ---------------------------------------------------------------------------


def _global_annotation_counts_for_branch(
    root: Path,
    branch: str,
) -> dict[str, int]:
    """Read annotation files from *branch* via ``git show`` and count
    project-level annotations (entries where ``target_id`` is None).

    Returns e.g. ``{"evidence": 2, "assumption": 1}``.
    Only counts project-level (global) annotations, not per-element ones.
    """
    # (relative_path, model_class, entries_attr, annotation_key)
    _SOURCES: list[tuple[str, type, str]] = [
        ("substrate/attributes/evidence-links.yaml", EvidenceLinkSet, "evidence"),
        ("ai/challenges.yaml", ChallengeLog, "challenge"),
        ("provenance/assumptions.yaml", AssumptionLog, "assumption"),
        ("provenance/decisions.yaml", DecisionLog, "decision"),
        ("provenance/questions.yaml", QuestionLog, "question"),
        ("provenance/signoffs.yaml", SignoffLog, "signoff"),
    ]

    counts: dict[str, int] = {}
    for rel_path, model_cls, key in _SOURCES:
        try:
            text = git.show_file(root, branch, rel_path)
        except git.GitError:
            continue
        try:
            model = load_model_from_string(model_cls, text)
        except Exception:
            continue
        n = sum(1 for e in model.entries if getattr(e, "target_id", None) is None)
        if n > 0:
            counts[key] = n

    return counts


def get_lineage_tree(root: Path | None = None, *, include_archived: bool = False) -> dict[str, Any]:
    """Reconstruct the full lineage tree from per-branch metadata.

    Returns a dict with ``nodes``, ``edges`` (derived from git
    topology), ``milestones``, ``current_version_id``,
    ``preferred_version_id``, ``current_branch``, and ``annotations``.

    Versions retired by a Reconcile decision (``archived``) are hidden unless
    *include_archived* is set (the GUI "show archived" toggle).
    """
    paths = require_project(root)
    root = paths.root

    current = git.current_branch(root)
    index = build_lineage_index(root)
    nodes: list[LineageNode] = list(index.nodes.values())

    # Synthesise a root node for pre-lineage projects that have no
    # lineage-node.yaml on main yet.
    if "main" not in index.nodes:
        synth = _synthesise_root(root)
        if synth is not None:
            nodes.insert(0, synth)
            index.branch_for_node[synth.id] = "main"

    # Hide archived (superseded) versions unless explicitly requested.
    if not include_archived:
        nodes = [n for n in nodes if not getattr(n, "archived", False)]
    kept_ids = {n.id for n in nodes}

    # Milestones for the current branch (from working tree, not git show).
    milestones: dict[str, list[dict[str, Any]]] = {}
    if paths.milestones_yaml.exists():
        log = load_model(MilestoneLog, paths.milestones_yaml)
        current_id = _current_version_id(nodes, current)
        if current_id:
            milestones[current_id] = [m.model_dump(mode="json") for m in log.entries]

    current_id = _current_version_id(nodes, current)
    preferred_id = _read_preferred(paths, nodes)

    # Per-version project-level annotation counts (cross-branch reads).
    annotations: dict[str, dict[str, int]] = {}
    for node in nodes:
        branch = index.branch_for_node.get(node.id)
        if branch:
            counts = _global_annotation_counts_for_branch(root, branch)
            if counts:
                annotations[node.id] = counts

    # Per-version sync state (local-only computation, no network). Read from the
    # last fetch; the GUI calls sync/refresh to update remote-tracking refs.
    sync_info = _sync_info(root)

    return {
        "nodes": [n.model_dump(mode="json") for n in nodes],
        "edges": [
            {"source": parent_id, "target": child_id}
            for parent_id, child_id in index.edges
            if parent_id in kept_ids and child_id in kept_ids
        ],
        "milestones": milestones,
        "current_version_id": current_id,
        "preferred_version_id": preferred_id,
        "current_branch": current,
        "annotations": annotations,
        "sync_state": sync_info["sync_state"],
        "ghosts": sync_info["ghosts"],
        "shared": sync_info["shared"],
    }


def _sync_info(root: Path) -> dict[str, Any]:
    """Per-version sync state, tolerant of a missing/offline sync layer.

    Function-local import: ``operations.sync`` and ``operations.lineage`` are
    the same layer and reference each other, so the import is deferred to call
    time to avoid a module-load cycle.
    """
    try:
        from latris.operations import sync

        return sync.version_sync_states(root=root)
    except Exception:
        # Tree loading must never fail because of sync state. Degrade to empty.
        return {"sync_state": {}, "ghosts": [], "shared": False}


def nodes_and_branches(root: Path) -> tuple[list[LineageNode], dict[str, str]]:
    """All version nodes + their ``version_id -> branch`` map.

    Includes the synthesised root for pre-lineage projects (mapped to ``main``).
    Shared by :func:`get_lineage_tree` and the sync layer so both agree on the
    set of versions and their branches.
    """
    index = build_lineage_index(root)
    nodes: list[LineageNode] = list(index.nodes.values())
    branch_for_node: dict[str, str] = dict(index.branch_for_node)
    if "main" not in index.nodes:
        synth = _synthesise_root(root)
        if synth is not None and synth.id not in branch_for_node:
            nodes.insert(0, synth)
            branch_for_node[synth.id] = "main"
    return nodes, branch_for_node


# ---------------------------------------------------------------------------
# Update version metadata
# ---------------------------------------------------------------------------


def update_version(
    *,
    name: str | None = None,
    maturity: Maturity | None = None,
    notes: str | None = None,
    root: Path | None = None,
) -> tuple[LineageNode, str]:
    """Update the current version's name, maturity, or notes."""
    paths = require_project(root)
    root = paths.root
    node = ensure_root_lineage(root)

    dirty = False
    if name is not None and name != node.name:
        node.name = name
        dirty = True
    if maturity is not None and maturity != node.maturity:
        node.maturity = maturity
        dirty = True
    if notes is not None and notes != node.notes:
        node.notes = notes
        dirty = True

    if not dirty:
        return node, ""

    dump_model(node, paths.lineage_node_yaml)
    sha = auto_commit(
        root,
        subject=f"Updated version: {node.name}",
        paths=[paths.lineage_node_yaml],
    )
    return node, sha


# ---------------------------------------------------------------------------
# Preferred version
# ---------------------------------------------------------------------------


def set_preferred(
    version_query: str,
    *,
    root: Path | None = None,
) -> tuple[str, str]:
    """Tag a version as the preferred (canonical) model.

    Only one version can be preferred at a time. The original version is
    implicitly preferred until explicitly changed.

    Returns ``(version_id, commit_sha)``.
    """
    paths = require_project(root)
    root = paths.root

    tree = get_lineage_tree(root)
    target = _resolve_version(version_query, tree["nodes"])
    target_id = target["id"] if isinstance(target, dict) else target.id

    # Write the preferred version ID to a small file.
    paths.preferred_version_file.write_text(
        target_id + "\n",
        encoding="utf-8",
        newline="",
    )
    sha = auto_commit(
        root,
        subject=f"Set preferred version: {target_id}",
        paths=[paths.preferred_version_file],
    )
    return target_id, sha


def _read_preferred(paths, nodes: list) -> str | None:
    """Read the preferred version ID, or fall back to the original."""
    if paths.preferred_version_file.exists():
        text = paths.preferred_version_file.read_text(encoding="utf-8").strip()
        if text:
            return text
    # Fall back: original version is implicitly preferred.
    for n in nodes:
        rel = n["relationship"] if isinstance(n, dict) else n.relationship
        if rel == "original":
            nid = n["id"] if isinstance(n, dict) else n.id
            return nid
    return None


# ---------------------------------------------------------------------------
# Compare versions
# ---------------------------------------------------------------------------


def compare_versions(
    version_a: str,
    version_b: str,
    *,
    root: Path | None = None,
) -> list[dict[str, Any]]:
    """Semantic diff between two versions.

    Returns a list of ``SemanticEvent`` dicts.
    """
    from latris.diff.semantic import diff_commits

    paths = require_project(root)
    root = paths.root

    tree = get_lineage_tree(root)
    node_a = _resolve_version(version_a, tree["nodes"])
    node_b = _resolve_version(version_b, tree["nodes"])

    branch_a = _branch_for_version(node_a, tree)
    branch_b = _branch_for_version(node_b, tree)

    # Get HEAD SHAs for each branch.
    sha_a = git.run_git(["rev-parse", branch_a], cwd=root).stdout.strip()
    sha_b = git.run_git(["rev-parse", branch_b], cwd=root).stdout.strip()

    events = diff_commits(root, sha_a, sha_b)
    return [e.__dict__ if hasattr(e, "__dict__") else e for e in events]


# ---------------------------------------------------------------------------
# Reconcile (resolve a diverged version: keep one line, archive the other)
# ---------------------------------------------------------------------------


def reconcile_preview(
    version_query: str,
    *,
    remote: str = "origin",
    root: Path | None = None,
) -> list[dict[str, Any]]:
    """Diff a diverged version's local line against the shared copy.

    Returns ``SemanticEvent`` dicts describing what changed on the shared side
    (``origin/<branch>``) relative to your local line — the data behind the
    side-by-side Reconcile view.
    """
    from latris.diff.semantic import diff_commits

    paths = require_project(root)
    root = paths.root
    tree = get_lineage_tree(root)
    node = _resolve_version(version_query, tree["nodes"])
    branch = _branch_for_version(node, tree)
    local_sha = git.run_git(["rev-parse", branch], cwd=root).stdout.strip()
    remote_sha = git.run_git(["rev-parse", f"{remote}/{branch}"], cwd=root).stdout.strip()
    events = diff_commits(root, local_sha, remote_sha)
    return [e.__dict__ if hasattr(e, "__dict__") else e for e in events]


def reconcile(
    version_query: str,
    keep: str,
    *,
    remote: str = "origin",
    env: dict[str, str] | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    """Resolve a diverged version by keeping one line and archiving the other.

    ``keep="mine"`` keeps your local line and publishes it; ``keep="theirs"``
    adopts the shared copy. **Nothing is deleted** — the losing line is first
    snapshotted onto a retained ``archived`` branch (a new version that records
    which version superseded it).
    """
    if keep not in ("mine", "theirs"):
        raise ValueError(f"keep must be 'mine' or 'theirs', got {keep!r}")

    paths = require_project(root)
    root = paths.root

    tree = get_lineage_tree(root)
    node = _resolve_version(version_query, tree["nodes"])
    version_id = node["id"] if isinstance(node, dict) else node.id
    name = node["name"] if isinstance(node, dict) else node.name
    branch = _branch_for_version(node, tree)
    remote_ref = f"{remote}/{branch}"

    if git.run_git(["rev-parse", "--verify", remote_ref], cwd=root, check=False).returncode != 0:
        raise ResolveError(f"version '{name}' has no shared copy to reconcile against")

    # Operate on the contested branch; auto-save and switch to it if needed.
    original_branch = git.current_branch(root)
    if git.has_uncommitted_changes(root):
        auto_commit(root, subject="Auto-save before reconcile")
    if original_branch != branch:
        git.checkout(root, branch)

    # 1) Snapshot the losing line onto a retained, archived branch (new id).
    loser_start = remote_ref if keep == "mine" else "HEAD"
    archived_id = new_id("version")
    _, ulid_part = parse_id(archived_id)
    archived_branch = f"lineage/{ulid_part}"
    git.create_branch(root, archived_branch, start=loser_start)
    git.checkout(root, archived_branch)
    # Label this branch's state as a retained, archived version. Built from the
    # contested version's metadata (the loser line may be a synthesised root
    # with no committed lineage-node.yaml of its own).
    created_by = node["created_by"] if isinstance(node, dict) else node.created_by.model_dump()
    maturity = node["maturity"] if isinstance(node, dict) else node.maturity
    arch_node = LineageNode(
        id=archived_id,
        name=f"{name} (archived)",
        maturity=maturity,
        relationship="alternative",
        created_by=HumanActor(**created_by) if isinstance(created_by, dict) else created_by,
        archived=True,
        superseded_by=version_id,
    )
    dump_model(arch_node, paths.lineage_node_yaml)
    auto_commit(
        root,
        subject=f"Archived superseded version: {arch_node.name}",
        paths=[paths.lineage_node_yaml],
    )
    git.checkout(root, branch)

    # 2) Make the winner the shared truth.
    if keep == "mine":
        git.merge_ours(root, remote_ref)  # record theirs as ancestor (no file change)
        git.push(root, remote, branch, set_upstream=True, env=env)  # fast-forward publish
    else:  # keep == "theirs" — your line is preserved on the archived branch
        git.reset_hard(root, remote_ref)
    head = git.head_sha(root)

    # 3) Restore the branch the user was on, if we moved off it and it survives.
    if original_branch != branch and original_branch in git.list_branches(root):
        git.checkout(root, original_branch)

    return {
        "version_id": version_id,
        "branch": branch,
        "head": head,
        "keep": keep,
        "archived_version_id": archived_id,
        "archived_branch": archived_branch,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_lineage_node_compat(path: Path) -> LineageNode:
    """Load a LineageNode from a YAML file."""
    return load_model(LineageNode, path)


def _synthesise_root(root: Path) -> LineageNode | None:
    """Synthesise a root node from project.yaml for pre-lineage projects."""
    from latris.repo.layout import ProjectPaths

    paths = ProjectPaths(root)
    if not paths.project_yaml.exists():
        return None

    foundation = load_model(ProjectFoundation, paths.project_yaml)
    return LineageNode(
        id="version_ROOT",
        name=foundation.name or foundation.statement[:60],
        relationship="original",
        created_by=HumanActor(name="(project creator)"),
    )


def _current_version_id(nodes: list[LineageNode], branch: str) -> str | None:
    """Find the version ID for a given branch name."""
    if branch == "main":
        for n in nodes:
            if n.relationship == "original":
                return n.id
        return None
    # lineage/<ulid> -> version_<ulid>
    ulid_part = branch.removeprefix("lineage/")
    for n in nodes:
        if n.id.endswith(ulid_part):
            return n.id
    return None


def _branch_for_version(
    node: LineageNode | dict[str, Any],
    tree: dict[str, Any],
) -> str:
    """Determine the git branch for a version node."""
    node_id = node["id"] if isinstance(node, dict) else node.id
    relationship = node["relationship"] if isinstance(node, dict) else node.relationship

    if relationship == "original":
        return "main"
    # version_<ulid> -> lineage/<ulid>
    _, ulid_part = parse_id(node_id)
    return f"lineage/{ulid_part}"


def _resolve_version(
    query: str,
    nodes: list[LineageNode | dict[str, Any]],
) -> LineageNode | dict[str, Any]:
    """Resolve a version by ID prefix or exact name."""

    # Normalise: nodes may be dicts (from get_lineage_tree) or LineageNode objects.
    def _get(n: LineageNode | dict, key: str) -> Any:
        return n[key] if isinstance(n, dict) else getattr(n, key)

    # Try branch name shorthand: "main" → root node, "lineage/<ulid>" → matching node.
    if query == "main":
        roots = [n for n in nodes if _get(n, "relationship") == "original"]
        if len(roots) == 1:
            return roots[0]
    elif query.startswith("lineage/"):
        ulid_part = query.removeprefix("lineage/")
        by_branch = [n for n in nodes if _get(n, "id").endswith(ulid_part)]
        if len(by_branch) == 1:
            return by_branch[0]

    # Try exact ID match.
    exact = [n for n in nodes if _get(n, "id") == query]
    if len(exact) == 1:
        return exact[0]

    # Try ID prefix match.
    prefix = [n for n in nodes if _get(n, "id").startswith(query)]
    if len(prefix) == 1:
        return prefix[0]
    if len(prefix) > 1:
        names = [_get(n, "name") for n in prefix]
        raise ResolveError(f"Ambiguous version prefix {query!r}: matches {names}")

    # Try exact name match (case-insensitive).
    q_lower = query.lower()
    by_name = [n for n in nodes if _get(n, "name").lower() == q_lower]
    if len(by_name) == 1:
        return by_name[0]
    if len(by_name) > 1:
        ids = [_get(n, "id") for n in by_name]
        raise ResolveError(f"Multiple versions named {query!r}: {ids}. Use the version ID to disambiguate.")

    raise ResolveError(f"No version found matching {query!r}")


def _resolve_milestone(query: str, root: Path) -> Milestone:
    """Resolve a milestone by ID prefix or exact name on the current branch."""
    from latris.repo.layout import ProjectPaths

    paths = ProjectPaths(root)
    if not paths.milestones_yaml.exists():
        raise ResolveError("No milestones on this version")

    log = load_model(MilestoneLog, paths.milestones_yaml)
    if not log.entries:
        raise ResolveError("No milestones on this version")

    # Try exact ID.
    exact = [m for m in log.entries if m.id == query]
    if len(exact) == 1:
        return exact[0]

    # Try ID prefix.
    prefix = [m for m in log.entries if m.id.startswith(query)]
    if len(prefix) == 1:
        return prefix[0]
    if len(prefix) > 1:
        raise ResolveError(f"Ambiguous milestone prefix {query!r}")

    # Try name.
    q_lower = query.lower()
    by_name = [m for m in log.entries if m.name.lower() == q_lower]
    if len(by_name) == 1:
        return by_name[0]
    if len(by_name) > 1:
        raise ResolveError(f"Multiple milestones named {query!r}")

    raise ResolveError(f"No milestone found matching {query!r}")
