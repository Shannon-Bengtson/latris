from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import attributes as attr_ops
from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations.batch import batch
from latris.operations.init import init_project
from latris.repo import git


@pytest.fixture
def project(tmp_path: Path, git_identity):
    root = tmp_path / "demo"
    init_project(root, statement="Q?")
    return root


def _commit_count(root: Path) -> int:
    return int(git.run_git(["rev-list", "--count", "HEAD"], cwd=root).stdout.strip())


def test_batch_groups_two_adds_into_one_commit(project: Path) -> None:
    before = _commit_count(project)
    with batch(project, subject="Add Price and Demand"):
        node_ops.add_node("Price", root=project)
        node_ops.add_node("Demand", root=project)
    after = _commit_count(project)
    assert after == before + 1  # exactly one commit for two operations

    # Both nodes exist
    labels = sorted(e.label for e in node_ops.list_nodes(project))
    assert labels == ["Demand", "Price"]


def test_batch_with_node_and_edge(project: Path) -> None:
    node_ops.add_node("Existing", root=project)
    before = _commit_count(project)
    with batch(project, subject="Add node and connect"):
        b, _ = node_ops.add_node("New", root=project)
        edge_ops.add_edge("Existing", b.id, root=project)
    after = _commit_count(project)
    assert after == before + 1
    assert len(edge_ops.list_edges(project)) == 1


def test_batch_exception_rolls_back(project: Path) -> None:
    before = _commit_count(project)
    node_ops.add_node("Before", root=project)
    before = _commit_count(project)

    with pytest.raises(ValueError, match="deliberate"), batch(project, subject="Should not land"):
        node_ops.add_node("Ghost", root=project)
        raise ValueError("deliberate error")

    after = _commit_count(project)
    assert after == before  # no new commit

    # "Ghost" node should NOT be persisted (working tree reverted)
    labels = [e.label for e in node_ops.list_nodes(project)]
    assert "Ghost" not in labels


def test_nested_batch_raises(project: Path) -> None:
    with (
        batch(project, subject="Outer"),
        pytest.raises(RuntimeError, match="Nested batch"),
        batch(project, subject="Inner"),
    ):  # noqa: SIM117
        pass  # pragma: no cover


def test_non_batched_operations_still_auto_commit(project: Path) -> None:
    """Backward compat: operations outside a batch behave as before."""
    before = _commit_count(project)
    entity, sha = node_ops.add_node("Solo", root=project)
    assert _commit_count(project) == before + 1
    assert len(sha) == 40
    assert entity.label == "Solo"


def test_batch_returns_empty_sha_during_batch(project: Path) -> None:
    """Inside a batch, auto_commit returns empty string (no commit yet)."""
    shas: list[str] = []
    with batch(project, subject="Batch check"):
        _, sha1 = node_ops.add_node("A", root=project)
        _, sha2 = node_ops.add_node("B", root=project)
        shas.extend([sha1, sha2])
    assert all(s == "" for s in shas)


def test_batch_commit_message_uses_batch_subject(project: Path) -> None:
    with batch(project, subject="Combined: add two nodes"):
        node_ops.add_node("X", root=project)
        node_ops.add_node("Y", root=project)

    # Check the last commit message
    msg = git.run_git(["log", "-1", "--format=%s"], cwd=project).stdout.strip()
    assert msg == "Combined: add two nodes"


def test_batch_provenance_trailer(project: Path) -> None:
    with batch(project, subject="AI batch", provenance="ai-proposed"):
        node_ops.add_node("Z", root=project)

    body = git.run_git(["log", "-1", "--format=%B"], cwd=project).stdout
    assert "Provenance: ai-proposed" in body


# ── T15: Batch edge cases ────────────────────────────────────────────


def test_batch_empty_no_commit(project: Path) -> None:
    """An empty batch (no operations) should not create a commit."""
    before = _commit_count(project)
    with batch(project, subject="Empty batch"):
        pass  # no operations
    assert _commit_count(project) == before


def test_batch_with_set_attribute(project: Path) -> None:
    """Attribute operations inside a batch produce one commit."""
    a, _ = node_ops.add_node("Price", root=project)
    before = _commit_count(project)
    with batch(project, subject="Set two attributes"):
        attr_ops.set_attribute(a.id, "description", "Retail price", root=project)
        attr_ops.set_attribute(a.id, "confidence", "high", root=project)
    assert _commit_count(project) == before + 1


def test_batch_mid_failure_rolls_back_all(project: Path) -> None:
    """If the second operation fails, the first should also be rolled back."""
    a, _ = node_ops.add_node("Existing", root=project)
    before = _commit_count(project)
    with pytest.raises(ValueError), batch(project, subject="Should fail"):
        node_ops.add_node("NewNode", root=project)
        # Try to add edge to nonexistent node — raises ResolveError (subclass of ValueError)
        edge_ops.add_edge(a.id, "node_DOESNOTEXIST12345678ABCDE", root=project)

    assert _commit_count(project) == before
    labels = [e.label for e in node_ops.list_nodes(project)]
    assert "NewNode" not in labels  # rolled back
