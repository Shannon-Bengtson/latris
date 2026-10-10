"""Pandas-based data engine for dataset operations.

Internal module — never imported above the operations layer.  Provides
DataFrame loading, saving, operation dispatch, column inference, stats
computation, and paginated preview.
"""

from __future__ import annotations

import hashlib
from contextlib import suppress
from pathlib import Path
from typing import Any

try:
    import pandas as pd
except ImportError:  # pragma: no cover
    pd = None  # type: ignore[assignment]

from latris.schema.datasets import ColumnSpec

_PANDAS_MISSING_MSG = (
    "pandas is required for data operations.  Install it with:\n"
    "  pip install 'latris[data]'\n"
    "or:\n"
    "  pip install pandas"
)


def _require_pandas() -> None:
    """Raise ImportError if pandas is not installed."""
    if pd is None:
        raise ImportError(_PANDAS_MISSING_MSG)


# ---------------------------------------------------------------------------
# Loading / saving
# ---------------------------------------------------------------------------


def load_dataframe(file_path: Path) -> pd.DataFrame:
    """Load a CSV or TSV file into a DataFrame.

    Separator is detected from the file extension (``.tsv`` / ``.tab`` → tab,
    everything else → comma).  Pandas infers dtypes naturally so that
    numeric columns saved by prior cast operations are read back as numeric.
    """
    _require_pandas()
    sep = "\t" if file_path.suffix.lower() in (".tsv", ".tab") else ","
    return pd.read_csv(file_path, sep=sep, keep_default_na=True)


def save_dataframe(df: pd.DataFrame, file_path: Path) -> None:
    """Write a DataFrame back to CSV/TSV (matching original format).

    Uses atomic write via a temp file + ``atomic_replace`` to match the
    ``yaml_io`` pattern (and inherit its Windows file-lock retry).
    """
    import os
    import tempfile

    from ..repo.yaml_io import atomic_replace

    sep = "\t" if file_path.suffix.lower() in (".tsv", ".tab") else ","
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=file_path.parent,
        suffix=file_path.suffix,
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8", newline="") as f:
            df.to_csv(f, index=False, sep=sep, lineterminator="\n")
        atomic_replace(tmp_path, file_path)
    except BaseException:
        with suppress(OSError):
            os.unlink(tmp_path)
        raise


def file_content_hash(file_path: Path) -> str:
    """Compute SHA-256 hex digest of a file's contents."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


# ---------------------------------------------------------------------------
# Column inference
# ---------------------------------------------------------------------------

_DTYPE_MAP: dict[str, str] = {
    "object": "string",
    "string": "string",
    "int64": "int64",
    "int32": "int64",
    "Int64": "int64",
    "Int32": "int64",
    "float64": "float64",
    "float32": "float64",
    "Float64": "float64",
    "Float32": "float64",
    "bool": "bool",
    "boolean": "bool",
    "datetime64[ns]": "datetime",
    "datetime64[ns, UTC]": "datetime",
    "category": "category",
}


def _map_dtype(pd_dtype: str) -> str:
    """Map a pandas dtype string to our ColumnSpec dtype literal."""
    return _DTYPE_MAP.get(str(pd_dtype), "string")


def infer_column_specs(df: pd.DataFrame) -> list[ColumnSpec]:
    """Derive a ColumnSpec list from a DataFrame's columns and dtypes."""
    _require_pandas()
    return [ColumnSpec(name=str(col), dtype=_map_dtype(str(df[col].dtype))) for col in df.columns]


# ---------------------------------------------------------------------------
# Operation handlers
# ---------------------------------------------------------------------------


