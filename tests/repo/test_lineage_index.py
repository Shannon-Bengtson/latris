"""The lineage index reads each branch's lineage node; one it can't read is skipped, not fatal."""

from __future__ import annotations

from latris.repo import git, lineage_index


def test_an_unreadable_lineage_node_is_skipped(tmp_path, git_identity, monkeypatch):
    monkeypatch.setattr(git, "show_file", lambda root, branch, path: "id: [unclosed")
    assert lineage_index._load_node_at_branch(tmp_path, "main") is None
    monkeypatch.setattr(git, "show_file", lambda root, branch, path: "just: a mapping\n")
    assert lineage_index._load_node_at_branch(tmp_path, "main") is None  # not a lineage node

    def missing(root, branch, path):
        raise git.GitError("no such path")

    monkeypatch.setattr(git, "show_file", missing)
    assert lineage_index._load_node_at_branch(tmp_path, "main") is None


# ── The fallback when a version's creation commit can't be found ─────────────
#
# ``_fork_point`` finds the commit a version was made from by searching for its id. When that
# search finds nothing (``None``), the index falls back to ``_derive_parent_branch``: the other
# branch it split from most recently.

import pytest  # noqa: E402

from latris.operations.init import init_project  # noqa: E402
from latris.operations.lineage import (  # noqa: E402
    create_alternative,
    create_milestone,
    ensure_root_lineage,
    switch_version,
    update_version,
)


@pytest.fixture
def project(tmp_path, git_identity):
    root = tmp_path / "proj"
    init_project(root, statement="Does price affect demand?")
    ensure_root_lineage(root)
    update_version(name="Original", root=root)
    return root


def _named_edges(index) -> set[tuple[str, str]]:
    name = {n.id: n.name for n in index.nodes.values()}
    return {(name[p], name[c]) for p, c in index.edges}


def _branch_named(index, name: str) -> str:
    return next(b for b, n in index.nodes.items() if n.name == name)


def test_without_a_fork_point_an_alternative_still_hangs_from_the_original(project, monkeypatch):
    create_alternative("Alt A", root=project)
    monkeypatch.setattr(lineage_index, "_fork_point", lambda root, branch, version_id: None)

    index = lineage_index.build_lineage_index(project)
    assert _named_edges(index) == {("Original", "Alt A")}
    assert set(index.branch_for_node.values()) == set(index.nodes)


def test_the_fallback_finds_an_alternative_made_from_an_alternative(project):
    create_alternative("Alt A", root=project)
    create_milestone("On A", root=project)
    create_alternative("Alt A2", root=project)
    index = lineage_index.build_lineage_index(project)
    branches = list(index.nodes)

    a, a2 = _branch_named(index, "Alt A"), _branch_named(index, "Alt A2")
    assert lineage_index._derive_parent_branch(project, a2, branches) == a


def test_the_fallback_gives_siblings_and_grandchildren_their_own_parents(project, monkeypatch):
    # Original -> A -> A2, and Original -> B. The old rule made B a child of A (any branch reaching
    # the fork commit won over main) and left A with no parent (A2 contains all of A).
    create_alternative("Alt A", root=project)
    create_milestone("On A", root=project)
    create_alternative("Alt A2", root=project)
    switch_version("Original", root=project)
    create_alternative("Alt B", root=project)
    monkeypatch.setattr(lineage_index, "_fork_point", lambda root, branch, version_id: None)

    index = lineage_index.build_lineage_index(project)
    assert _named_edges(index) == {("Original", "Alt A"), ("Alt A", "Alt A2"), ("Original", "Alt B")}


def test_the_fallback_gives_up_without_other_versions(project):
    assert lineage_index._derive_parent_branch(project, "main", ["main"]) is None


def test_the_fallback_hangs_a_branch_with_no_commits_of_its_own_from_where_it_points(project):
    # A lineage branch pointing at main's tip was made from main.
    git.create_branch(project, "lineage/bare")
    assert lineage_index._derive_parent_branch(project, "lineage/bare", ["main", "lineage/bare"]) == "main"


def test_the_fallback_gives_up_on_a_root_commit(tmp_path, git_identity):
    # A branch whose only unique commit has no parent (an orphan history) has no parent version.
    root = tmp_path / "proj"
    init_project(root, statement="Q?")
    git.run_git(["checkout", "--orphan", "lineage/orphan"], cwd=root)
    git.run_git(["commit", "--allow-empty", "-m", "orphan"], cwd=root)
    assert lineage_index._derive_parent_branch(root, "lineage/orphan", ["main", "lineage/orphan"]) is None


def test_the_fork_point_is_the_parent_of_the_commit_that_wrote_the_id(tmp_path, git_identity):
    root = tmp_path / "proj"
    init_project(root, statement="Q?")
    node = ensure_root_lineage(root)
    # The id was first written in a commit that has a parent: the fork point is that parent.
    assert lineage_index._fork_point(root, "main", node.id) == git.run_git(
        ["rev-parse", "HEAD~1"], cwd=root
    ).stdout.strip()
    assert lineage_index._fork_point(root, "main", "version_never_written") is None
