from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import attributes as attr_ops
from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations import view_attributes as view_attr_ops
from latris.operations.init import init_project
from latris.repo import git
from latris.repo.yaml_io import load_model
from latris.schema import DescriptionSet, PolaritySet


@pytest.fixture
def project_with_edge(tmp_path: Path, git_identity):
    root = tmp_path / "demo"
    init_project(root, statement="Q?")
    a, _ = node_ops.add_node("Price", kind="variable", root=root)
    b, _ = node_ops.add_node("Demand", kind="variable", root=root)
    edge, _ = edge_ops.add_edge(a.id, b.id, root=root)
    return root, a, b, edge


def test_set_description_on_node(project_with_edge) -> None:
    root, a, _, _ = project_with_edge
    attr_ops.set_attribute(a.id, "description", "Posted retail price.", root=root)
    store = load_model(
        DescriptionSet,
        root / "substrate" / "attributes" / "descriptions.yaml",
    )
    assert len(store.entries) == 1
    assert store.entries[0].target_id == a.id
    assert store.entries[0].value == "Posted retail price."


def test_set_polarity_via_view_attribute(project_with_edge) -> None:
    root, _, _, edge = project_with_edge
    view_attr_ops.set_view_attribute(edge.id, "cld", "polarity", "-", root=root)
    store = load_model(
        PolaritySet,
        root / "views" / "parameters" / "cld-polarity.yaml",
    )
    assert store.entries[0].value == "-"


def test_set_confidence_rejects_bad_value(project_with_edge) -> None:
    root, _, _, edge = project_with_edge
    with pytest.raises(ValueError, match="confidence must be"):
        attr_ops.set_attribute(edge.id, "confidence", "excellent", root=root)


def test_set_attribute_upserts(project_with_edge) -> None:
    root, a, _, _ = project_with_edge
    attr_ops.set_attribute(a.id, "description", "first", root=root)
    attr_ops.set_attribute(a.id, "description", "second", root=root)
    store = load_model(
        DescriptionSet,
        root / "substrate" / "attributes" / "descriptions.yaml",
    )
    assert len(store.entries) == 1
    assert store.entries[0].value == "second"


def test_each_mutation_creates_commit(project_with_edge) -> None:
    root, _, _, edge = project_with_edge
    before = int(git.run_git(["rev-list", "--count", "HEAD"], cwd=root).stdout.strip())
    view_attr_ops.set_view_attribute(edge.id, "cld", "polarity", "+", root=root)
    view_attr_ops.set_view_attribute(edge.id, "cld", "polarity", "-", root=root)
    after = int(git.run_git(["rev-list", "--count", "HEAD"], cwd=root).stdout.strip())
    assert after == before + 2