def _apply_rename(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    col = params["column"]
    new_name = params["new_name"]
    if col not in df.columns:
        raise ValueError(f"Column {col!r} not found. Available: {list(df.columns)}")
    return df.rename(columns={col: new_name})


def _apply_cast(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    col = params["column"]
    target_dtype = params["dtype"]
    if col not in df.columns:
        raise ValueError(f"Column {col!r} not found. Available: {list(df.columns)}")

    dtype_map = {
        "string": "object",
        "int64": "int64",
        "float64": "float64",
        "bool": "bool",
        "datetime": "datetime64[ns]",
        "category": "category",
    }
    pd_dtype = dtype_map.get(target_dtype)
    if pd_dtype is None:
        raise ValueError(f"Unknown target dtype {target_dtype!r}")

    result = df.copy()
    if pd_dtype == "datetime64[ns]":
        result[col] = pd.to_datetime(result[col], errors="coerce")
    else:
        result[col] = result[col].astype(pd_dtype)
    return result


def _apply_drop_columns(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    columns = params["columns"]
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"Columns not found: {missing}. Available: {list(df.columns)}")
    return df.drop(columns=columns)


def _apply_drop_nan(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    columns = params.get("columns")
    how = params.get("how", "any")
    if columns:
        missing = [c for c in columns if c not in df.columns]
        if missing:
            raise ValueError(f"Columns not found: {missing}. Available: {list(df.columns)}")
    return df.dropna(subset=columns or None, how=how).reset_index(drop=True)


def _apply_fill_nan(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    col = params["column"]
    method = params["method"]
    if col not in df.columns:
        raise ValueError(f"Column {col!r} not found. Available: {list(df.columns)}")

    result = df.copy()
    if method == "backfill":
        result[col] = result[col].bfill()
    elif method == "forwardfill":
        result[col] = result[col].ffill()
    elif method == "value":
        fill_value = params.get("value")
        if fill_value is None:
            raise ValueError("fill_nan with method='value' requires a 'value' param")
        result[col] = result[col].fillna(fill_value)
    else:
        raise ValueError(f"Unknown fill method {method!r}")
    return result


def _apply_filter(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    col = params["column"]
    op = params["op"]
    value = params["value"]
    if col not in df.columns:
        raise ValueError(f"Column {col!r} not found. Available: {list(df.columns)}")

    series = df[col]
    ops = {
        "eq": lambda s, v: s == v,
        "ne": lambda s, v: s != v,
        "gt": lambda s, v: s > v,
        "lt": lambda s, v: s < v,
        "gte": lambda s, v: s >= v,
        "lte": lambda s, v: s <= v,
        "contains": lambda s, v: s.astype(str).str.contains(str(v), na=False),
        "isin": lambda s, v: s.isin(v if isinstance(v, list) else [v]),
    }
    if op not in ops:
        raise ValueError(f"Unknown filter op {op!r}. Known: {sorted(ops)}")
    mask = ops[op](series, value)
    return df[mask].reset_index(drop=True)


def _apply_sort(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    col = params["column"]
    ascending = params.get("ascending", True)
    if col not in df.columns:
        raise ValueError(f"Column {col!r} not found. Available: {list(df.columns)}")
    return df.sort_values(by=col, ascending=ascending).reset_index(drop=True)


def _apply_deduplicate(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    columns = params.get("columns")
    keep = params.get("keep", "first")
    if columns:
        missing = [c for c in columns if c not in df.columns]
        if missing:
            raise ValueError(f"Columns not found: {missing}. Available: {list(df.columns)}")
    return df.drop_duplicates(subset=columns or None, keep=keep).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Cleaning (new)
# ---------------------------------------------------------------------------


def _apply_replace_values(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    col = params["column"]
    old = params["old"]
    new = params["new"]
    if col not in df.columns:
        raise ValueError(f"Column {col!r} not found. Available: {list(df.columns)}")
    result = df.copy()
    result[col] = result[col].replace(old, new)
    return result


def _apply_strip_whitespace(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    col = params["column"]
    if col not in df.columns:
        raise ValueError(f"Column {col!r} not found. Available: {list(df.columns)}")
    result = df.copy()
    result[col] = result[col].astype(str).str.strip()
    return result


def _apply_lowercase(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    col = params["column"]
    if col not in df.columns:
        raise ValueError(f"Column {col!r} not found. Available: {list(df.columns)}")
    result = df.copy()
    result[col] = result[col].astype(str).str.lower()
    return result


def _apply_uppercase(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    col = params["column"]
    if col not in df.columns:
        raise ValueError(f"Column {col!r} not found. Available: {list(df.columns)}")
    result = df.copy()
    result[col] = result[col].astype(str).str.upper()
    return result


def _apply_clip(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    col = params["column"]
    lower = params.get("min")
    upper = params.get("max")
    if col not in df.columns:
        raise ValueError(f"Column {col!r} not found. Available: {list(df.columns)}")
    result = df.copy()
    result[col] = pd.to_numeric(result[col], errors="coerce").clip(lower=lower, upper=upper)
    return result


def _apply_remove_outliers(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    col = params["column"]
    method = params.get("method", "iqr")
    if col not in df.columns:
        raise ValueError(f"Column {col!r} not found. Available: {list(df.columns)}")
    series = pd.to_numeric(df[col], errors="coerce")
    if method == "iqr":
        q1, q3 = series.quantile(0.25), series.quantile(0.75)
        iqr = q3 - q1
        mask = series.between(q1 - 1.5 * iqr, q3 + 1.5 * iqr) | series.isna()
    elif method == "zscore":
        threshold = params.get("threshold", 3)
        z = (series - series.mean()) / series.std()
        mask = z.abs().le(threshold) | series.isna()
    else:
        raise ValueError(f"Unknown outlier method {method!r}")
    return df[mask].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Transformation
# ---------------------------------------------------------------------------


def _apply_log_transform(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    import numpy as np

    col = params["column"]
    target = params.get("target", f"{col}_log")
    if col not in df.columns:
        raise ValueError(f"Column {col!r} not found. Available: {list(df.columns)}")
    result = df.copy()
    result[target] = np.log(pd.to_numeric(result[col], errors="coerce"))
    return result


def _apply_normalize(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    col = params["column"]
    if col not in df.columns:
        raise ValueError(f"Column {col!r} not found. Available: {list(df.columns)}")
    result = df.copy()
    series = pd.to_numeric(result[col], errors="coerce")
    mn, mx = series.min(), series.max()
    result[col] = (series - mn) / (mx - mn) if mx != mn else 0.0
    return result


def _apply_standardize(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    col = params["column"]
    if col not in df.columns:
        raise ValueError(f"Column {col!r} not found. Available: {list(df.columns)}")
    result = df.copy()
    series = pd.to_numeric(result[col], errors="coerce")
    result[col] = (series - series.mean()) / series.std()
    return result


def _apply_round(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    col = params["column"]
    decimals = params.get("decimals", 2)
    if col not in df.columns:
        raise ValueError(f"Column {col!r} not found. Available: {list(df.columns)}")
    result = df.copy()
    result[col] = pd.to_numeric(result[col], errors="coerce").round(decimals)
    return result


def _apply_bin(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    col = params["column"]
    bins = params.get("bins", 5)
    labels = params.get("labels")
    target = params.get("target", f"{col}_bin")
    if col not in df.columns:
        raise ValueError(f"Column {col!r} not found. Available: {list(df.columns)}")
    result = df.copy()
    result[target] = pd.cut(
        pd.to_numeric(result[col], errors="coerce"),
        bins=bins,
        labels=labels or False,
    ).astype(str)
    return result


def _apply_rank(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    col = params["column"]
    method = params.get("method", "average")
    if col not in df.columns:
        raise ValueError(f"Column {col!r} not found. Available: {list(df.columns)}")
    result = df.copy()
    result[col] = result[col].rank(method=method)
    return result


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------


def _apply_derived_column(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    expression = params["expression"]
    target = params["target"]
    result = df.copy()
    try:
        result[target] = result.eval(expression)
    except Exception as exc:
        raise ValueError(f"Expression error: {exc}") from exc
    return result


def _apply_date_extract(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    col = params["column"]
    parts = params.get("parts", ["year", "month", "day"])
    if col not in df.columns:
        raise ValueError(f"Column {col!r} not found. Available: {list(df.columns)}")
    result = df.copy()
    dt = pd.to_datetime(result[col], errors="coerce")
    for part in parts:
        if part == "year":
            result[f"{col}_year"] = dt.dt.year
        elif part == "month":
            result[f"{col}_month"] = dt.dt.month
        elif part == "day":
            result[f"{col}_day"] = dt.dt.day
        elif part == "dayofweek":
            result[f"{col}_dayofweek"] = dt.dt.dayofweek
        elif part == "quarter":
            result[f"{col}_quarter"] = dt.dt.quarter
        elif part == "hour":
            result[f"{col}_hour"] = dt.dt.hour
    return result


def _apply_lag_lead(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    col = params["column"]
    periods = params.get("periods", 1)
    target = params.get("target", f"{col}_lag{periods}")
    if col not in df.columns:
        raise ValueError(f"Column {col!r} not found. Available: {list(df.columns)}")
    result = df.copy()
    result[target] = result[col].shift(periods)
    return result


def _apply_rolling_window(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    col = params["column"]
    window = params.get("window", 3)
    func = params.get("func", "mean")
    target = params.get("target", f"{col}_roll{window}_{func}")
    if col not in df.columns:
        raise ValueError(f"Column {col!r} not found. Available: {list(df.columns)}")
    result = df.copy()
    series = pd.to_numeric(result[col], errors="coerce")
    roller = series.rolling(window=window, min_periods=1)
    result[target] = getattr(roller, func)()
    return result


def _apply_difference(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    col = params["column"]
    periods = params.get("periods", 1)
    target = params.get("target", f"{col}_diff{periods}")
    if col not in df.columns:
        raise ValueError(f"Column {col!r} not found. Available: {list(df.columns)}")
    result = df.copy()
    result[target] = pd.to_numeric(result[col], errors="coerce").diff(periods)
    return result


def _apply_cumulative_sum(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    col = params["column"]
    target = params.get("target", f"{col}_cumsum")
    if col not in df.columns:
        raise ValueError(f"Column {col!r} not found. Available: {list(df.columns)}")
    result = df.copy()
    result[target] = pd.to_numeric(result[col], errors="coerce").cumsum()
    return result


def _apply_pct_change(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    col = params["column"]
    target = params.get("target", f"{col}_pct")
    if col not in df.columns:
        raise ValueError(f"Column {col!r} not found. Available: {list(df.columns)}")
    result = df.copy()
    result[target] = pd.to_numeric(result[col], errors="coerce").pct_change()
    return result


def _apply_ratio(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    numerator = params["numerator"]
    denominator = params["denominator"]
    target = params.get("target", f"{numerator}_over_{denominator}")
    for c in [numerator, denominator]:
        if c not in df.columns:
            raise ValueError(f"Column {c!r} not found. Available: {list(df.columns)}")
    result = df.copy()
    result[target] = pd.to_numeric(result[numerator], errors="coerce") / pd.to_numeric(
        result[denominator], errors="coerce"
    )
    return result


def _apply_one_hot(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    col = params["column"]
    if col not in df.columns:
        raise ValueError(f"Column {col!r} not found. Available: {list(df.columns)}")
    return pd.get_dummies(df, columns=[col], prefix=col, dtype=int)


def _apply_label_encode(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    col = params["column"]
    if col not in df.columns:
        raise ValueError(f"Column {col!r} not found. Available: {list(df.columns)}")
    result = df.copy()
    result[col] = result[col].astype("category").cat.codes
    return result


def _apply_string_split(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    col = params["column"]
    delimiter = params.get("delimiter", ",")
    max_splits = params.get("max_splits", -1)
    if col not in df.columns:
        raise ValueError(f"Column {col!r} not found. Available: {list(df.columns)}")
    result = df.copy()
    splits = result[col].astype(str).str.split(delimiter, n=max_splits if max_splits > 0 else -1, expand=True)
    for i in range(splits.shape[1]):
        result[f"{col}_{i}"] = splits[i]
    return result


def _apply_group_aggregate(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    group_col = params["group_by"]
    value_col = params["column"]
    func = params.get("func", "mean")
    target = params.get("target", f"{value_col}_{func}_by_{group_col}")
    for c in [group_col, value_col]:
        if c not in df.columns:
            raise ValueError(f"Column {c!r} not found. Available: {list(df.columns)}")
    result = df.copy()
    agg = result.groupby(group_col)[value_col].transform(func)
    result[target] = agg
    return result


# ---------------------------------------------------------------------------
# Reshaping
# ---------------------------------------------------------------------------


def _apply_melt(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    id_vars = params.get("id_vars", [])
    value_vars = params.get("value_vars")
    var_name = params.get("var_name", "variable")
    value_name = params.get("value_name", "value")
    return pd.melt(
        df,
        id_vars=id_vars or None,
        value_vars=value_vars or None,
        var_name=var_name,
        value_name=value_name,
    )


def _apply_pivot(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    index = params["index"]
    columns_param = params["columns"]
    values = params.get("values")
    result = df.pivot_table(
        index=index,
        columns=columns_param,
        values=values or None,
        aggfunc=params.get("aggfunc", "first"),
    ).reset_index()
    # Flatten multi-level column names
    if hasattr(result.columns, "levels"):
        result.columns = ["_".join(str(c) for c in col).strip("_") for col in result.columns.values]
    return result


# ---------------------------------------------------------------------------
# Row operations
# ---------------------------------------------------------------------------


def _apply_insert_row(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Insert a new row at a given position.  Values default to NaN."""
    position = params.get("position", len(df))
    values = params.get("values", {})
    if position < 0 or position > len(df):
        raise ValueError(f"Position {position} out of range. DataFrame has {len(df)} rows.")
    new_row = {col: values.get(col, pd.NA) for col in df.columns}
    top = df.iloc[:position]
    bottom = df.iloc[position:]
    inserted = pd.DataFrame([new_row], columns=df.columns)
    return pd.concat([top, inserted, bottom], ignore_index=True)


def _apply_delete_rows(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Delete rows by positional index."""
    indices = params["indices"]
    if not indices:
        raise ValueError("No row indices provided")
    invalid = [i for i in indices if i < 0 or i >= len(df)]
    if invalid:
        raise ValueError(f"Row indices out of range: {invalid}. DataFrame has {len(df)} rows.")
    return df.drop(df.index[indices]).reset_index(drop=True)


def _apply_duplicate_rows(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Duplicate selected rows, inserting copies immediately after each."""
    indices = params["indices"]
    if not indices:
        raise ValueError("No row indices provided")
    invalid = [i for i in indices if i < 0 or i >= len(df)]
    if invalid:
        raise ValueError(f"Row indices out of range: {invalid}. DataFrame has {len(df)} rows.")
    parts: list[pd.DataFrame] = []
    sorted_indices = sorted(set(indices))
    prev = 0
    for idx in sorted_indices:
        parts.append(df.iloc[prev : idx + 1])
        parts.append(df.iloc[[idx]])
        prev = idx + 1
    parts.append(df.iloc[prev:])
    return pd.concat(parts, ignore_index=True)


def _apply_update_cell(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Update a single cell by positional row index and column name."""
    row_index = params["row_index"]
    column = params["column"]
    value = params["value"]

    if row_index < 0 or row_index >= len(df):
        raise ValueError(f"Row index {row_index} out of range. DataFrame has {len(df)} rows.")
    if column not in df.columns:
        raise ValueError(f"Column {column!r} not found. Available: {list(df.columns)}")

    result = df.copy()
    col_loc = result.columns.get_loc(column)

    if value == "" or value is None:
        result.iloc[row_index, col_loc] = pd.NA
    else:
        col_dtype = result[column].dtype
        try:
            if pd.api.types.is_numeric_dtype(col_dtype):
                coerced = pd.to_numeric(value, errors="raise")
            elif pd.api.types.is_bool_dtype(col_dtype):
                coerced = str(value).lower() in ("true", "1", "yes")
            elif pd.api.types.is_datetime64_any_dtype(col_dtype):
                coerced = pd.to_datetime(value, errors="raise")
            else:
                coerced = str(value)
        except (ValueError, TypeError):
            coerced = str(value)
        result.iloc[row_index, col_loc] = coerced
    return result


def _apply_reorder_columns(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Reorder columns to match the given order."""
    new_order = params["columns"]
    missing = [c for c in new_order if c not in df.columns]
    if missing:
        raise ValueError(f"Columns not in DataFrame: {missing}")
    extra = [c for c in df.columns if c not in new_order]
    if extra:
        raise ValueError(f"Columns missing from new order: {extra}")
    if len(new_order) != len(df.columns):
        raise ValueError(f"Column count mismatch: got {len(new_order)}, expected {len(df.columns)}")
    return df[new_order]


_HANDLERS: dict[str, Any] = {
    # Cleaning
    "rename_column": _apply_rename,
    "cast_column": _apply_cast,
    "drop_columns": _apply_drop_columns,
    "drop_nan_rows": _apply_drop_nan,
    "fill_nan": _apply_fill_nan,
    "filter_rows": _apply_filter,
    "sort_rows": _apply_sort,
    "deduplicate": _apply_deduplicate,
    "replace_values": _apply_replace_values,
    "strip_whitespace": _apply_strip_whitespace,
    "lowercase": _apply_lowercase,
    "uppercase": _apply_uppercase,
    "clip_values": _apply_clip,
    "remove_outliers": _apply_remove_outliers,
    # Transformation
    "log_transform": _apply_log_transform,
    "normalize": _apply_normalize,
    "standardize": _apply_standardize,
    "round_values": _apply_round,
    "bin_discretize": _apply_bin,
    "rank_transform": _apply_rank,
    # Feature engineering
    "derived_column": _apply_derived_column,
    "date_extract": _apply_date_extract,
    "lag_lead": _apply_lag_lead,
    "rolling_window": _apply_rolling_window,
    "difference": _apply_difference,
    "cumulative_sum": _apply_cumulative_sum,
    "pct_change": _apply_pct_change,
    "ratio": _apply_ratio,
    "one_hot_encode": _apply_one_hot,
    "label_encode": _apply_label_encode,
    "string_split": _apply_string_split,
    "group_aggregate": _apply_group_aggregate,
    # Reshaping
    "melt": _apply_melt,
    "pivot": _apply_pivot,
    # Row operations
    "insert_row": _apply_insert_row,
    "delete_rows": _apply_delete_rows,
    "duplicate_rows": _apply_duplicate_rows,
    # Cell editing
    "update_cell": _apply_update_cell,
    # Column reorder
    "reorder_columns": _apply_reorder_columns,
}


def execute_operation(
    df: pd.DataFrame,
    kind: str,
    params: dict,
) -> pd.DataFrame:
    """Apply a single operation to a DataFrame.  Raises ValueError on failure."""
    _require_pandas()
    handler = _HANDLERS.get(kind)
    if handler is None:
        raise ValueError(f"Unknown operation kind {kind!r}. Known: {sorted(_HANDLERS)}")
    return handler(df, params)


# ---------------------------------------------------------------------------
# Stats & pagination
# ---------------------------------------------------------------------------


def compute_column_stats(df: pd.DataFrame, column: str) -> dict[str, Any]:
    """Compute summary statistics for a single column."""
    _require_pandas()
    if column not in df.columns:
        raise ValueError(f"Column {column!r} not found. Available: {list(df.columns)}")

    series = df[column]
    stats: dict[str, Any] = {
        "name": column,
        "dtype": _map_dtype(str(series.dtype)),
        "count": int(series.count()),
        "nulls": int(series.isna().sum()),
        "total": len(series),
        "unique": int(series.nunique()),
    }

    if pd.api.types.is_numeric_dtype(series):
        stats["min"] = series.min() if not series.empty else None
        stats["max"] = series.max() if not series.empty else None
        stats["mean"] = series.mean() if not series.empty else None
        stats["std"] = series.std() if not series.empty else None

    return stats


def compute_correlations(
    df: pd.DataFrame,
    columns: list[str] | None = None,
    method: str = "pearson",
    threshold: float = 0.3,
) -> list[dict[str, Any]]:
    """Compute pairwise correlations between numeric columns.

    Parameters
    ----------
    df:
        DataFrame to analyse.
    columns:
        Subset of columns to include.  ``None`` means all numeric columns.
    method:
        Correlation method: ``"pearson"``, ``"spearman"``, or ``"kendall"``.
    threshold:
        Minimum absolute correlation to include in results.

    Returns a list of ``{col_a, col_b, coefficient, p_value, method}`` dicts,
    sorted by descending absolute coefficient.
    """
    _require_pandas()
    from scipy import stats as sp_stats

    numeric = df.select_dtypes(include="number")
    if columns is not None:
        valid = [c for c in columns if c in numeric.columns]
        numeric = numeric[valid]

    if numeric.shape[1] < 2:
        return []

    col_names = list(numeric.columns)
    results: list[dict[str, Any]] = []

    for i in range(len(col_names)):
        for j in range(i + 1, len(col_names)):
            a = numeric[col_names[i]].dropna()
            b = numeric[col_names[j]].dropna()
            # Align on shared non-null indices.
            shared = a.index.intersection(b.index)
            if len(shared) < 3:
                continue
            a_shared = a.loc[shared]
            b_shared = b.loc[shared]

            if method == "spearman":
                r, p = sp_stats.spearmanr(a_shared, b_shared)
            elif method == "kendall":
                r, p = sp_stats.kendalltau(a_shared, b_shared)
            else:
                r, p = sp_stats.pearsonr(a_shared, b_shared)

            if abs(r) >= threshold:
                results.append(
                    {
                        "col_a": col_names[i],
                        "col_b": col_names[j],
                        "coefficient": round(float(r), 4),
                        "p_value": round(float(p), 6),
                        "method": method,
                    }
                )

    results.sort(key=lambda x: abs(x["coefficient"]), reverse=True)
    return results


def dataframe_to_page(
    df: pd.DataFrame,
    offset: int = 0,
    limit: int = 100,
) -> dict[str, Any]:
    """Slice a DataFrame for JSON-safe transmission to the GUI."""
    _require_pandas()
    total = len(df)
    page = df.iloc[offset : offset + limit]

    # Convert to Python-native types for JSON serialisation.
    rows: list[list[Any]] = []
    for _, row in page.iterrows():
        rows.append([None if pd.isna(v) else v for v in row.tolist()])

    return {
        "columns": [str(c) for c in df.columns],
        "rows": rows,
        "total_rows": total,
        "offset": offset,
        "limit": limit,
    }
