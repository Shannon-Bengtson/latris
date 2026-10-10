"""Dataset mutations — upload, operations, versioning.

Every mutating function auto-commits.  Data operations modify the CSV/TSV
file directly (mutable data model), and an action log records what was
done for audit.  Versioning creates named snapshots; restore checks out
the file from a previous commit.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from latris.operations._data_engine import (
    compute_column_stats as _compute_stats,
)
from latris.operations._data_engine import (
    dataframe_to_page,
    execute_operation,
    file_content_hash,
    infer_column_specs,
    load_dataframe,
    save_dataframe,
)
from latris.operations.commit import auto_commit
from latris.repo import git
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_model, load_model
from latris.schema import (
    DataAction,
    DataActionLog,
    Dataset,
    DatasetLibrary,
    DatasetVersion,
    DatasetVersionLibrary,
    new_id,
)
from latris.schema.data_actions import DataActionKind

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_datasets(root: Path | None) -> tuple:
    paths = require_project(root)
    if paths.data_datasets_yaml.exists():
        library = load_model(DatasetLibrary, paths.data_datasets_yaml)
    else:
        library = DatasetLibrary()
    return paths, library


def _find_dataset(library: DatasetLibrary, query: str) -> Dataset:
    """Resolve a dataset by ID or name (case-insensitive)."""
    for ds in library.entries:
        if ds.id == query:
            return ds
    for ds in library.entries:
        if ds.name.lower() == query.lower():
            return ds
    # Try ID prefix (min 4 chars after 'dataset_')
    if query.startswith("dataset_") and len(query) >= 12:
        matches = [ds for ds in library.entries if ds.id.startswith(query)]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ValueError(f"Ambiguous dataset prefix {query!r}: {[d.id for d in matches]}")
    raise ValueError(f"Dataset not found: {query!r}")


def _load_action_log(paths, dataset_id: str) -> DataActionLog:
    log_path = paths.data_action_log(dataset_id)
    if log_path.exists():
        return load_model(DataActionLog, log_path)
    return DataActionLog(dataset_id=dataset_id)


def _load_versions(paths) -> DatasetVersionLibrary:
    if paths.data_versions_yaml.exists():
        return load_model(DatasetVersionLibrary, paths.data_versions_yaml)
    return DatasetVersionLibrary()


# ---------------------------------------------------------------------------
# Dataset lifecycle
# ---------------------------------------------------------------------------


def list_datasets(root: Path | None = None) -> list[Dataset]:
    """List all registered datasets."""
    _, library = _load_datasets(root)
    return list(library.entries)


def get_dataset(query: str, root: Path | None = None) -> Dataset:
    """Get a dataset by ID or name."""
    _, library = _load_datasets(root)
    return _find_dataset(library, query)


def upload_dataset(
    file_path: Path,
    *,
    name: str | None = None,
    description: str = "",
    root: Path | None = None,
) -> tuple[Dataset, str]:
    """Import a CSV/TSV file into the project.

    1. Copy file to ``data/files/<name>.<ext>``
    2. Compute content hash
    3. Read with pandas to extract columns, dtypes, row count
    4. Create Dataset entry with ColumnSpec list
    5. Create empty DataActionLog
    6. Auto-commit everything
    """
    paths, library = _load_datasets(root)

    file_path = Path(file_path).resolve()
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    ext = file_path.suffix.lower()
    if ext not in (".csv", ".tsv", ".tab"):
        raise ValueError(f"Unsupported file type {ext!r}. Use .csv or .tsv")

    dataset_name = name or file_path.stem

    # Check for name collision
    for existing in library.entries:
        if existing.name == dataset_name:
            raise ValueError(f"Dataset named {dataset_name!r} already exists (id: {existing.id})")

    # Copy file into project
    dest = paths.data_files_dir / f"{dataset_name}{ext}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(file_path, dest)

    # Read with pandas for metadata
    df = load_dataframe(dest)
    columns = infer_column_specs(df)
    content_hash = file_content_hash(dest)

    dataset_id = new_id("dataset")
    dataset = Dataset(
        id=dataset_id,
        name=dataset_name,
        description=description,
        source_type="file",
        location=f"data/files/{dataset_name}{ext}",
        schema_info={"columns": [c.name for c in columns]},
        rows=len(df),
        columns=columns,
        storage_policy="committed",
    )
    library.entries.append(dataset)

    # Create empty action log
    action_log = DataActionLog(dataset_id=dataset_id)

    dump_model(library, paths.data_datasets_yaml)
    dump_model(action_log, paths.data_action_log(dataset_id))

    sha = auto_commit(
        paths.root,
        subject=f'Uploaded dataset "{dataset_name}" ({len(df)} rows, {len(columns)} columns)',
        body=f"id: {dataset_id}\nfile: {dest.name}",
        paths=[dest, paths.data_datasets_yaml, paths.data_action_log(dataset_id)],
    )

    # Auto-create initial version so there's always a restore point.
    version = DatasetVersion(
        id=new_id("data-version"),
        dataset_id=dataset_id,
        name="uploaded",
        description="As uploaded, before any operations",
        commit_sha=sha,
        content_hash=content_hash,
        row_count=len(df),
        column_count=len(columns),
        column_names=[c.name for c in columns],
    )
    versions = _load_versions(paths)
    versions.entries.append(version)
    dump_model(versions, paths.data_versions_yaml)
    auto_commit(
        paths.root,
        subject=f'Auto-versioned dataset "{dataset_name}" as "uploaded"',
        paths=[paths.data_versions_yaml],
    )

    return dataset, sha


def remove_dataset(
    query: str,
    *,
    root: Path | None = None,
) -> tuple[Dataset, str]:
    """Remove a dataset, its action log, and its versions.

    The raw file under ``data/files/`` is **not** deleted (git history
    preserves it, and it may be referenced by past analysis runs).
    """
    paths, library = _load_datasets(root)
    dataset = _find_dataset(library, query)

    library.entries = [ds for ds in library.entries if ds.id != dataset.id]
    dump_model(library, paths.data_datasets_yaml)

    # Remove action log file if present
    action_log_path = paths.data_action_log(dataset.id)
    touched: list[Path] = [paths.data_datasets_yaml]
    if action_log_path.exists():
        action_log_path.unlink()
        touched.append(action_log_path)

    # Remove versions for this dataset
    versions = _load_versions(paths)
    versions.entries = [v for v in versions.entries if v.dataset_id != dataset.id]
    dump_model(versions, paths.data_versions_yaml)
    touched.append(paths.data_versions_yaml)

    sha = auto_commit(
        paths.root,
        subject=f'Removed dataset "{dataset.name}"',
        body=f"id: {dataset.id}",
        paths=touched,
    )
    return dataset, sha


# ---------------------------------------------------------------------------
# Data operations (mutate file + log action)
# ---------------------------------------------------------------------------


def apply_operation(
    dataset_id: str,
    kind: DataActionKind,
    params: dict,
    *,
    root: Path | None = None,
) -> tuple[DataAction, str]:
    """Apply a data operation to a dataset's file.

    1. Load the CSV into a DataFrame
    2. Apply the operation
    3. Write the modified DataFrame back
    4. Update column metadata on the Dataset entry
    5. Log the action
    6. Auto-commit everything
    """
    paths, library = _load_datasets(root)
    dataset = _find_dataset(library, dataset_id)

    file_path = paths.root / dataset.location
    df = load_dataframe(file_path)
    rows_before = len(df)

    # Apply the operation (raises ValueError on failure)
    df = execute_operation(df, kind, params)
    rows_after = len(df)

    # Write modified file back
    save_dataframe(df, file_path)

    # Update dataset metadata
    dataset.columns = infer_column_specs(df)
    dataset.rows = rows_after
    dataset.schema_info = {"columns": [c.name for c in dataset.columns]}
    dump_model(library, paths.data_datasets_yaml)

    # Build summary
    summary = _build_summary(kind, params, rows_before, rows_after)
    columns_affected = _affected_columns(kind, params)

    # Log the action
    action_log = _load_action_log(paths, dataset.id)
    action = DataAction(
        id=new_id("data-action"),
        dataset_id=dataset.id,
        kind=kind,
        params=params,
        summary=summary,
        rows_before=rows_before,
        rows_after=rows_after,
        columns_affected=columns_affected,
    )
    action_log.entries.append(action)
    dump_model(action_log, paths.data_action_log(dataset.id))

    sha = auto_commit(
        paths.root,
        subject=f'{summary} in "{dataset.name}"',
        body=f"dataset: {dataset.id}\naction: {action.id}",
        paths=[file_path, paths.data_datasets_yaml, paths.data_action_log(dataset.id)],
    )

    # Backfill commit SHA
    action.commit_sha = sha
    dump_model(action_log, paths.data_action_log(dataset.id))
    # Stage the updated action log (commit SHA backfill is cosmetic, amend not needed)
    auto_commit(
        paths.root,
        subject=f"Record commit SHA for action {action.id}",
        paths=[paths.data_action_log(dataset.id)],
    )

    return action, sha


def _build_summary(kind: str, params: dict, rows_before: int, rows_after: int) -> str:
    """Build a human-readable summary of a data operation."""
    diff = rows_before - rows_after
    col = params.get("column", "")
    match kind:
        # Cleaning
        case "rename_column":
            return f'Renamed column "{col}" to "{params["new_name"]}"'
        case "cast_column":
            return f'Cast column "{col}" to {params["dtype"]}'
        case "drop_columns":
            cols = ", ".join(f'"{c}"' for c in params["columns"])
            return f"Dropped columns {cols}"
        case "drop_nan_rows":
            cols = ", ".join(f'"{c}"' for c in params.get("columns", ["all"]))
            return f"Dropped {diff} NaN rows (columns: {cols})"
        case "fill_nan":
            return f'Filled NaN in "{col}" ({params["method"]})'
        case "filter_rows":
            return f'Filtered rows: "{col}" {params["op"]} {params["value"]} (removed {diff})'
        case "sort_rows":
            direction = "ascending" if params.get("ascending", True) else "descending"
            return f'Sorted by "{col}" ({direction})'
        case "deduplicate":
            return f"Deduplicated (removed {diff} rows)"
        case "replace_values":
            return f'Replaced "{params["old"]}" with "{params["new"]}" in "{col}"'
        case "strip_whitespace":
            return f'Stripped whitespace from "{col}"'
        case "lowercase":
            return f'Lowercased "{col}"'
        case "uppercase":
            return f'Uppercased "{col}"'
        case "clip_values":
            return f'Clipped "{col}" to [{params.get("min", "")}, {params.get("max", "")}]'
        case "remove_outliers":
            return f'Removed {diff} outliers from "{col}" ({params.get("method", "iqr")})'
        # Transformation
        case "log_transform":
            return f'Log-transformed "{col}"'
        case "normalize":
            return f'Normalized "{col}" (min-max)'
        case "standardize":
            return f'Standardized "{col}" (z-score)'
        case "round_values":
            return f'Rounded "{col}" to {params.get("decimals", 2)} decimals'
        case "bin_discretize":
            return f'Binned "{col}" into {params.get("bins", 5)} bins'
        case "rank_transform":
            return f'Ranked "{col}"'
        # Feature engineering
        case "derived_column":
            return f'Created column "{params["target"]}" = {params["expression"]}'
        case "date_extract":
            parts = ", ".join(params.get("parts", ["year", "month", "day"]))
            return f'Extracted {parts} from "{col}"'
        case "lag_lead":
            return f'Created lag({params.get("periods", 1)}) of "{col}"'
        case "rolling_window":
            return f'Rolling {params.get("func", "mean")}({params.get("window", 3)}) of "{col}"'
        case "difference":
            return f'Differenced "{col}" (periods={params.get("periods", 1)})'
        case "cumulative_sum":
            return f'Cumulative sum of "{col}"'
        case "pct_change":
            return f'Percentage change of "{col}"'
        case "ratio":
            return f'Ratio "{params["numerator"]}" / "{params["denominator"]}"'
        case "one_hot_encode":
            return f'One-hot encoded "{col}"'
        case "label_encode":
            return f'Label-encoded "{col}"'
        case "string_split":
            return f'Split "{col}" on "{params.get("delimiter", ",")}"'
        case "group_aggregate":
            return f'{params.get("func", "mean")} of "{col}" by "{params["group_by"]}"'
        # Reshaping
        case "melt":
            return f"Melted to long format (removed {diff} rows)" if diff else "Melted to long format"
        case "pivot":
            return f'Pivoted on "{params["columns"]}"'
        # Row operations
        case "insert_row":
            pos = params.get("position", "end")
            return f"Inserted row at position {pos}"
        case "delete_rows":
            count = len(params.get("indices", []))
            return f"Deleted {count} row(s)"
        case "duplicate_rows":
            count = len(params.get("indices", []))
            return f"Duplicated {count} row(s)"
        # Cell editing
        case "update_cell":
            return f'Updated cell [{params["row_index"]}, "{params["column"]}"]'
        # Column reorder
        case "reorder_columns":
            return "Reordered columns"
        case _:
            return f"Applied {kind}"


def _affected_columns(kind: str, params: dict) -> list[str]:
    """Extract affected column names from operation params."""
    col = params.get("column", "")
    match kind:
        case "rename_column":
            return [col, params["new_name"]]
        case (
            "cast_column"
            | "fill_nan"
            | "filter_rows"
            | "sort_rows"
            | "strip_whitespace"
            | "lowercase"
            | "uppercase"
            | "clip_values"
            | "remove_outliers"
            | "replace_values"
            | "normalize"
            | "standardize"
            | "round_values"
            | "rank_transform"
            | "label_encode"
            | "one_hot_encode"
        ):
            return [col] if col else []
        case "log_transform" | "lag_lead" | "rolling_window" | "difference" | "cumulative_sum" | "pct_change":
            result = [col] if col else []
            if "target" in params:
                result.append(params["target"])
            return result
        case "bin_discretize" | "date_extract":
            result = [col] if col else []
            if "target" in params:
                result.append(params["target"])
            return result
        case "derived_column":
            return [params.get("target", "")]
        case "ratio":
            return [params.get("numerator", ""), params.get("denominator", ""), params.get("target", "")]
        case "string_split":
            return [col] if col else []
        case "group_aggregate":
            return [params.get("group_by", ""), col, params.get("target", "")]
        case "drop_columns":
            return list(params["columns"])
        case "drop_nan_rows" | "deduplicate":
            return list(params.get("columns", []))
        case "insert_row" | "delete_rows" | "duplicate_rows":
            return []
        case "update_cell":
            return [params.get("column", "")]
        case "reorder_columns":
            return list(params.get("columns", []))
        case _:
            return [col] if col else []


# ---------------------------------------------------------------------------
# Column metadata (no CSV mutation)
# ---------------------------------------------------------------------------


def update_column_metadata(
    dataset_id: str,
    column_name: str,
    *,
    role: str | None = ...,  # type: ignore[assignment]
    description: str | None = ...,  # type: ignore[assignment]
    root: Path | None = None,
) -> tuple[Dataset, str]:
    """Update metadata (role, description) on a column.  Does not modify the CSV."""
    paths, library = _load_datasets(root)
    dataset = _find_dataset(library, dataset_id)

    col = None
    for c in dataset.columns:
        if c.name == column_name:
            col = c
            break
    if col is None:
        raise ValueError(
            f"Column {column_name!r} not found in dataset {dataset.name!r}. "
            f"Available: {[c.name for c in dataset.columns]}"
        )

    if role is not ...:
        col.role = role  # type: ignore[assignment]
    if description is not ...:
        col.description = description

    dump_model(library, paths.data_datasets_yaml)
    sha = auto_commit(
        paths.root,
        subject=f'Updated column "{column_name}" metadata in "{dataset.name}"',
        paths=[paths.data_datasets_yaml],
    )
    return dataset, sha


# ---------------------------------------------------------------------------
# Versioning
# ---------------------------------------------------------------------------


def version_dataset(
    dataset_id: str,
    name: str,
    *,
    description: str = "",
    root: Path | None = None,
) -> tuple[DatasetVersion, str]:
    """Create a named version (snapshot) of a dataset."""
    paths, library = _load_datasets(root)
    dataset = _find_dataset(library, dataset_id)

    file_path = paths.root / dataset.location
    content_hash = file_content_hash(file_path)
    head = git.head_sha(paths.root)

    version = DatasetVersion(
        id=new_id("data-version"),
        dataset_id=dataset.id,
        name=name,
        description=description,
        commit_sha=head,
        content_hash=content_hash,
        row_count=dataset.rows or 0,
        column_count=len(dataset.columns),
        column_names=[c.name for c in dataset.columns],
    )

    versions = _load_versions(paths)
    versions.entries.append(version)
    dump_model(versions, paths.data_versions_yaml)

    sha = auto_commit(
        paths.root,
        subject=f'Versioned dataset "{dataset.name}" as "{name}"',
        body=f"dataset: {dataset.id}\nversion: {version.id}\ncommit: {head}",
        paths=[paths.data_versions_yaml],
    )
    return version, sha


def list_versions(
    dataset_id: str,
    root: Path | None = None,
) -> list[DatasetVersion]:
    """List all versions for a dataset."""
    paths = require_project(root)
    versions = _load_versions(paths)
    return [v for v in versions.entries if v.dataset_id == dataset_id]


def restore_version(
    dataset_id: str,
    version_id: str,
    *,
    root: Path | None = None,
) -> tuple[Dataset, str]:
    """Restore a dataset to a previously versioned state.

    Checks out the file from the version's commit SHA and writes it
    as a new commit.
    """
    paths, library = _load_datasets(root)
    dataset = _find_dataset(library, dataset_id)
    versions = _load_versions(paths)

    version = None
    for v in versions.entries:
        if v.id == version_id:
            version = v
            break
    if version is None:
        raise ValueError(f"Version {version_id!r} not found")
    if version.dataset_id != dataset.id:
        raise ValueError(f"Version {version_id!r} belongs to a different dataset")

    # Retrieve file content from the version's commit
    rel_path = dataset.location
    old_content = git.show_file(paths.root, version.commit_sha, rel_path)

    # Write restored content
    file_path = paths.root / dataset.location
    file_path.write_text(old_content, encoding="utf-8", newline="")

    # Re-read with pandas to update metadata
    df = load_dataframe(file_path)
    dataset.columns = infer_column_specs(df)
    dataset.rows = len(df)
    dataset.schema_info = {"columns": [c.name for c in dataset.columns]}
    dump_model(library, paths.data_datasets_yaml)

    sha = auto_commit(
        paths.root,
        subject=f'Restored dataset "{dataset.name}" to version "{version.name}"',
        body=f"dataset: {dataset.id}\nversion: {version.id}\nfrom commit: {version.commit_sha}",
        paths=[file_path, paths.data_datasets_yaml],
    )
    return dataset, sha


# ---------------------------------------------------------------------------
# Read-only: preview and stats
# ---------------------------------------------------------------------------


def preview_data(
    dataset_id: str,
    *,
    offset: int = 0,
    limit: int = 100,
    root: Path | None = None,
) -> dict:
    """Return a paginated preview of a dataset's current state."""
    paths, library = _load_datasets(root)
    dataset = _find_dataset(library, dataset_id)
    file_path = paths.root / dataset.location
    df = load_dataframe(file_path)
    return dataframe_to_page(df, offset, limit)


def column_stats(
    dataset_id: str,
    column_name: str,
    *,
    root: Path | None = None,
) -> dict:
    """Compute summary statistics for a single column."""
    paths, library = _load_datasets(root)
    dataset = _find_dataset(library, dataset_id)
    file_path = paths.root / dataset.location
    df = load_dataframe(file_path)
    return _compute_stats(df, column_name)


def get_action_log(
    dataset_id: str,
    root: Path | None = None,
) -> DataActionLog:
    """Return the full action log for a dataset."""
    paths = require_project(root)
    return _load_action_log(paths, dataset_id)
