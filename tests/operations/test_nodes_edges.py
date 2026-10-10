from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations._resolve import ResolveError
from latris.operations.init import init_project
from latris.repo import git


@pytest.fixture
def project(tmp_path: Path, git_identity):
    root = tmp_path / "demo"
    init_project(root, statement="Q?")
    return root


def _commit_count(root: Path) -> int:
    return int(git.run_git(["rev-list", "--count", "HEAD"], cwd=root).stdout.strip())


def test_add_node_creates_commit(project: Path) -> None:
    before = _commit_count(project)
    entity, sha = node_ops.add_node("Price", kind="variable", root=project)
    assert entity.label == "Price"
    assert entity.kind == "variable"
    assert entity.id.startswith("node_")
    assert _commit_count(project) == before + 1
    assert len(sha) == 40


def test_list_nodes(project: Path) -> None:
    assert node_ops.list_nodes(project) == []
    node_ops.add_node("Price", root=project)
    node_ops.add_node("Demand", root=project)
    labels = [e.label for e in node_ops.list_nodes(project)]
    assert labels == ["Price", "Demand"]


def test_get_node_by_label_and_prefix(project: Path) -> None:
    price, _ = node_ops.add_node("Price", root=project)
    node_ops.add_node("Demand", root=project)

    assert node_ops.get_node("Price", project).id == price.id
    assert node_ops.get_node(price.id, project).id == price.id

    # A long enough prefix is unique (ULIDs share a timestamp prefix when
    # generated in the same millisecond, so we take most of the random part).
    prefix = price.id[:24]
    assert node_ops.get_node(prefix, project).id == price.id


def test_rename_node(project: Path) -> None:
    entity, _ = node_ops.add_node("Price", root=project)
    renamed, _ = node_ops.rename_node(entity.id, "Retail price", root=project)
    assert renamed.id == entity.id
    assert renamed.label == "Retail price"
    assert node_ops.get_node("Retail price", project).id == entity.id


def test_rename_rejects_noop(project: Path) -> None:
    entity, _ = node_ops.add_node("Price", root=project)
    with pytest.raises(ValueError, match="already has label"):
        node_ops.rename_node(entity.id, "Price", root=project)


def test_remove_node_cascades_edges(project: Path) -> None:
    a, _ = node_ops.add_node("Price", root=project)
    b, _ = node_ops.add_node("Demand", root=project)
    c, _ = node_ops.add_node("Ads", root=project)
    edge_ops.add_edge(a.id, b.id, root=project)
    edge_ops.add_edge(c.id, a.id, root=project)
    edge_ops.add_edge(c.id, b.id, root=project)

    _, cascaded, _ = node_ops.remove_node(a.id, root=project)
    assert len(cascaded) == 2  # a→b and c→a removed; c→b untouched

    remaining = edge_ops.list_edges(project)
    assert len(remaining) == 1
    assert remaining[0].from_id == c.id
    assert remaining[0].to_id == b.id


def test_add_edge_requires_existing_nodes(project: Path) -> None:
    a, _ = node_ops.add_node("Price", root=project)
    with pytest.raises(ResolveError, match="no node matches"):
        edge_ops.add_edge(a.id, "node_NOSUCHNODEEVERFOUNDANYWHERE", root=project)


def test_add_edge_rejects_self_loop(project: Path) -> None:
    a, _ = node_ops.add_node("Price", root=project)
    with pytest.raises(ValueError, match="self-loop"):
        edge_ops.add_edge(a.id, a.id, root=project)


def test_edge_list_and_remove(project: Path) -> None:
    a, _ = node_ops.add_node("A", root=project)
    b, _ = node_ops.add_node("B", root=project)
    edge, _ = edge_ops.add_edge(a.id, b.id, root=project)

    assert [e.id for e in edge_ops.list_edges(project)] == [edge.id]
    edge_ops.remove_edge(edge.id, root=project)
    assert edge_ops.list_edges(project) == []


def test_remove_edge_records_rationale_in_commit(project: Path) -> None:
    """AI-proposed removals carry the model's rationale into the
    commit body — that's the audit record (Phase 3 git-native design)."""
    a, _ = node_ops.add_node("A", root=project)
    b, _ = node_ops.add_node("B", root=project)
    edge, _ = edge_ops.add_edge(a.id, b.id, root=project)

    edge_ops.remove_edge(
        edge.id,
        rationale="this edge is a decision rule, not a causal mechanism",
        root=project,
    )
    body = git.run_git(["log", "-1", "--format=%B"], cwd=project).stdout
    assert "rationale: this edge is a decision rule" in body


def test_remove_node_records_rationale_in_commit(project: Path) -> None:
    a, _ = node_ops.add_node("A", root=project)
    node_ops.remove_node(a.id, rationale="out of scope", root=project)
    body = git.run_git(["log", "-1", "--format=%B"], cwd=project).stdout
    assert "rationale: out of scope" in body


def test_retype_node(project: Path) -> None:
    entity, _ = node_ops.add_node("Price", kind="concept", root=project)
    retyped, _ = node_ops.retype_node(entity.id, "variable", root=project)
    assert retyped.id == entity.id
    assert retyped.kind == "variable"


def test_retype_node_rejects_noop(project: Path) -> None:
    entity, _ = node_ops.add_node("Price", kind="concept", root=project)
    with pytest.raises(ValueError, match="already has kind"):
        node_ops.retype_node(entity.id, "concept", root=project)


def test_retype_edge(project: Path) -> None:
    a, _ = node_ops.add_node("A", root=project)
    b, _ = node_ops.add_node("B", root=project)
    edge, _ = edge_ops.add_edge(a.id, b.id, kind="causal", root=project)
    retyped, _ = edge_ops.retype_edge(edge.id, "correlation", root=project)
    assert retyped.id == edge.id
    assert retyped.kind == "correlation"


def test_retype_edge_rejects_noop(project: Path) -> None:
    a, _ = node_ops.add_node("A", root=project)
    b, _ = node_ops.add_node("B", root=project)
    edge, _ = edge_ops.add_edge(a.id, b.id, kind="causal", root=project)
    with pytest.raises(ValueError, match="already has kind"):
        edge_ops.retype_edge(edge.id, "causal", root=project)


def test_ambiguous_label_raises(project: Path) -> None:
    node_ops.add_node("Price", root=project)
    node_ops.add_node("Price", root=project)  # same label, different IDs
    with pytest.raises(ResolveError, match="ambiguous"):
        node_ops.get_node("Price", project)
