"""Tests for dataset operations — upload, data operations, versioning."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import datasets as ds_ops
from latris.operations.init import init_project
from latris.repo import git

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def project(tmp_path: Path, git_identity):
    root = tmp_path / "demo"
    init_project(root, statement="Q?")
    return root


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    """Create a small CSV file for upload tests."""
    p = tmp_path / "sample.csv"
    p.write_text(
        "name,age,score\nAlice,30,85.5\nBob,,92.0\nCarol,25,\nDave,35,78.0\n",
        encoding="utf-8",
        newline="",
    )
    return p


@pytest.fixture
def sample_tsv(tmp_path: Path) -> Path:
    """Create a small TSV file for upload tests."""
    p = tmp_path / "survey.tsv"
    p.write_text(
        "id\tresponse\tregion\n1\thigh\tnorth\n2\tlow\tsouth\n3\tmedium\tnorth\n",
        encoding="utf-8",
        newline="",
    )
    return p


def _commit_count(root: Path) -> int:
    return int(git.run_git(["rev-list", "--count", "HEAD"], cwd=root).stdout.strip())


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


class TestUpload:
    def test_upload_csv_creates_dataset(self, project: Path, sample_csv: Path) -> None:
        before = _commit_count(project)
        dataset, sha = ds_ops.upload_dataset(sample_csv, root=project)

        assert dataset.name == "sample"
        assert dataset.source_type == "file"
        assert dataset.rows == 4
        assert len(dataset.columns) == 3
        assert dataset.columns[0].name == "name"
        assert _commit_count(project) == before + 2  # upload + auto-version
        assert len(sha) == 40

        # File exists on disk
        assert (project / dataset.location).exists()

        # Auto-version created
        versions = ds_ops.list_versions(dataset.id, root=project)
        assert len(versions) == 1
        assert versions[0].name == "uploaded"

    def test_upload_tsv(self, project: Path, sample_tsv: Path) -> None:
        dataset, _ = ds_ops.upload_dataset(sample_tsv, root=project)
        assert dataset.name == "survey"
        assert dataset.rows == 3
        assert dataset.columns[0].name == "id"

    def test_upload_custom_name(self, project: Path, sample_csv: Path) -> None:
        dataset, _ = ds_ops.upload_dataset(
            sample_csv,
            name="pricing-data",
            description="Test data",
            root=project,
        )
        assert dataset.name == "pricing-data"
        assert dataset.description == "Test data"
        assert "pricing-data" in dataset.location

    def test_upload_duplicate_name_fails(self, project: Path, sample_csv: Path) -> None:
        ds_ops.upload_dataset(sample_csv, root=project)
        with pytest.raises(ValueError, match="already exists"):
            ds_ops.upload_dataset(sample_csv, root=project)

    def test_upload_unsupported_format_fails(self, project: Path, tmp_path: Path) -> None:
        bad = tmp_path / "data.xlsx"
        bad.write_text("not a csv", encoding="utf-8")
        with pytest.raises(ValueError, match="Unsupported"):
            ds_ops.upload_dataset(bad, root=project)


# ---------------------------------------------------------------------------
# List / get
# ---------------------------------------------------------------------------


class TestListGet:
    def test_list_empty(self, project: Path) -> None:
        assert ds_ops.list_datasets(project) == []

    def test_list_empty_when_dataset_library_missing(self, project: Path) -> None:
        """Legacy projects may predate data/datasets.yaml."""
        (project / "data" / "datasets.yaml").unlink()
        assert ds_ops.list_datasets(project) == []

    def test_list_after_upload(self, project: Path, sample_csv: Path) -> None:
        ds_ops.upload_dataset(sample_csv, root=project)
        datasets = ds_ops.list_datasets(project)
        assert len(datasets) == 1
        assert datasets[0].name == "sample"

    def test_upload_creates_missing_data_sidecars(self, project: Path, sample_csv: Path) -> None:
        """Uploading should work in projects created before the data layout existed."""
        data_dir = project / "data"
        for child in sorted(data_dir.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                child.rmdir()
        data_dir.rmdir()

        dataset, _ = ds_ops.upload_dataset(sample_csv, root=project)

        assert dataset.name == "sample"
        assert (project / "data" / "datasets.yaml").is_file()
        assert (project / "data" / "versions.yaml").is_file()
        assert (project / dataset.location).is_file()

    def test_get_by_name(self, project: Path, sample_csv: Path) -> None:
        uploaded, _ = ds_ops.upload_dataset(sample_csv, root=project)
        found = ds_ops.get_dataset("sample", root=project)
        assert found.id == uploaded.id

    def test_get_by_id(self, project: Path, sample_csv: Path) -> None:
        uploaded, _ = ds_ops.upload_dataset(sample_csv, root=project)
        found = ds_ops.get_dataset(uploaded.id, root=project)
        assert found.name == "sample"

    def test_get_not_found(self, project: Path) -> None:
        with pytest.raises(ValueError, match="not found"):
            ds_ops.get_dataset("nonexistent", root=project)


# ---------------------------------------------------------------------------
# Remove
# ---------------------------------------------------------------------------


class TestRemove:
    def test_remove_dataset(self, project: Path, sample_csv: Path) -> None:
        uploaded, _ = ds_ops.upload_dataset(sample_csv, root=project)
        removed, sha = ds_ops.remove_dataset(uploaded.id, root=project)
        assert removed.id == uploaded.id
        assert ds_ops.list_datasets(project) == []
        assert len(sha) == 40

    def test_remove_not_found(self, project: Path) -> None:
        with pytest.raises(ValueError, match="not found"):
            ds_ops.remove_dataset("nonexistent", root=project)


# ---------------------------------------------------------------------------
# Data operations
# ---------------------------------------------------------------------------


class TestOperations:
    def test_rename_column(self, project: Path, sample_csv: Path) -> None:
        dataset, _ = ds_ops.upload_dataset(sample_csv, root=project)
        action, sha = ds_ops.apply_operation(
            dataset.id,
            "rename_column",
            {"column": "name", "new_name": "full_name"},
            root=project,
        )
        assert action.kind == "rename_column"
        assert action.rows_before == 4
        assert action.rows_after == 4
        assert "full_name" in action.columns_affected

        # Verify column metadata updated
        ds = ds_ops.get_dataset(dataset.id, root=project)
        col_names = [c.name for c in ds.columns]
        assert "full_name" in col_names
        assert "name" not in col_names

    def test_drop_nan_rows(self, project: Path, sample_csv: Path) -> None:
        dataset, _ = ds_ops.upload_dataset(sample_csv, root=project)
        # Cast age to float first so NaN works
        ds_ops.apply_operation(
            dataset.id,
            "cast_column",
            {"column": "age", "dtype": "float64"},
            root=project,
        )
        action, _ = ds_ops.apply_operation(
            dataset.id,
            "drop_nan_rows",
            {"columns": ["age"], "how": "any"},
            root=project,
        )
        assert action.rows_before == 4
        assert action.rows_after == 3  # Bob has no age

    def test_fill_nan_with_value(self, project: Path, sample_csv: Path) -> None:
        dataset, _ = ds_ops.upload_dataset(sample_csv, root=project)
        ds_ops.apply_operation(
            dataset.id,
            "cast_column",
            {"column": "score", "dtype": "float64"},
            root=project,
        )
        action, _ = ds_ops.apply_operation(
            dataset.id,
            "fill_nan",
            {"column": "score", "method": "value", "value": 0.0},
            root=project,
        )
        assert action.rows_before == action.rows_after  # fill doesn't remove rows

        # Verify the data changed
        preview = ds_ops.preview_data(dataset.id, root=project)
        score_idx = preview["columns"].index("score")
        scores = [row[score_idx] for row in preview["rows"]]
        assert None not in scores  # No more nulls

    def test_fill_nan_forwardfill(self, project: Path, sample_csv: Path) -> None:
        dataset, _ = ds_ops.upload_dataset(sample_csv, root=project)
        ds_ops.apply_operation(
            dataset.id,
            "cast_column",
            {"column": "score", "dtype": "float64"},
            root=project,
        )
        action, _ = ds_ops.apply_operation(
            dataset.id,
            "fill_nan",
            {"column": "score", "method": "forwardfill"},
            root=project,
        )
        assert action.kind == "fill_nan"

    def test_drop_columns(self, project: Path, sample_csv: Path) -> None:
        dataset, _ = ds_ops.upload_dataset(sample_csv, root=project)
        action, _ = ds_ops.apply_operation(
            dataset.id,
            "drop_columns",
            {"columns": ["age"]},
            root=project,
        )
        ds = ds_ops.get_dataset(dataset.id, root=project)
        assert len(ds.columns) == 2
        assert all(c.name != "age" for c in ds.columns)

    def test_filter_rows(self, project: Path, sample_csv: Path) -> None:
        dataset, _ = ds_ops.upload_dataset(sample_csv, root=project)
        action, _ = ds_ops.apply_operation(
            dataset.id,
            "filter_rows",
            {"column": "name", "op": "eq", "value": "Alice"},
            root=project,
        )
        assert action.rows_after == 1

    def test_sort_rows(self, project: Path, sample_csv: Path) -> None:
        dataset, _ = ds_ops.upload_dataset(sample_csv, root=project)
        action, _ = ds_ops.apply_operation(
            dataset.id,
            "sort_rows",
            {"column": "name", "ascending": False},
            root=project,
        )
        assert action.rows_before == action.rows_after
        preview = ds_ops.preview_data(dataset.id, root=project)
        name_idx = preview["columns"].index("name")
        names = [row[name_idx] for row in preview["rows"]]
        assert names == sorted(names, reverse=True)

    def test_deduplicate(self, project: Path, tmp_path: Path) -> None:
        # Create CSV with duplicates
        csv = tmp_path / "dupes.csv"
        csv.write_text(
            "x,y\n1,a\n2,b\n1,a\n3,c\n",
            encoding="utf-8",
            newline="",
        )
        dataset, _ = ds_ops.upload_dataset(csv, root=project)
        action, _ = ds_ops.apply_operation(
            dataset.id,
            "deduplicate",
            {"columns": ["x", "y"], "keep": "first"},
            root=project,
        )
        assert action.rows_after == 3

    def test_invalid_column_fails(self, project: Path, sample_csv: Path) -> None:
        dataset, _ = ds_ops.upload_dataset(sample_csv, root=project)
        with pytest.raises(ValueError, match="not found"):
            ds_ops.apply_operation(
                dataset.id,
                "rename_column",
                {"column": "nonexistent", "new_name": "x"},
                root=project,
            )

    def test_action_log_recorded(self, project: Path, sample_csv: Path) -> None:
        dataset, _ = ds_ops.upload_dataset(sample_csv, root=project)
        ds_ops.apply_operation(
            dataset.id,
            "rename_column",
            {"column": "name", "new_name": "full_name"},
            root=project,
        )
        ds_ops.apply_operation(
            dataset.id,
            "drop_columns",
            {"columns": ["age"]},
            root=project,
        )
        log = ds_ops.get_action_log(dataset.id, root=project)
        assert len(log.entries) == 2
        assert log.entries[0].kind == "rename_column"
        assert log.entries[1].kind == "drop_columns"


# ---------------------------------------------------------------------------
# Column metadata
# ---------------------------------------------------------------------------


class TestColumnMetadata:
    def test_update_role(self, project: Path, sample_csv: Path) -> None:
        dataset, _ = ds_ops.upload_dataset(sample_csv, root=project)
        updated, sha = ds_ops.update_column_metadata(
            dataset.id,
            "name",
            role="id",
            root=project,
        )
        col = [c for c in updated.columns if c.name == "name"][0]
        assert col.role == "id"

    def test_update_description(self, project: Path, sample_csv: Path) -> None:
        dataset, _ = ds_ops.upload_dataset(sample_csv, root=project)
        updated, _ = ds_ops.update_column_metadata(
            dataset.id,
            "score",
            description="Exam score 0-100",
            root=project,
        )
        col = [c for c in updated.columns if c.name == "score"][0]
        assert col.description == "Exam score 0-100"

    def test_update_nonexistent_column_fails(self, project: Path, sample_csv: Path) -> None:
        dataset, _ = ds_ops.upload_dataset(sample_csv, root=project)
        with pytest.raises(ValueError, match="not found"):
            ds_ops.update_column_metadata(
                dataset.id,
                "bogus",
                role="feature",
                root=project,
            )


# ---------------------------------------------------------------------------
# Versioning
# ---------------------------------------------------------------------------


class TestVersioning:
    def test_version_and_list(self, project: Path, sample_csv: Path) -> None:
        dataset, _ = ds_ops.upload_dataset(sample_csv, root=project)
        version, sha = ds_ops.version_dataset(
            dataset.id,
            "raw-import",
            description="As uploaded",
            root=project,
        )
        assert version.name == "raw-import"
        assert version.row_count == 4
        assert version.column_count == 3
        assert version.content_hash.startswith("sha256:")
        assert len(version.commit_sha) == 40

        versions = ds_ops.list_versions(dataset.id, root=project)
        assert len(versions) == 2  # auto "uploaded" + manual "raw-import"
        assert versions[-1].id == version.id

    def test_restore_version(self, project: Path, sample_csv: Path) -> None:
        dataset, _ = ds_ops.upload_dataset(sample_csv, root=project)

        # Use the auto-created "uploaded" version as restore point
        versions = ds_ops.list_versions(dataset.id, root=project)
        version = versions[0]  # the auto-created "uploaded" version

        # Modify: drop a column
        ds_ops.apply_operation(
            dataset.id,
            "drop_columns",
            {"columns": ["age"]},
            root=project,
        )
        ds_after_drop = ds_ops.get_dataset(dataset.id, root=project)
        assert len(ds_after_drop.columns) == 2

        # Restore to raw state
        restored, sha = ds_ops.restore_version(
            dataset.id,
            version.id,
            root=project,
        )
        assert len(restored.columns) == 3
        assert restored.rows == 4
        col_names = [c.name for c in restored.columns]
        assert "age" in col_names

    def test_version_not_found(self, project: Path, sample_csv: Path) -> None:
        dataset, _ = ds_ops.upload_dataset(sample_csv, root=project)
        with pytest.raises(ValueError, match="not found"):
            ds_ops.restore_version(
                dataset.id,
                "data-version_NONEXISTENT01234567890",
                root=project,
            )


# ---------------------------------------------------------------------------
# Preview and stats
# ---------------------------------------------------------------------------


class TestPreviewAndStats:
    def test_preview(self, project: Path, sample_csv: Path) -> None:
        dataset, _ = ds_ops.upload_dataset(sample_csv, root=project)
        preview = ds_ops.preview_data(dataset.id, root=project)
        assert preview["total_rows"] == 4
        assert preview["columns"] == ["name", "age", "score"]
        assert len(preview["rows"]) == 4

    def test_preview_pagination(self, project: Path, sample_csv: Path) -> None:
        dataset, _ = ds_ops.upload_dataset(sample_csv, root=project)
        preview = ds_ops.preview_data(dataset.id, offset=1, limit=2, root=project)
        assert len(preview["rows"]) == 2
        assert preview["offset"] == 1
        assert preview["total_rows"] == 4

    def test_column_stats(self, project: Path, sample_csv: Path) -> None:
        dataset, _ = ds_ops.upload_dataset(sample_csv, root=project)
        # Cast to numeric first
        ds_ops.apply_operation(
            dataset.id,
            "cast_column",
            {"column": "score", "dtype": "float64"},
            root=project,
        )
        stats = ds_ops.column_stats(dataset.id, "score", root=project)
        assert stats["name"] == "score"
        assert stats["count"] == 3  # one NaN
        assert stats["nulls"] == 1
        assert stats["total"] == 4
        assert "mean" in stats


# ---------------------------------------------------------------------------
# Row operations, cell editing, column reorder
# ---------------------------------------------------------------------------


class TestRowOperations:
    def test_insert_row_appends_by_default(self, project: Path, sample_csv: Path) -> None:
        dataset, _ = ds_ops.upload_dataset(sample_csv, root=project)
        action, _ = ds_ops.apply_operation(
            dataset.id,
            "insert_row",
            {},
            root=project,
        )
        assert action.rows_before == 4
        assert action.rows_after == 5
        preview = ds_ops.preview_data(dataset.id, root=project)
        # Last row should be all NaN
        last_row = preview["rows"][-1]
        assert all(v is None for v in last_row)

    def test_insert_row_at_position(self, project: Path, sample_csv: Path) -> None:
        dataset, _ = ds_ops.upload_dataset(sample_csv, root=project)
        action, _ = ds_ops.apply_operation(
            dataset.id,
            "insert_row",
            {"position": 1, "values": {"name": "Zara", "age": 22}},
            root=project,
        )
        assert action.rows_after == 5
        preview = ds_ops.preview_data(dataset.id, root=project)
        name_idx = preview["columns"].index("name")
        assert preview["rows"][1][name_idx] == "Zara"

    def test_insert_row_invalid_position(self, project: Path, sample_csv: Path) -> None:
        dataset, _ = ds_ops.upload_dataset(sample_csv, root=project)
        with pytest.raises(ValueError, match="out of range"):
            ds_ops.apply_operation(
                dataset.id,
                "insert_row",
                {"position": 100},
                root=project,
            )

    def test_delete_rows_single(self, project: Path, sample_csv: Path) -> None:
        dataset, _ = ds_ops.upload_dataset(sample_csv, root=project)
        action, _ = ds_ops.apply_operation(
            dataset.id,
            "delete_rows",
            {"indices": [0]},
            root=project,
        )
        assert action.rows_before == 4
        assert action.rows_after == 3
        preview = ds_ops.preview_data(dataset.id, root=project)
        name_idx = preview["columns"].index("name")
        names = [r[name_idx] for r in preview["rows"]]
        assert "Alice" not in names

    def test_delete_rows_multiple(self, project: Path, sample_csv: Path) -> None:
        dataset, _ = ds_ops.upload_dataset(sample_csv, root=project)
        action, _ = ds_ops.apply_operation(
            dataset.id,
            "delete_rows",
            {"indices": [0, 3]},
            root=project,
        )
        assert action.rows_after == 2

    def test_delete_rows_invalid_index(self, project: Path, sample_csv: Path) -> None:
        dataset, _ = ds_ops.upload_dataset(sample_csv, root=project)
        with pytest.raises(ValueError, match="out of range"):
            ds_ops.apply_operation(
                dataset.id,
                "delete_rows",
                {"indices": [99]},
                root=project,
            )

    def test_delete_rows_empty_indices(self, project: Path, sample_csv: Path) -> None:
        dataset, _ = ds_ops.upload_dataset(sample_csv, root=project)
        with pytest.raises(ValueError, match="No row indices"):
            ds_ops.apply_operation(
                dataset.id,
                "delete_rows",
                {"indices": []},
                root=project,
            )

    def test_duplicate_rows_single(self, project: Path, sample_csv: Path) -> None:
        dataset, _ = ds_ops.upload_dataset(sample_csv, root=project)
        action, _ = ds_ops.apply_operation(
            dataset.id,
            "duplicate_rows",
            {"indices": [0]},
            root=project,
        )
        assert action.rows_after == 5
        preview = ds_ops.preview_data(dataset.id, root=project)
        name_idx = preview["columns"].index("name")
        # Row 0 and row 1 should both be "Alice"
        assert preview["rows"][0][name_idx] == "Alice"
        assert preview["rows"][1][name_idx] == "Alice"

    def test_duplicate_rows_multiple(self, project: Path, sample_csv: Path) -> None:
        dataset, _ = ds_ops.upload_dataset(sample_csv, root=project)
        action, _ = ds_ops.apply_operation(
            dataset.id,
            "duplicate_rows",
            {"indices": [0, 2]},
            root=project,
        )
        assert action.rows_after == 6  # 4 + 2 duplicates

    def test_duplicate_rows_invalid(self, project: Path, sample_csv: Path) -> None:
        dataset, _ = ds_ops.upload_dataset(sample_csv, root=project)
        with pytest.raises(ValueError, match="out of range"):
            ds_ops.apply_operation(
                dataset.id,
                "duplicate_rows",
                {"indices": [10]},
                root=project,
            )


class TestCellEditing:
    def test_update_cell_string(self, project: Path, sample_csv: Path) -> None:
        dataset, _ = ds_ops.upload_dataset(sample_csv, root=project)
        action, _ = ds_ops.apply_operation(
            dataset.id,
            "update_cell",
            {"row_index": 0, "column": "name", "value": "Alicia"},
            root=project,
        )
        assert action.kind == "update_cell"
        preview = ds_ops.preview_data(dataset.id, root=project)
        name_idx = preview["columns"].index("name")
        assert preview["rows"][0][name_idx] == "Alicia"

    def test_update_cell_numeric(self, project: Path, sample_csv: Path) -> None:
        dataset, _ = ds_ops.upload_dataset(sample_csv, root=project)
        ds_ops.apply_operation(
            dataset.id,
            "cast_column",
            {"column": "score", "dtype": "float64"},
            root=project,
        )
        action, _ = ds_ops.apply_operation(
            dataset.id,
            "update_cell",
            {"row_index": 0, "column": "score", "value": "99.5"},
            root=project,
        )
        preview = ds_ops.preview_data(dataset.id, root=project)
        score_idx = preview["columns"].index("score")
        assert preview["rows"][0][score_idx] == 99.5

    def test_update_cell_to_null(self, project: Path, sample_csv: Path) -> None:
        dataset, _ = ds_ops.upload_dataset(sample_csv, root=project)
        action, _ = ds_ops.apply_operation(
            dataset.id,
            "update_cell",
            {"row_index": 0, "column": "name", "value": ""},
            root=project,
        )
        preview = ds_ops.preview_data(dataset.id, root=project)
        name_idx = preview["columns"].index("name")
        assert preview["rows"][0][name_idx] is None

    def test_update_cell_invalid_row(self, project: Path, sample_csv: Path) -> None:
        dataset, _ = ds_ops.upload_dataset(sample_csv, root=project)
        with pytest.raises(ValueError, match="out of range"):
            ds_ops.apply_operation(
                dataset.id,
                "update_cell",
                {"row_index": 99, "column": "name", "value": "x"},
                root=project,
            )

    def test_update_cell_invalid_column(self, project: Path, sample_csv: Path) -> None:
        dataset, _ = ds_ops.upload_dataset(sample_csv, root=project)
        with pytest.raises(ValueError, match="not found"):
            ds_ops.apply_operation(
                dataset.id,
                "update_cell",
                {"row_index": 0, "column": "bogus", "value": "x"},
                root=project,
            )


class TestReorderColumns:
    def test_reorder_columns(self, project: Path, sample_csv: Path) -> None:
        dataset, _ = ds_ops.upload_dataset(sample_csv, root=project)
        action, _ = ds_ops.apply_operation(
            dataset.id,
            "reorder_columns",
            {"columns": ["score", "name", "age"]},
            root=project,
        )
        assert action.kind == "reorder_columns"
        preview = ds_ops.preview_data(dataset.id, root=project)
        assert preview["columns"] == ["score", "name", "age"]

    def test_reorder_columns_missing(self, project: Path, sample_csv: Path) -> None:
        dataset, _ = ds_ops.upload_dataset(sample_csv, root=project)
        with pytest.raises(ValueError, match="not in DataFrame"):
            ds_ops.apply_operation(
                dataset.id,
                "reorder_columns",
                {"columns": ["score", "name", "bogus"]},
                root=project,
            )

    def test_reorder_columns_incomplete(self, project: Path, sample_csv: Path) -> None:
        dataset, _ = ds_ops.upload_dataset(sample_csv, root=project)
        with pytest.raises(ValueError, match="missing from new order"):
            ds_ops.apply_operation(
                dataset.id,
                "reorder_columns",
                {"columns": ["score", "name"]},
                root=project,
            )


# ---------------------------------------------------------------------------
# Action summaries and affected columns, for every operation kind
# ---------------------------------------------------------------------------

# (kind, params, rows_before, rows_after, summary, columns_affected)
_SUMMARIES = [
    ("rename_column", {"column": "a", "new_name": "b"}, 4, 4, 'Renamed column "a" to "b"', ["a", "b"]),
    ("cast_column", {"column": "a", "dtype": "float64"}, 4, 4, 'Cast column "a" to float64', ["a"]),
    ("drop_columns", {"columns": ["a", "b"]}, 4, 4, 'Dropped columns "a", "b"', ["a", "b"]),
    ("drop_nan_rows", {"columns": ["a"]}, 4, 3, 'Dropped 1 NaN rows (columns: "a")', ["a"]),
    ("drop_nan_rows", {}, 4, 2, 'Dropped 2 NaN rows (columns: "all")', []),
    ("drop_nan_rows", {"columns": None}, 4, 2, 'Dropped 2 NaN rows (columns: "all")', []),
    ("fill_nan", {"column": "a", "method": "backfill"}, 4, 4, 'Filled NaN in "a" (backfill)', ["a"]),
    ("filter_rows", {"column": "a", "op": "gt", "value": 3}, 4, 1, 'Filtered rows: "a" gt 3 (removed 3)', ["a"]),
    ("sort_rows", {"column": "a"}, 4, 4, 'Sorted by "a" (ascending)', ["a"]),
    ("sort_rows", {"column": "a", "ascending": False}, 4, 4, 'Sorted by "a" (descending)', ["a"]),
    ("deduplicate", {}, 4, 3, "Deduplicated (removed 1 rows)", []),
    ("deduplicate", {"columns": None}, 4, 3, "Deduplicated (removed 1 rows)", []),
    ("replace_values", {"column": "a", "old": 1, "new": 2}, 4, 4, 'Replaced "1" with "2" in "a"', ["a"]),
    ("strip_whitespace", {"column": "a"}, 4, 4, 'Stripped whitespace from "a"', ["a"]),
    ("lowercase", {"column": "a"}, 4, 4, 'Lowercased "a"', ["a"]),
    ("uppercase", {"column": "a"}, 4, 4, 'Uppercased "a"', ["a"]),
    ("clip_values", {"column": "a", "min": 0}, 4, 4, 'Clipped "a" to [0, ]', ["a"]),
    ("remove_outliers", {"column": "a"}, 4, 3, 'Removed 1 outliers from "a" (iqr)', ["a"]),
    ("log_transform", {"column": "a"}, 4, 4, 'Log-transformed "a"', ["a"]),
    ("log_transform", {"column": "a", "target": "la"}, 4, 4, 'Log-transformed "a"', ["a", "la"]),
    ("normalize", {"column": "a"}, 4, 4, 'Normalized "a" (min-max)', ["a"]),
    ("standardize", {"column": "a"}, 4, 4, 'Standardized "a" (z-score)', ["a"]),
    ("round_values", {"column": "a"}, 4, 4, 'Rounded "a" to 2 decimals', ["a"]),
    ("bin_discretize", {"column": "a", "bins": 3, "target": "ab"}, 4, 4, 'Binned "a" into 3 bins', ["a", "ab"]),
    ("rank_transform", {"column": "a"}, 4, 4, 'Ranked "a"', ["a"]),
    ("derived_column", {"expression": "a * 2", "target": "d"}, 4, 4, 'Created column "d" = a * 2', ["d"]),
    ("date_extract", {"column": "t"}, 4, 4, 'Extracted year, month, day from "t"', ["t"]),
    ("date_extract", {"column": "t", "parts": ["hour"]}, 4, 4, 'Extracted hour from "t"', ["t"]),
    ("lag_lead", {"column": "a", "periods": 2}, 4, 4, 'Created lag(2) of "a"', ["a"]),
    ("rolling_window", {"column": "a", "window": 5, "func": "sum"}, 4, 4, 'Rolling sum(5) of "a"', ["a"]),
    ("difference", {"column": "a"}, 4, 4, 'Differenced "a" (periods=1)', ["a"]),
    ("cumulative_sum", {"column": "a", "target": "c"}, 4, 4, 'Cumulative sum of "a"', ["a", "c"]),
    ("pct_change", {"column": "a"}, 4, 4, 'Percentage change of "a"', ["a"]),
    ("ratio", {"numerator": "a", "denominator": "b", "target": "r"}, 4, 4, 'Ratio "a" / "b"', ["a", "b", "r"]),
    ("one_hot_encode", {"column": "a"}, 4, 4, 'One-hot encoded "a"', ["a"]),
    ("label_encode", {"column": "a"}, 4, 4, 'Label-encoded "a"', ["a"]),
    ("string_split", {"column": "a", "delimiter": ";"}, 4, 4, 'Split "a" on ";"', ["a"]),
    ("group_aggregate", {"column": "a", "group_by": "g"}, 4, 4, 'mean of "a" by "g"', ["g", "a", ""]),
    ("melt", {}, 4, 8, "Melted to long format (removed -4 rows)", []),
    ("melt", {}, 4, 4, "Melted to long format", []),
    ("pivot", {"index": "i", "columns": "c"}, 4, 2, 'Pivoted on "c"', []),
    ("insert_row", {}, 4, 5, "Inserted row at position end", []),
    ("insert_row", {"position": 1}, 4, 5, "Inserted row at position 1", []),
    ("delete_rows", {"indices": [0, 2]}, 4, 2, "Deleted 2 row(s)", []),
    ("duplicate_rows", {"indices": [1]}, 4, 5, "Duplicated 1 row(s)", []),
    ("update_cell", {"row_index": 0, "column": "a", "value": 1}, 4, 4, 'Updated cell [0, "a"]', ["a"]),
    ("reorder_columns", {"columns": ["b", "a"]}, 4, 4, "Reordered columns", ["b", "a"]),
    ("something_new", {"column": "a"}, 4, 4, "Applied something_new", ["a"]),
    ("something_new", {}, 4, 4, "Applied something_new", []),
]


@pytest.mark.parametrize(
    ("kind", "params", "before", "after", "summary", "affected"),
    _SUMMARIES,
    ids=[f"{row[0]}-{i}" for i, row in enumerate(_SUMMARIES)],
)
def test_summary_and_affected_columns(kind, params, before, after, summary, affected):
    assert ds_ops._build_summary(kind, params, before, after) == summary
    assert ds_ops._affected_columns(kind, params) == affected


def test_every_operation_kind_has_its_own_summary():
    from typing import get_args

    from latris.schema.data_actions import DataActionKind

    for kind in get_args(DataActionKind):
        assert not ds_ops._build_summary(kind, _params_for(kind), 4, 4).startswith("Applied "), kind


def _params_for(kind: str) -> dict:
    for row in _SUMMARIES:
        if row[0] == kind:
            return row[1]
    raise AssertionError(f"No summary case for {kind!r}: add one to _SUMMARIES")


class TestOperationsEndToEnd:
    """The newer transforms through ``apply_operation``: file, metadata, log, commit."""

    def test_columns_null_is_accepted(self, project: Path, sample_csv: Path) -> None:
        # Regression: {"columns": null} (as JSON sends it) passed the engine,
        # then crashed building the summary after the file had been rewritten,
        # leaving the change on disk uncommitted.
        dataset, _ = ds_ops.upload_dataset(sample_csv, root=project)
        action, _ = ds_ops.apply_operation(dataset.id, "drop_nan_rows", {"columns": None}, root=project)
        assert action.rows_after == 2
        assert action.summary.startswith("Dropped 2 NaN rows")
        assert git.run_git(["status", "--porcelain"], cwd=project).stdout.strip() == ""

    @pytest.mark.parametrize(
        ("kind", "params", "new_columns"),
        [
            ("rolling_window", {"column": "age", "window": 10}, ["age_roll10_mean"]),
            ("ratio", {"numerator": "score", "denominator": "age"}, ["score_over_age"]),
            ("group_aggregate", {"group_by": "name", "column": "score", "func": "sum"}, ["score_sum_by_name"]),
            ("string_split", {"column": "name", "delimiter": "l"}, ["name_0", "name_1"]),
            ("date_extract", {"column": "name", "parts": ["year"]}, ["name_year"]),
        ],
    )
    def test_adds_columns_and_commits(self, project, sample_csv, kind, params, new_columns) -> None:
        dataset, _ = ds_ops.upload_dataset(sample_csv, root=project)
        before = _commit_count(project)
        action, sha = ds_ops.apply_operation(dataset.id, kind, params, root=project)
        assert action.kind == kind and action.commit_sha == sha
        ds = ds_ops.get_dataset(dataset.id, root=project)
        assert set(new_columns) <= {c.name for c in ds.columns}
        assert _commit_count(project) == before + 2
        assert ds_ops.get_action_log(dataset.id, root=project).entries[-1].id == action.id

    def test_remove_outliers_end_to_end(self, project: Path, tmp_path: Path) -> None:
        csv = tmp_path / "o.csv"
        csv.write_text("v\n1\n2\n3\n2\n1000\n", encoding="utf-8", newline="")
        dataset, _ = ds_ops.upload_dataset(csv, root=project)
        action, _ = ds_ops.apply_operation(dataset.id, "remove_outliers", {"column": "v"}, root=project)
        assert (action.rows_before, action.rows_after) == (5, 4)
        assert action.summary == 'Removed 1 outliers from "v" (iqr)'

    @pytest.mark.parametrize(
        ("kind", "params"),
        [
            ("rolling_window", {"column": "age", "func": "__class__"}),
            ("ratio", {"numerator": "score"}),
            ("date_extract", {"column": "name", "parts": ["week"]}),
        ],
    )
    def test_refused_operation_changes_nothing(self, project, sample_csv, kind, params) -> None:
        dataset, _ = ds_ops.upload_dataset(sample_csv, root=project)
        file_path = project / dataset.location
        content = file_path.read_bytes()
        before = _commit_count(project)
        with pytest.raises(ValueError):
            ds_ops.apply_operation(dataset.id, kind, params, root=project)
        assert file_path.read_bytes() == content
        assert _commit_count(project) == before
        assert ds_ops.get_action_log(dataset.id, root=project).entries == []

    def test_column_stats_and_preview_after_ratio(self, project: Path, tmp_path: Path) -> None:
        csv = tmp_path / "r.csv"
        csv.write_text("a,b\n1,0\n0,0\n-1,2\n", encoding="utf-8", newline="")
        dataset, _ = ds_ops.upload_dataset(csv, root=project)
        ds_ops.apply_operation(dataset.id, "ratio", {"numerator": "a", "denominator": "b"}, root=project)
        preview = ds_ops.preview_data(dataset.id, root=project)
        assert preview["columns"] == ["a", "b", "a_over_b"]
        assert preview["rows"][1][2] is None  # 0 / 0
        stats = ds_ops.column_stats(dataset.id, "a_over_b", root=project)
        assert stats["count"] == 2 and stats["nulls"] == 1
