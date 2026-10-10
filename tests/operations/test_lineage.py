"""Integration tests for lineage operations.

Covers the full branch lifecycle: init → milestone → alternative → switch → tree.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations._resolve import ResolveError
from latris.operations.init import init_project
from latris.operations.lineage import (
    compare_versions,
    create_alternative,
    create_milestone,
    ensure_root_lineage,
    get_lineage_tree,
    restore_milestone,
    switch_version,
    update_version,
)
from latris.repo import git
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model
from latris.schema import LineageNode, MilestoneLog


@pytest.fixture
def project(tmp_path: Path, git_identity: tuple[str, str]) -> Path:
    root = tmp_path / "proj"
    init_project(root, statement="Does price affect demand?")
    return root


# -- ensure_root_lineage --


def test_ensure_root_lineage_creates_on_fresh_project(project: Path) -> None:
    node = ensure_root_lineage(project)
    assert node.relationship == "original"
    assert node.id.startswith("version_")
    assert ProjectPaths(project).lineage_node_yaml.exists()


def test_ensure_root_lineage_is_idempotent(project: Path) -> None:
    node1 = ensure_root_lineage(project)
    node2 = ensure_root_lineage(project)
    assert node1.id == node2.id
    assert node1.name == node2.name


# -- create_milestone --


def test_create_milestone(project: Path) -> None:
    milestone, sha = create_milestone("Draft 1", root=project)
    assert milestone.name == "Draft 1"
    assert milestone.maturity == "proposed"
    assert len(milestone.commit_sha) == 40
    assert len(sha) == 40

    # Verify persisted.
    paths = ProjectPaths(project)
    log = load_model(MilestoneLog, paths.milestones_yaml)
    assert len(log.entries) == 1
    assert log.entries[0].id == milestone.id


def test_create_milestone_approved(project: Path) -> None:
    milestone, _ = create_milestone("v1 approved", maturity="approved", root=project)
    assert milestone.maturity == "approved"


def test_create_multiple_milestones(project: Path) -> None:
    create_milestone("M1", root=project)
    create_milestone("M2", root=project)
    create_milestone("M3", root=project)

    paths = ProjectPaths(project)
    log = load_model(MilestoneLog, paths.milestones_yaml)
    assert len(log.entries) == 3


# -- create_alternative --


def test_create_alternative(project: Path) -> None:
    node, branch = create_alternative("What-if: no feedback", root=project)

    assert node.name == "What-if: no feedback"
    assert node.relationship == "alternative"
    assert branch.startswith("lineage/")

    # Should be on the new branch now.
    assert git.current_branch(project) == branch

    # Lineage metadata should exist on the new branch.
    paths = ProjectPaths(project)
    assert paths.lineage_node_yaml.exists()
    loaded = load_model(LineageNode, paths.lineage_node_yaml)
    assert loaded.id == node.id


def test_create_alternative_from_milestone(project: Path) -> None:
    # Add content, then milestone, then more content.
    from latris.operations.nodes import add_node

    add_node("Price", root=project)
    milestone, _ = create_milestone("Before workshop", root=project)
    add_node("Demand", root=project)

    # Create alternative from the milestone (before "Demand" was added).
    node, branch = create_alternative(
        "Alt from milestone",
        from_milestone=milestone.id,
        root=project,
    )

    assert node.relationship == "alternative"
    assert git.current_branch(project) == branch

    # "Demand" node should not exist on this branch.
    from latris.schema import Substrate

    sub = load_model(Substrate, ProjectPaths(project).conceptual_yaml)
    labels = [e.label for e in sub.entities]
    assert "Demand" not in labels
    assert "Price" in labels


# -- restore_milestone --


def test_restore_milestone(project: Path) -> None:
    create_milestone("Snapshot", root=project)
    node, branch = restore_milestone("Snapshot", "Restored from snapshot", root=project)

    assert node.relationship == "alternative"
    assert node.name == "Restored from snapshot"
    assert git.current_branch(project) == branch


# -- switch_version --


def test_switch_version(project: Path) -> None:
    # Create an alternative.
    alt_node, alt_branch = create_alternative("Alt version", root=project)
    assert git.current_branch(project) == alt_branch

    # Switch back to root via "main" shorthand.
    switch_version("main", root=project)
    assert git.current_branch(project) == "main"

    # Switch to alternative by name.
    switched = switch_version("Alt version", root=project)
    switched_id = switched["id"] if isinstance(switched, dict) else switched.id
    assert switched_id == alt_node.id
    assert git.current_branch(project) == alt_branch


def test_switch_auto_commits_dirty_state(project: Path) -> None:
    create_alternative("Alt", root=project)
    alt_branch = git.current_branch(project)

    # Make the working tree dirty.
    paths = ProjectPaths(project)
    (paths.root / "scratch.txt").write_text("temp\n", encoding="utf-8", newline="")
    git.add(project, [paths.root / "scratch.txt"])
    assert git.has_uncommitted_changes(project) is True

    # Switch should auto-commit.
    switch_version("main", root=project)
    assert git.current_branch(project) == "main"

    # Switch back — the file should still exist (it was committed).
    git.checkout(project, alt_branch)
    assert (paths.root / "scratch.txt").exists()


# -- get_lineage_tree --


def test_get_lineage_tree_fresh_project(project: Path) -> None:
    """A project with no lineage operations synthesises a root node."""
    tree = get_lineage_tree(project)
    assert len(tree["nodes"]) == 1
    assert tree["nodes"][0]["relationship"] == "original"
    assert tree["current_branch"] == "main"


def test_get_lineage_tree_with_alternatives(project: Path) -> None:
    ensure_root_lineage(project)
    create_milestone("M1", root=project)

    # Create two alternatives.
    alt1, _ = create_alternative("Alt A", root=project)
    git.checkout(project, "main")  # go back to create second alt from main
    alt2, _ = create_alternative("Alt B", root=project)

    tree = get_lineage_tree(project)
    assert len(tree["nodes"]) == 3  # root + Alt A + Alt B
    names = sorted(n["name"] for n in tree["nodes"])
    assert "Alt A" in names
    assert "Alt B" in names


# -- pre-lineage compatibility --


def test_pre_lineage_compatibility(project: Path) -> None:
    """A project created without lineage ops still produces a tree."""
    tree = get_lineage_tree(project)
    assert len(tree["nodes"]) == 1
    root_node = tree["nodes"][0]
    assert root_node["relationship"] == "original"
    # The synthesised root uses a sentinel ID.
    assert root_node["id"] == "version_ROOT"


# -- update_version --


def test_update_version_name(project: Path) -> None:
    ensure_root_lineage(project)
    node, sha = update_version(name="Renamed version", root=project)
    assert node.name == "Renamed version"
    assert len(sha) == 40


def test_update_version_status(project: Path) -> None:
    ensure_root_lineage(project)
    node, sha = update_version(maturity="approved", root=project)
    assert node.maturity == "approved"


def test_update_version_no_change(project: Path) -> None:
    ensure_root_lineage(project)
    node, sha = update_version(root=project)
    assert sha == ""  # no commit needed


# -- name resolution --


def test_version_name_resolution_ambiguous(project: Path) -> None:
    ensure_root_lineage(project)
    create_alternative("Same Name", root=project)
    git.checkout(project, "main")
    create_alternative("Same Name", root=project)

    get_lineage_tree(project)
    with pytest.raises(ResolveError, match="Multiple versions"):
        switch_version("Same Name", root=project)


def test_version_not_found(project: Path) -> None:
    ensure_root_lineage(project)
    with pytest.raises(ResolveError, match="No version found"):
        switch_version("nonexistent", root=project)


# -- compare_versions --


def test_compare_versions(project: Path) -> None:
    from latris.operations.nodes import add_node

    ensure_root_lineage(project)
    add_node("Price", root=project)
    create_milestone("With Price", root=project)

    alt, _ = create_alternative("Alt", root=project)
    add_node("Supply", root=project)

    events = compare_versions("main", alt.id, root=project)
    # Should detect at least the added node.
    assert len(events) > 0


# -- set_preferred / _read_preferred --


def test_set_preferred(project: Path) -> None:
    from latris.operations.lineage import set_preferred

    ensure_root_lineage(project)
    tree = get_lineage_tree(project)
    root_id = tree["nodes"][0]["id"]

    # Before explicitly setting, the original is implicitly preferred.
    assert tree["preferred_version_id"] == root_id

    # Create an alternative and set it as preferred.
    alt, _ = create_alternative("Alt", root=project)
    version_id, sha = set_preferred(alt.id, root=project)
    assert version_id == alt.id
    assert len(sha) == 40

    tree = get_lineage_tree(project)
    assert tree["preferred_version_id"] == alt.id


def test_set_preferred_back_to_original(project: Path) -> None:
    from latris.operations.lineage import set_preferred

    ensure_root_lineage(project)
    root_id = get_lineage_tree(project)["nodes"][0]["id"]

    create_alternative("Alt", root=project)
    set_preferred("Alt", root=project)

    # Switch back and set original as preferred
    switch_version("main", root=project)
    set_preferred("main", root=project)

    tree = get_lineage_tree(project)
    assert tree["preferred_version_id"] == root_id


# -- milestone resolution edge cases --


def test_resolve_milestone_by_name(project: Path) -> None:
    """Milestones can be resolved by name."""
    ms, _ = create_milestone("Draft 1", root=project)
    # Create alternative from milestone by name (not ID).
    alt, _ = create_alternative("From Draft", from_milestone="Draft 1", root=project)
    assert alt.relationship == "alternative"


def test_resolve_milestone_not_found(project: Path) -> None:
    ensure_root_lineage(project)
    with pytest.raises(ResolveError, match="No milestones"):
        restore_milestone("nonexistent", "Restored", root=project)


# -- update_version with notes --


def test_update_version_notes(project: Path) -> None:
    ensure_root_lineage(project)
    node, sha = update_version(notes="Added after workshop", root=project)
    assert node.notes == "Added after workshop"
    assert len(sha) == 40

    # Verify persisted
    loaded = load_model(LineageNode, ProjectPaths(project).lineage_node_yaml)
    assert loaded.notes == "Added after workshop"


# -- lineage tree milestones --


def test_lineage_tree_includes_milestones(project: Path) -> None:
    ensure_root_lineage(project)
    create_milestone("M1", root=project)
    create_milestone("M2", root=project)

    tree = get_lineage_tree(project)
    root_id = tree["current_version_id"]
    assert root_id in tree["milestones"]
    assert len(tree["milestones"][root_id]) == 2
    names = [m["name"] for m in tree["milestones"][root_id]]
    assert "M1" in names
    assert "M2" in names
