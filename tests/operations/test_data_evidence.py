from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import datasets as data_ops
from latris.operations import evidence as evidence_ops
from latris.operations import nodes as node_ops
from latris.operations.init import init_project


@pytest.fixture
def project_with_dataset(tmp_path: Path, git_identity):
    root = tmp_path / "demo"
    init_project(root, statement="Q?")
    node, _ = node_ops.add_node("Temperature", root=root)

    # Create a minimal CSV for upload
    csv = tmp_path / "sample.csv"
    csv.write_text("temperature,rainfall\n20,100\n25,80\n")
    ds, _ = data_ops.upload_dataset(csv, name="weather", root=root)

    return root, node, ds


def test_add_data_link_creates_and_commits(project_with_dataset) -> None:
    root, node, ds = project_with_dataset
    link, sha = evidence_ops.add_data_link(
        node.id,
        ds.id,
        column_names=["temperature"],
        statistic="distribution",
        value="mean=22.5",
        rationale="Column maps to concept",
        root=root,
    )
    assert link.target_id == node.id
    assert link.dataset_id == ds.id
    assert link.column_names == ["temperature"]
    assert link.statistic == "distribution"
    assert link.value == "mean=22.5"
    assert link.origin == "human-direct"
    assert sha


def test_add_data_link_rejects_unknown_dataset(project_with_dataset) -> None:
    root, node, _ = project_with_dataset
    with pytest.raises(ValueError, match="unknown dataset"):
        evidence_ops.add_data_link(node.id, "nonexistent_id", root=root)


def test_add_data_link_resolves_target_by_label(project_with_dataset) -> None:
    root, node, ds = project_with_dataset
    link, _ = evidence_ops.add_data_link(
        "Temperature",
        ds.id,
        root=root,
    )
    assert link.target_id == node.id


def test_add_data_link_model_level(project_with_dataset) -> None:
    root, _, ds = project_with_dataset
    link, _ = evidence_ops.add_data_link(
        None,
        ds.id,
        rationale="Dataset supports overall model",
        root=root,
    )
    assert link.target_id is None
    assert link.dataset_id == ds.id
