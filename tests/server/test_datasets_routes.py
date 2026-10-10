"""Tests for dataset API endpoints — upload, operations, preview, versions."""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.operations.init import init_project
from latris.server.app import create_app


@pytest.fixture
def project(tmp_path: Path, git_identity) -> Path:
    root = tmp_path / "demo"
    init_project(root, statement="Test Q?")
    return root


@pytest.fixture
def client(project: Path) -> TestClient:
    app = create_app(project_root=project)
    return TestClient(app)


def _csv_bytes(rows: list[list[str]]) -> bytes:
    """Build a CSV file as bytes from a list of rows."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerows(rows)
    return buf.getvalue().encode()


@pytest.fixture
def sample_csv() -> bytes:
    return _csv_bytes(
        [
            ["name", "price", "quantity"],
            ["Widget", "9.99", "100"],
            ["Gadget", "19.99", "50"],
            ["Doohickey", "4.99", "200"],
        ]
    )


@pytest.fixture
def uploaded_dataset(client: TestClient, sample_csv: bytes) -> dict:
    """Upload a dataset and return its info."""
    resp = client.post(
        "/api/datasets/upload",
        files={"file": ("test.csv", sample_csv, "text/csv")},
        data={"name": "Test Dataset", "description": "For testing"},
    )
    assert resp.status_code == 201
    return resp.json()["result"]


# ── Upload ────────────────────────────────────────────────────────────


def test_upload_dataset(client: TestClient, sample_csv: bytes) -> None:
    resp = client.post(
        "/api/datasets/upload",
        files={"file": ("sales.csv", sample_csv, "text/csv")},
        data={"name": "Sales Data"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "result" in data
    assert "commit_sha" in data
    assert len(data["commit_sha"]) == 40
    # The result should have an id and columns
    assert "id" in data["result"]
    assert "columns" in data["result"]


def test_upload_without_name_uses_filename(client: TestClient, sample_csv: bytes) -> None:
    resp = client.post(
        "/api/datasets/upload",
        files={"file": ("inventory.csv", sample_csv, "text/csv")},
    )
    assert resp.status_code == 201
    result = resp.json()["result"]
    # Name should be derived from filename or be non-empty
    assert result["name"]


# ── List ──────────────────────────────────────────────────────────────


def test_list_datasets_empty(client: TestClient) -> None:
    resp = client.get("/api/datasets")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_datasets_after_upload(client: TestClient, uploaded_dataset: dict) -> None:
    resp = client.get("/api/datasets")
    assert resp.status_code == 200
    datasets = resp.json()
    assert len(datasets) == 1
    assert datasets[0]["id"] == uploaded_dataset["id"]


# ── Get single ────────────────────────────────────────────────────────


def test_get_dataset_by_id(client: TestClient, uploaded_dataset: dict) -> None:
    ds_id = uploaded_dataset["id"]
    resp = client.get(f"/api/datasets/{ds_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == ds_id


def test_get_dataset_not_found(client: TestClient) -> None:
    resp = client.get("/api/datasets/nonexistent-id")
    assert resp.status_code in (404, 422, 500)


# ── Delete ────────────────────────────────────────────────────────────


def test_delete_dataset(client: TestClient, uploaded_dataset: dict) -> None:
    ds_id = uploaded_dataset["id"]
    resp = client.delete(f"/api/datasets/{ds_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "commit_sha" in data

    # Should no longer appear in list
    listing = client.get("/api/datasets").json()
    assert all(d["id"] != ds_id for d in listing)


# ── Preview ───────────────────────────────────────────────────────────


def test_preview_data(client: TestClient, uploaded_dataset: dict) -> None:
    ds_id = uploaded_dataset["id"]
    resp = client.get(f"/api/datasets/{ds_id}/preview")
    assert resp.status_code == 200
    data = resp.json()
    assert "columns" in data
    assert "rows" in data
    assert "total_rows" in data
    assert data["total_rows"] == 3
    assert "name" in data["columns"]


def test_preview_with_offset_and_limit(client: TestClient, uploaded_dataset: dict) -> None:
    ds_id = uploaded_dataset["id"]
    resp = client.get(f"/api/datasets/{ds_id}/preview", params={"offset": 1, "limit": 1})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["rows"]) == 1


# ── Operations ────────────────────────────────────────────────────────


def test_apply_rename_column_operation(client: TestClient, uploaded_dataset: dict) -> None:
    ds_id = uploaded_dataset["id"]
    resp = client.post(
        f"/api/datasets/{ds_id}/operations",
        json={"kind": "rename_column", "params": {"column": "name", "new_name": "product_name"}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "result" in data
    assert "commit_sha" in data

    # Verify column was renamed in preview
    preview = client.get(f"/api/datasets/{ds_id}/preview").json()
    assert "product_name" in preview["columns"]
    assert "name" not in preview["columns"]


# ── Column metadata ───────────────────────────────────────────────────


def test_update_column_metadata(client: TestClient, uploaded_dataset: dict) -> None:
    ds_id = uploaded_dataset["id"]
    resp = client.patch(
        f"/api/datasets/{ds_id}/columns/price",
        json={"role": "measure", "description": "Unit price in dollars"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "result" in data
    assert "commit_sha" in data


# ── Actions ───────────────────────────────────────────────────────────


def test_get_actions_empty(client: TestClient, uploaded_dataset: dict) -> None:
    ds_id = uploaded_dataset["id"]
    resp = client.get(f"/api/datasets/{ds_id}/actions")
    assert resp.status_code == 200
    data = resp.json()
    assert "entries" in data


def test_get_actions_after_operation(client: TestClient, uploaded_dataset: dict) -> None:
    ds_id = uploaded_dataset["id"]
    # Apply an operation first
    client.post(
        f"/api/datasets/{ds_id}/operations",
        json={"kind": "rename_column", "params": {"column": "name", "new_name": "item"}},
    )
    resp = client.get(f"/api/datasets/{ds_id}/actions")
    assert resp.status_code == 200
    entries = resp.json()["entries"]
    assert len(entries) >= 1


# ── Versions ──────────────────────────────────────────────────────────


def test_create_version(client: TestClient, uploaded_dataset: dict) -> None:
    ds_id = uploaded_dataset["id"]
    resp = client.post(
        f"/api/datasets/{ds_id}/versions",
        json={"name": "v1", "description": "Initial snapshot"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "result" in data
    assert "commit_sha" in data
    assert data["result"]["name"] == "v1"


def test_list_versions(client: TestClient, uploaded_dataset: dict) -> None:
    ds_id = uploaded_dataset["id"]
    # Create a version
    client.post(
        f"/api/datasets/{ds_id}/versions",
        json={"name": "baseline"},
    )
    resp = client.get(f"/api/datasets/{ds_id}/versions")
    assert resp.status_code == 200
    versions = resp.json()
    assert len(versions) >= 1
    # Find our version in the list (upload auto-creates one)
    names = [v["name"] for v in versions]
    assert "baseline" in names


def test_restore_version(client: TestClient, uploaded_dataset: dict) -> None:
    ds_id = uploaded_dataset["id"]
    # Create a version
    ver_resp = client.post(
        f"/api/datasets/{ds_id}/versions",
        json={"name": "before-changes"},
    )
    version_id = ver_resp.json()["result"]["id"]

    # Make a change
    client.post(
        f"/api/datasets/{ds_id}/operations",
        json={"kind": "rename_column", "params": {"column": "name", "new_name": "item"}},
    )

    # Restore
    resp = client.post(f"/api/datasets/{ds_id}/versions/{version_id}/restore")
    assert resp.status_code == 200
    data = resp.json()
    assert "result" in data
    assert "commit_sha" in data

    # Verify the column name is back
    preview = client.get(f"/api/datasets/{ds_id}/preview").json()
    assert "name" in preview["columns"]


# ── Stats ─────────────────────────────────────────────────────────────


def test_column_stats(client: TestClient, uploaded_dataset: dict) -> None:
    ds_id = uploaded_dataset["id"]
    resp = client.get(f"/api/datasets/{ds_id}/stats/price")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)
