"""Server route tests for /api/compose/*: suggestions from data, and applying a staged selection."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.operations import datasets as ds_ops
from latris.operations import nodes as node_ops
from latris.operations.edges import list_edges
from latris.repo import git
from latris.repo.project import require_project
from latris.repo.yaml_io import load_model
from latris.schema import DataLinkSet
from latris.server.app import create_app

CSV = (
    "rainfall,temperature,water_quality,sediment_load\n"
    "120.5,22.3,85.0,15.2\n"
    "95.0,24.1,78.0,18.5\n"
    "140.2,20.8,92.0,12.1\n"
    "80.0,26.0,65.0,22.3\n"
    "110.0,23.5,80.0,16.8\n"
)


@pytest.fixture
def project(empty_project_root: Path) -> Path:
    return empty_project_root


@pytest.fixture
def client(project: Path) -> TestClient:
    return TestClient(create_app(project_root=project))


@pytest.fixture
def dataset_id(project: Path, tmp_path: Path) -> str:
    csv = tmp_path / "water.csv"
    csv.write_text(CSV, encoding="utf-8", newline="")
    ds, _ = ds_ops.upload_dataset(csv, name="Water", root=project)
    return ds.id


def test_suggest_nodes(client: TestClient, project: Path, dataset_id: str) -> None:
    node_ops.add_node("Rainfall", root=project)  # already a factor: not suggested again
    rows = client.get("/api/compose/suggest-nodes").json()
    assert [r["label"] for r in rows] == ["temperature", "water_quality", "sediment_load"]
    first = rows[0]
    assert (first["kind"], first["datasetId"], first["columnName"], first["source"]) == (
        "variable", dataset_id, "temperature", "data")
    assert first["stats"]["nonNull"] == 5


def test_suggest_nodes_without_data(client: TestClient) -> None:
    assert client.get("/api/compose/suggest-nodes").json() == []


def test_suggest_edges(client: TestClient, dataset_id: str) -> None:
    r = client.post("/api/compose/suggest-edges", json={"node_labels": ["Water_Quality", "sediment_load"],
                                                       "method": "spearman"})
    assert r.status_code == 200
    (edge,) = r.json()
    assert (edge["fromLabel"], edge["toLabel"]) == ("Water_Quality", "sediment_load")  # the labels as given
    assert edge["datasetId"] == dataset_id and edge["statistic"] == "spearman"
    assert edge["coefficient"] == pytest.approx(-1.0)
    # Below the threshold, or fewer than two matching columns: nothing.
    assert client.post("/api/compose/suggest-edges", json={"node_labels": ["rainfall", "water_quality"],
                                                           "threshold": 2}).json() == []
    assert client.post("/api/compose/suggest-edges", json={"node_labels": ["rainfall"]}).json() == []


def test_suggest_edges_errors(client: TestClient, dataset_id: str) -> None:
    # An unknown method was once run as Pearson and labelled with the unknown name.
    bad = client.post("/api/compose/suggest-edges", json={"node_labels": ["rainfall", "water_quality"],
                                                         "method": "bogus"})
    assert bad.status_code == 422 and "not a correlation method" in bad.json()["detail"]
    assert client.post("/api/compose/suggest-edges", json={}).status_code == 422


def test_apply(client: TestClient, project: Path, dataset_id: str) -> None:
    r = client.post("/api/compose/apply", json={
        "nodes": [
            {"label": "rainfall", "kind": "variable", "origin": "data-derived", "description": "mm per month",
             "dataset_id": dataset_id, "column_name": "rainfall"},
            {"label": "Water quality", "kind": "driver"},
        ],
        "edges": [{"from_label": "rainfall", "to_label": "Water quality", "origin": "data-derived",
                   "description": "wetter months are cleaner", "dataset_id": dataset_id,
                   "from_column": "rainfall", "to_column": "water_quality", "statistic": "pearson",
                   "stat_value": "r=+0.97"}],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["remapped"] == [{"label": "Water quality", "from": "driver", "to": "variable"}]
    nodes = {e.label: e for e in node_ops.list_nodes(root=project)}
    (edge,) = list_edges(root=project)
    assert body["created_ids"] == [nodes["rainfall"].id, nodes["Water quality"].id, edge.id]
    assert nodes["Water quality"].kind == "variable"
    # One commit holds everything, the data links included.
    assert body["commit_sha"] == git.head_sha(project)
    assert not git.has_uncommitted_changes(project)
    links = load_model(DataLinkSet, require_project(project).data_links_yaml).entries
    assert {(dl.target_id, tuple(dl.column_names)) for dl in links} == {
        (nodes["rainfall"].id, ("rainfall",)), (edge.id, ("rainfall", "water_quality"))}


def test_apply_errors_leave_nothing_behind(client: TestClient, project: Path) -> None:
    head = git.head_sha(project)
    missing_desc = client.post("/api/compose/apply", json={"nodes": [{"label": "B", "origin": "ai-proposed"}]})
    assert missing_desc.status_code == 422 and "description required" in missing_desc.json()["detail"]
    dangling = client.post("/api/compose/apply", json={"nodes": [{"label": "A"}],
                                                       "edges": [{"from_label": "A", "to_label": "Missing"}]})
    assert dangling.status_code == 404
    assert client.post("/api/compose/apply", json={"nodes": [{"kind": "concept"}]}).status_code == 422
    assert node_ops.list_nodes(root=project) == []
    assert git.head_sha(project) == head and not git.has_uncommitted_changes(project)

    assert client.post("/api/compose/apply", json={"nodes": [{"label": "A"}]}).status_code == 200
    dup = client.post("/api/compose/apply", json={"nodes": [{"label": "A"}]})
    assert dup.status_code == 422 and "already called" in dup.json()["detail"]
    assert [e.label for e in node_ops.list_nodes(root=project)] == ["A"]


def test_apply_nothing(client: TestClient, project: Path) -> None:
    head = git.head_sha(project)
    r = client.post("/api/compose/apply", json={})
    assert r.status_code == 200 and r.json() == {"created_ids": [], "commit_sha": head, "remapped": []}
