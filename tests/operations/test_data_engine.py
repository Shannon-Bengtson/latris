"""Tests for the pandas data engine — every operation handler, dispatch,
loading/saving, stats, correlations and paging.

Tested directly against DataFrames (no project, no git): each handler is a
pure DataFrame -> DataFrame function. The end-to-end path through
``datasets.apply_operation`` is covered in ``test_datasets.py`` and, for every
operation kind's summary, below.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from latris.operations import _data_engine as engine
from latris.operations._data_engine import (
    compute_column_stats,
    compute_correlations,
    dataframe_to_page,
    execute_operation,
    file_content_hash,
    infer_column_specs,
    load_dataframe,
    save_dataframe,
)


def _vals(series: pd.Series) -> list:
    """Series values with NaN/NA as None, for easy comparison."""
    return [None if pd.isna(v) else v for v in series.tolist()]


@pytest.fixture
def df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "x": [1.0, 2.0, np.nan, 4.0, 100.0],
            "g": ["a", "a", "b", "b", None],
            "s": ["a,b", "c", None, "d,e,f", "g"],
        }
    )


@pytest.fixture
def empty() -> pd.DataFrame:
    return pd.DataFrame({"x": pd.Series([], dtype=float), "g": pd.Series([], dtype=object)})


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


class TestDispatch:
    def test_unknown_kind_names_the_known_ones(self, df):
        with pytest.raises(ValueError, match="Unknown operation kind 'nope'.*rename_column"):
            execute_operation(df, "nope", {})

    def test_every_schema_kind_has_a_handler(self):
        from typing import get_args

        from latris.schema.data_actions import DataActionKind

        assert set(get_args(DataActionKind)) <= set(engine._HANDLERS)

    @pytest.mark.parametrize(
        ("kind", "params"),
        [
            ("ratio", {"numerator": "x"}),
            ("rename_column", {"column": "x"}),
            ("filter_rows", {"column": "x", "op": "eq"}),
            ("group_aggregate", {"column": "x"}),
            ("pivot", {"index": "x", "columns": "nope"}),
            ("melt", {"id_vars": ["nope"]}),
        ],
    )
    def test_missing_param_or_column_is_a_value_error(self, df, kind, params):
        # A raw KeyError would reach the server as 404 "not found".
        with pytest.raises(ValueError, match=f"{kind}: missing a required parameter or column"):
            execute_operation(df, kind, params)

    @pytest.mark.parametrize(
        ("kind", "params"),
        [
            ("filter_rows", {"column": "m", "op": "gt", "value": 0}),
            ("sort_rows", {"column": "m"}),
            ("group_aggregate", {"group_by": "k", "column": "m", "func": "mean"}),
        ],
    )
    def test_wrong_dtype_is_a_value_error(self, kind, params):
        mixed = pd.DataFrame({"m": ["a", 1, "b"], "k": [1, 1, 2]})
        with pytest.raises(ValueError, match=f"{kind} can't run on this data"):
            execute_operation(mixed, kind, params)

    def test_handler_value_error_passes_through_unchanged(self, df):
        with pytest.raises(ValueError, match="^Column 'nope' not found"):
            execute_operation(df, "sort_rows", {"column": "nope"})

    def test_input_frame_is_not_mutated(self, df):
        before = df.copy()
        for kind, params in [
            ("normalize", {"column": "x"}),
            ("rolling_window", {"column": "x"}),
            ("date_extract", {"column": "g", "parts": ["year"]}),
            ("string_split", {"column": "s"}),
        ]:
            execute_operation(df, kind, params)
        pd.testing.assert_frame_equal(df, before)


# ---------------------------------------------------------------------------
# Missing column: every single-column handler refuses it the same way
# ---------------------------------------------------------------------------

_SINGLE_COLUMN_KINDS = [
    ("rename_column", {"new_name": "y"}),
    ("cast_column", {"dtype": "string"}),
    ("fill_nan", {"method": "forwardfill"}),
    ("filter_rows", {"op": "eq", "value": 1}),
    ("sort_rows", {}),
    ("replace_values", {"old": 1, "new": 2}),
    ("strip_whitespace", {}),
    ("lowercase", {}),
    ("uppercase", {}),
    ("clip_values", {"min": 0}),
    ("remove_outliers", {}),
    ("log_transform", {}),
    ("normalize", {}),
    ("standardize", {}),
    ("round_values", {}),
    ("bin_discretize", {}),
    ("rank_transform", {}),
    ("date_extract", {}),
    ("lag_lead", {}),
    ("rolling_window", {}),
    ("difference", {}),
    ("cumulative_sum", {}),
    ("pct_change", {}),
    ("one_hot_encode", {}),
    ("label_encode", {}),
    ("string_split", {}),
    ("group_aggregate", {"group_by": "g"}),
    ("update_cell", {"row_index": 0, "value": 1}),
]


@pytest.mark.parametrize(("kind", "params"), _SINGLE_COLUMN_KINDS, ids=[k for k, _ in _SINGLE_COLUMN_KINDS])
def test_missing_column_is_refused(df, kind, params):
    with pytest.raises(ValueError, match="Column 'nope' not found. Available: \\['x', 'g', 's'\\]"):
        execute_operation(df, kind, {**params, "column": "nope"})


@pytest.mark.parametrize(
    ("kind", "params"),
    [
        ("drop_columns", {"columns": ["x", "nope"]}),
        ("drop_nan_rows", {"columns": ["nope"]}),
        ("deduplicate", {"columns": ["nope"]}),
    ],
)
def test_missing_columns_in_a_list_are_named(df, kind, params):
    with pytest.raises(ValueError, match="Columns not found: \\['nope'\\]"):
        execute_operation(df, kind, params)


@pytest.mark.parametrize(
    "params",
    [
        {"numerator": "nope", "denominator": "x"},
        {"numerator": "x", "denominator": "nope"},
    ],
)
def test_ratio_missing_column(df, params):
    with pytest.raises(ValueError, match="Column 'nope' not found"):
        execute_operation(df, "ratio", params)


def test_group_aggregate_missing_group_column(df):
    with pytest.raises(ValueError, match="Column 'nope' not found"):
        execute_operation(df, "group_aggregate", {"group_by": "nope", "column": "x"})


# ---------------------------------------------------------------------------
# Cleaning
# ---------------------------------------------------------------------------


class TestCast:
    @pytest.mark.parametrize(
        ("target", "check"),
        [
            ("string", lambda s: not pd.api.types.is_numeric_dtype(s)),
            ("float64", lambda s: s.dtype == "float64"),
            ("category", lambda s: s.dtype == "category"),
            ("bool", lambda s: s.dtype == "bool"),
        ],
    )
    def test_targets(self, target, check):
        out = execute_operation(pd.DataFrame({"v": [1, 0, 1]}), "cast_column", {"column": "v", "dtype": target})
        assert check(out["v"])

    def test_datetime_coerces_unparsable_to_missing(self):
        frame = pd.DataFrame({"d": ["2024-01-01", "not a date"]})
        out = execute_operation(frame, "cast_column", {"column": "d", "dtype": "datetime"})
        assert pd.api.types.is_datetime64_any_dtype(out["d"])
        assert out["d"].isna().tolist() == [False, True]

    def test_unknown_dtype(self, df):
        with pytest.raises(ValueError, match="Unknown target dtype 'decimal'"):
            execute_operation(df, "cast_column", {"column": "x", "dtype": "decimal"})

    @pytest.mark.parametrize(
        ("values", "dtype"),
        [(["a", "1"], "int64"), ([1.0, np.nan], "int64")],
        ids=["unparsable", "nan-to-int"],
    )
    def test_impossible_cast_is_a_value_error(self, values, dtype):
        with pytest.raises(ValueError):
            execute_operation(pd.DataFrame({"v": values}), "cast_column", {"column": "v", "dtype": dtype})


class TestDropAndFill:
    def test_drop_columns(self, df):
        assert list(execute_operation(df, "drop_columns", {"columns": ["g", "s"]}).columns) == ["x"]

    @pytest.mark.parametrize(
        ("params", "rows"),
        [({}, 3), ({"columns": ["x"]}, 4), ({"how": "all"}, 5)],
    )
    def test_drop_nan(self, df, params, rows):
        out = execute_operation(df, "drop_nan_rows", params)
        assert len(out) == rows
        assert list(out.index) == list(range(rows))

    @pytest.mark.parametrize(
        ("method", "extra", "expected"),
        [
            ("forwardfill", {}, [1.0, 2.0, 2.0, 4.0, 100.0]),
            ("backfill", {}, [1.0, 2.0, 4.0, 4.0, 100.0]),
            ("value", {"value": 0}, [1.0, 2.0, 0.0, 4.0, 100.0]),
        ],
    )
    def test_fill(self, df, method, extra, expected):
        out = execute_operation(df, "fill_nan", {"column": "x", "method": method, **extra})
        assert out["x"].tolist() == expected

    def test_fill_value_requires_value(self, df):
        with pytest.raises(ValueError, match="requires a 'value'"):
            execute_operation(df, "fill_nan", {"column": "x", "method": "value"})

    def test_fill_unknown_method(self, df):
        with pytest.raises(ValueError, match="Unknown fill method 'mean'"):
            execute_operation(df, "fill_nan", {"column": "x", "method": "mean"})

    def test_drop_nan_bad_how(self, df):
        with pytest.raises(ValueError):
            execute_operation(df, "drop_nan_rows", {"how": "some"})


class TestFilterSortDedupe:
    @pytest.mark.parametrize(
        ("op", "value", "expected"),
        [
            ("eq", 2.0, [2.0]),
            ("ne", 2.0, [1.0, None, 4.0, 100.0]),
            ("gt", 2.0, [4.0, 100.0]),
            ("lt", 2.0, [1.0]),
            ("gte", 4.0, [4.0, 100.0]),
            ("lte", 2.0, [1.0, 2.0]),
            ("isin", [1.0, 4.0], [1.0, 4.0]),
            ("isin", 4.0, [4.0]),
        ],
    )
    def test_numeric_ops(self, df, op, value, expected):
        out = execute_operation(df, "filter_rows", {"column": "x", "op": op, "value": value})
        assert _vals(out["x"]) == expected
        assert list(out.index) == list(range(len(out)))

    def test_contains_skips_missing(self, df):
        out = execute_operation(df, "filter_rows", {"column": "s", "op": "contains", "value": ","})
        assert out["s"].tolist() == ["a,b", "d,e,f"]

    def test_unknown_op(self, df):
        with pytest.raises(ValueError, match="Unknown filter op 'like'"):
            execute_operation(df, "filter_rows", {"column": "x", "op": "like", "value": 1})

    @pytest.mark.parametrize(("ascending", "first"), [(True, 1.0), (False, 100.0)])
    def test_sort(self, df, ascending, first):
        out = execute_operation(df, "sort_rows", {"column": "x", "ascending": ascending})
        assert out["x"].iloc[0] == first
        assert pd.isna(out["x"].iloc[-1])  # missing values sort last either way

    @pytest.mark.parametrize(
        ("params", "rows"),
        [({}, 3), ({"columns": ["k"]}, 2), ({"columns": ["k"], "keep": "last"}, 2), ({"keep": False}, 2)],
    )
    def test_deduplicate(self, params, rows):
        frame = pd.DataFrame({"k": [1, 1, 1, 2], "v": [1, 1, 3, 4]})
        assert len(execute_operation(frame, "deduplicate", params)) == rows

    def test_deduplicate_keep_last_keeps_the_last(self):
        frame = pd.DataFrame({"k": [1, 1], "v": [1, 2]})
        out = execute_operation(frame, "deduplicate", {"columns": ["k"], "keep": "last"})
        assert out["v"].tolist() == [2]


class TestTextCleaning:
    def test_replace(self, df):
        out = execute_operation(df, "replace_values", {"column": "g", "old": "a", "new": "z"})
        assert _vals(out["g"]) == ["z", "z", "b", "b", None]

    @pytest.mark.parametrize(
        ("kind", "expected"),
        [("strip_whitespace", "Ab c"), ("lowercase", " ab c "), ("uppercase", " AB C ")],
    )
    def test_case_and_whitespace(self, kind, expected):
        out = execute_operation(pd.DataFrame({"t": [" Ab c "]}), kind, {"column": "t"})
        assert out["t"].tolist() == [expected]


class TestClip:
    @pytest.mark.parametrize(
        ("bounds", "expected"),
        [
            ({"min": 0, "max": 6}, [5.0, None, 6.0, 0.0]),
            ({"min": 1}, [5.0, None, 10.0, 1.0]),
            ({"max": 2.5}, [2.5, None, 2.5, -3.0]),
        ],
    )
    def test_clip_coerces_text_to_missing(self, bounds, expected):
        frame = pd.DataFrame({"v": ["5", "a", 10, -3]})
        assert _vals(execute_operation(frame, "clip_values", {"column": "v", **bounds})["v"]) == expected

    @pytest.mark.parametrize(
        ("bounds", "message"),
        [
            ({}, "Give a lowest value"),
            ({"min": "1"}, "Give a lowest value"),
            ({"max": True}, "Give a lowest value"),
            ({"min": 5, "max": 1}, "can't be above"),
        ],
    )
    def test_bad_bounds(self, df, bounds, message):
        with pytest.raises(ValueError, match=message):
            execute_operation(df, "clip_values", {"column": "x", **bounds})


class TestRemoveOutliers:
    @pytest.mark.parametrize(
        ("params", "expected"),
        [
            ({}, [1.0, 2.0, None, 4.0]),
            ({"method": "iqr"}, [1.0, 2.0, None, 4.0]),
            ({"method": "zscore", "threshold": 1}, [1.0, 2.0, None, 4.0]),
            ({"method": "zscore"}, [1.0, 2.0, None, 4.0, 100.0]),  # threshold 3: none that far out
        ],
    )
    def test_methods_keep_missing_rows(self, df, params, expected):
        out = execute_operation(df, "remove_outliers", {"column": "x", **params})
        assert _vals(out["x"]) == expected
        assert list(out.index) == list(range(len(out)))

    @pytest.mark.parametrize("values", [[1, 1, 1], [7], [np.nan, 3.0, 3.0]], ids=["constant", "single", "const+nan"])
    @pytest.mark.parametrize("method", ["iqr", "zscore"])
    def test_no_spread_removes_nothing(self, values, method):
        # Regression: zscore divided by a zero (or undefined) std, got NaN for
        # every z, and removed every row.
        frame = pd.DataFrame({"v": values})
        out = execute_operation(frame, "remove_outliers", {"column": "v", "method": method})
        assert len(out) == len(values)

    def test_non_numeric_column_removes_nothing(self):
        frame = pd.DataFrame({"v": ["a", "b"]})
        assert len(execute_operation(frame, "remove_outliers", {"column": "v"})) == 2

    @pytest.mark.parametrize("method", ["iqr", "zscore"])
    def test_empty_frame(self, empty, method):
        assert execute_operation(empty, "remove_outliers", {"column": "x", "method": method}).empty

    def test_unknown_method(self, df):
        with pytest.raises(ValueError, match="Unknown outlier method 'mad'"):
            execute_operation(df, "remove_outliers", {"column": "x", "method": "mad"})


# ---------------------------------------------------------------------------
# Transformation
# ---------------------------------------------------------------------------


class TestTransformation:
    def test_log_default_and_named_target(self):
        frame = pd.DataFrame({"v": [-1, 0, 1, math.e]})
        with np.errstate(divide="ignore", invalid="ignore"):
            out = execute_operation(frame, "log_transform", {"column": "v"})
            named = execute_operation(frame, "log_transform", {"column": "v", "target": "lv"})
        vals = out["v_log"].tolist()
        assert math.isnan(vals[0]) and vals[1] == -math.inf and vals[2] == 0.0 and vals[3] == pytest.approx(1.0)
        assert "lv" in named.columns

    def test_normalize(self, df):
        out = execute_operation(df, "normalize", {"column": "x"})
        assert out["x"].iloc[0] == 0.0 and out["x"].iloc[4] == 1.0 and pd.isna(out["x"].iloc[2])

    def test_normalize_constant_keeps_missing(self):
        # Regression: a constant column was overwritten with 0.0 everywhere,
        # its missing values included.
        out = execute_operation(pd.DataFrame({"v": [2, np.nan, 2]}), "normalize", {"column": "v"})
        assert _vals(out["v"]) == [0.0, None, 0.0]

    def test_normalize_non_numeric_is_all_missing(self):
        out = execute_operation(pd.DataFrame({"v": ["a", "b"]}), "normalize", {"column": "v"})
        assert out["v"].isna().all()

    def test_standardize(self):
        out = execute_operation(pd.DataFrame({"v": [1.0, 2.0, 3.0]}), "standardize", {"column": "v"})
        assert out["v"].tolist() == [-1.0, 0.0, 1.0]

    def test_standardize_single_value_is_missing(self):
        out = execute_operation(pd.DataFrame({"v": [5]}), "standardize", {"column": "v"})
        assert out["v"].isna().all()

    @pytest.mark.parametrize(("decimals", "expected"), [(None, 1.23), (0, 1.0), (1, 1.2)])
    def test_round(self, decimals, expected):
        params = {"column": "v"} if decimals is None else {"column": "v", "decimals": decimals}
        assert execute_operation(pd.DataFrame({"v": [1.234]}), "round_values", params)["v"].iloc[0] == expected

    def test_bin_codes_and_labels(self, df):
        codes = execute_operation(df, "bin_discretize", {"column": "x", "bins": 2})
        labels = execute_operation(df, "bin_discretize", {"column": "x", "bins": 2, "labels": ["lo", "hi"]})
        assert codes["x_bin"].iloc[0] != codes["x_bin"].iloc[4]
        assert _vals(labels["x_bin"]) == ["lo", "lo", None, "lo", "hi"]

    def test_bin_custom_target(self, df):
        assert "band" in execute_operation(df, "bin_discretize", {"column": "x", "bins": 2, "target": "band"})

    def test_bin_empty_frame(self, empty):
        with pytest.raises(ValueError):
            execute_operation(empty, "bin_discretize", {"column": "x"})

    @pytest.mark.parametrize(
        ("method", "expected"),
        [("average", [1.0, 2.5, 2.5]), ("min", [1.0, 2.0, 2.0]), ("dense", [1.0, 2.0, 2.0]), ("first", [1.0, 2.0, 3.0])],
    )
    def test_rank(self, method, expected):
        out = execute_operation(pd.DataFrame({"v": [1, 5, 5]}), "rank_transform", {"column": "v", "method": method})
        assert out["v"].tolist() == expected

    def test_rank_unknown_method(self, df):
        # Regression: pandas raised a KeyError, which the server answers as 404.
        with pytest.raises(ValueError, match="Unknown rank method 'zz'"):
            execute_operation(df, "rank_transform", {"column": "x", "method": "zz"})


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------


class TestDerivedColumn:
    def test_expression(self, df):
        out = execute_operation(df, "derived_column", {"expression": "x * 2", "target": "y"})
        assert _vals(out["y"]) == [2.0, 4.0, None, 8.0, 200.0]

    def test_bad_expression(self, df):
        with pytest.raises(ValueError, match="Expression error"):
            execute_operation(df, "derived_column", {"expression": "__import__('os')", "target": "y"})


class TestDateExtract:
    def test_default_parts(self):
        out = execute_operation(pd.DataFrame({"d": ["2024-05-17"]}), "date_extract", {"column": "d"})
        assert [out[c].iloc[0] for c in ("d_year", "d_month", "d_day")] == [2024, 5, 17]
        assert "d_hour" not in out

    def test_all_parts(self):
        out = execute_operation(
            pd.DataFrame({"d": ["2024-05-17 13:45"]}),
            "date_extract",
            {"column": "d", "parts": ["year", "month", "day", "dayofweek", "quarter", "hour"]},
        )
        row = out.iloc[0]
        assert (row.d_year, row.d_month, row.d_day, row.d_dayofweek, row.d_quarter, row.d_hour) == (
            2024,
            5,
            17,
            4,
            2,
            13,
        )

    def test_unparsable_and_missing_become_missing(self):
        frame = pd.DataFrame({"d": ["2024-01-15", "not a date", None]})
        out = execute_operation(frame, "date_extract", {"column": "d", "parts": ["year"]})
        assert _vals(out["d_year"]) == [2024, None, None]

    def test_mixed_formats_all_parse(self):
        # Regression: pandas guessed the format from the first value and
        # blanked the date-and-time value that followed.
        frame = pd.DataFrame({"d": ["2024-01-15", "2024-03-01 13:00", "15 March 2024"]})
        out = execute_operation(frame, "date_extract", {"column": "d", "parts": ["month", "hour"]})
        assert _vals(out["d_month"]) == [1, 3, 3]
        assert _vals(out["d_hour"]) == [0, 13, 0]

    def test_all_unparsable(self):
        out = execute_operation(pd.DataFrame({"d": ["x", "y"]}), "date_extract", {"column": "d", "parts": ["year"]})
        assert out["d_year"].isna().all()

    def test_one_time_zone_keeps_local_time(self):
        frame = pd.DataFrame({"d": ["2024-01-15T10:00:00+02:00", "2024-01-16T23:00:00+02:00"]})
        out = execute_operation(frame, "date_extract", {"column": "d", "parts": ["hour", "day"]})
        assert out["d_hour"].tolist() == [10, 23]
        assert out["d_day"].tolist() == [15, 16]

    @pytest.mark.parametrize(
        "values",
        [
            ["2024-01-15T10:00:00+02:00", "2024-01-15T10:00:00-05:00"],
            ["2024-01-15T10:00:00+02:00", "2024-01-16"],
        ],
        ids=["two-zones", "zoned-and-naive"],
    )
    def test_mixed_time_zones_are_refused_clearly(self, values):
        with pytest.raises(ValueError, match="Could not read column 'd' as dates"):
            execute_operation(pd.DataFrame({"d": values}), "date_extract", {"column": "d", "parts": ["hour"]})

    @pytest.mark.parametrize("parts", [["year", "week"], "year"], ids=["unknown-part", "string-not-list"])
    def test_unknown_parts_are_refused(self, parts):
        # Regression: unknown parts were silently ignored.
        with pytest.raises(ValueError, match="Unknown date parts"):
            execute_operation(pd.DataFrame({"d": ["2024-01-01"]}), "date_extract", {"column": "d", "parts": parts})

    def test_empty_frame(self):
        out = execute_operation(pd.DataFrame({"d": pd.Series([], dtype=object)}), "date_extract", {"column": "d"})
        assert out.empty and {"d_year", "d_month", "d_day"} <= set(out.columns)


class TestShifts:
    @pytest.mark.parametrize(
        ("params", "target", "expected"),
        [
            ({}, "x_lag1", [None, 1.0, 2.0, None, 4.0]),
            ({"periods": 2}, "x_lag2", [None, None, 1.0, 2.0, None]),
            ({"periods": -1}, "x_lag-1", [2.0, None, 4.0, 100.0, None]),
            ({"target": "prev"}, "prev", [None, 1.0, 2.0, None, 4.0]),
        ],
    )
    def test_lag_lead(self, df, params, target, expected):
        assert _vals(execute_operation(df, "lag_lead", {"column": "x", **params})[target]) == expected

    @pytest.mark.parametrize(
        ("params", "target", "expected"),
        [({}, "x_diff1", [None, 1.0, None, None, 96.0]), ({"periods": 3, "target": "d3"}, "d3", [None, None, None, 3.0, 98.0])],
    )
    def test_difference(self, df, params, target, expected):
        assert _vals(execute_operation(df, "difference", {"column": "x", **params})[target]) == expected

    def test_cumulative_sum_skips_missing(self, df):
        out = execute_operation(df, "cumulative_sum", {"column": "x"})
        assert _vals(out["x_cumsum"]) == [1.0, 3.0, None, 7.0, 107.0]

    def test_pct_change_from_zero_is_infinite(self):
        out = execute_operation(pd.DataFrame({"v": [0, 1, 2]}), "pct_change", {"column": "v", "target": "p"})
        assert _vals(out["p"]) == [None, math.inf, 1.0]


class TestRollingWindow:
    @pytest.mark.parametrize(
        ("params", "target", "expected"),
        [
            ({}, "x_roll3_mean", [1.0, 1.5, 1.5, 3.0, 52.0]),
            ({"window": 2, "func": "sum"}, "x_roll2_sum", [1.0, 3.0, 2.0, 4.0, 104.0]),
            ({"window": 2, "func": "max"}, "x_roll2_max", [1.0, 2.0, 2.0, 4.0, 100.0]),
            ({"window": 2, "func": "min"}, "x_roll2_min", [1.0, 1.0, 2.0, 4.0, 4.0]),
            ({"window": 3, "func": "count"}, "x_roll3_count", [1.0, 2.0, 2.0, 2.0, 2.0]),
            ({"window": 1, "target": "same"}, "same", [1.0, 2.0, None, 4.0, 100.0]),
        ],
    )
    def test_funcs(self, df, params, target, expected):
        out = execute_operation(df, "rolling_window", {"column": "x", **params})
        assert _vals(out[target]) == expected

    def test_window_larger_than_frame_uses_what_there_is(self, df):
        out = execute_operation(df, "rolling_window", {"column": "x", "window": 50, "func": "sum"})
        assert out["x_roll50_sum"].tolist() == [1.0, 3.0, 3.0, 7.0, 107.0]

    @pytest.mark.parametrize("func", ["median", "std", "var"])
    def test_other_known_funcs_run(self, df, func):
        assert f"x_roll3_{func}" in execute_operation(df, "rolling_window", {"column": "x", "func": func})

    def test_empty_frame(self, empty):
        out = execute_operation(empty, "rolling_window", {"column": "x"})
        assert out.empty and "x_roll3_mean" in out.columns

    def test_text_column_is_all_missing(self):
        out = execute_operation(pd.DataFrame({"v": ["a", "b"]}), "rolling_window", {"column": "v"})
        assert out["v_roll3_mean"].isna().all()

    @pytest.mark.parametrize("func", ["nope", "__class__", "apply", "_get_window_indexer"])
    def test_unknown_func_is_refused(self, df, func):
        # Regression: the name went straight to getattr on the pandas object.
        with pytest.raises(ValueError, match="Unknown rolling function"):
            execute_operation(df, "rolling_window", {"column": "x", "func": func})

    @pytest.mark.parametrize("window", [0, -2, "3", 2.5, True, None])
    def test_bad_window_is_refused(self, df, window):
        with pytest.raises(ValueError, match="The window must be a whole number of rows"):
            execute_operation(df, "rolling_window", {"column": "x", "window": window})


class TestRatio:
    def test_division_by_zero(self):
        frame = pd.DataFrame({"a": [1, 0, -1, 6], "b": [0, 0, 0, 2]})
        out = execute_operation(frame, "ratio", {"numerator": "a", "denominator": "b"})
        assert _vals(out["a_over_b"]) == [math.inf, None, -math.inf, 3.0]

    def test_text_and_missing_become_missing(self):
        frame = pd.DataFrame({"a": ["4", "z", None], "b": [2, 2, 2]})
        out = execute_operation(frame, "ratio", {"numerator": "a", "denominator": "b", "target": "r"})
        assert _vals(out["r"]) == [2.0, None, None]


class TestEncoding:
    def test_one_hot(self, df):
        out = execute_operation(df, "one_hot_encode", {"column": "g"})
        assert "g" not in out.columns
        assert out["g_a"].tolist() == [1, 1, 0, 0, 0]
        assert out["g_b"].tolist() == [0, 0, 1, 1, 0]

    def test_label_encode_missing_is_minus_one(self, df):
        out = execute_operation(df, "label_encode", {"column": "g"})
        assert out["g"].tolist() == [0, 0, 1, 1, -1]


class TestStringSplit:
    @pytest.mark.parametrize(
        ("params", "expected"),
        [
            ({}, {"s_0": ["a", "c", None, "d", "g"], "s_1": ["b", None, None, "e", None], "s_2": [None, None, None, "f", None]}),
            ({"max_splits": 1}, {"s_0": ["a", "c", None, "d", "g"], "s_1": ["b", None, None, "e,f", None]}),
        ],
    )
    def test_split(self, df, params, expected):
        out = execute_operation(df, "string_split", {"column": "s", **params})
        for col, vals in expected.items():
            assert _vals(out[col]) == vals
        assert "s_3" not in out.columns

    def test_delimiter_not_present(self):
        out = execute_operation(pd.DataFrame({"s": ["ab", "cd"]}), "string_split", {"column": "s", "delimiter": "|"})
        assert out["s_0"].tolist() == ["ab", "cd"] and "s_1" not in out.columns

    def test_numbers_are_split_as_text(self):
        out = execute_operation(pd.DataFrame({"s": [1.5]}), "string_split", {"column": "s", "delimiter": "."})
        assert out["s_0"].tolist() == ["1"] and out["s_1"].tolist() == ["5"]

    def test_empty_frame_adds_nothing(self, empty):
        out = execute_operation(empty, "string_split", {"column": "g"})
        assert list(out.columns) == ["x", "g"]


class TestGroupAggregate:
    @pytest.mark.parametrize(
        ("func", "expected"),
        [
            ("mean", [1.5, 1.5, 4.0, 4.0, None]),
            ("sum", [3.0, 3.0, 4.0, 4.0, None]),
            ("max", [2.0, 2.0, 4.0, 4.0, None]),
            ("count", [2, 2, 1, 1, None]),
        ],
    )
    def test_funcs_with_missing_values_and_keys(self, df, func, expected):
        # A row with no group key gets no aggregate.
        out = execute_operation(df, "group_aggregate", {"group_by": "g", "column": "x", "func": func})
        assert _vals(out[f"x_{func}_by_g"]) == expected

    def test_custom_target(self, df):
        out = execute_operation(df, "group_aggregate", {"group_by": "g", "column": "x", "target": "avg"})
        assert "avg" in out.columns

    def test_empty_frame(self, empty):
        out = execute_operation(empty, "group_aggregate", {"group_by": "g", "column": "x"})
        assert out.empty and "x_mean_by_g" in out.columns

    def test_unknown_func(self, df):
        with pytest.raises(ValueError):
            execute_operation(df, "group_aggregate", {"group_by": "g", "column": "x", "func": "nope"})


# ---------------------------------------------------------------------------
# Reshaping
# ---------------------------------------------------------------------------


class TestReshape:
    def test_melt(self):
        frame = pd.DataFrame({"i": [1, 2], "a": [3, 4], "b": [5, 6]})
        out = execute_operation(frame, "melt", {"id_vars": ["i"], "var_name": "k", "value_name": "v"})
        assert list(out.columns) == ["i", "k", "v"] and len(out) == 4

    def test_melt_value_vars_subset(self):
        frame = pd.DataFrame({"i": [1], "a": [3], "b": [5]})
        out = execute_operation(frame, "melt", {"id_vars": ["i"], "value_vars": ["a"]})
        assert out["variable"].tolist() == ["a"] and out["value"].tolist() == [3]

    def test_melt_defaults_to_all_columns(self):
        out = execute_operation(pd.DataFrame({"a": [1], "b": [2]}), "melt", {})
        assert list(out.columns) == ["variable", "value"] and len(out) == 2

    def test_pivot_one_value_column(self):
        frame = pd.DataFrame({"i": [1, 1, 2], "c": ["a", "b", "a"], "v": [1, 2, 3]})
        out = execute_operation(frame, "pivot", {"index": "i", "columns": "c", "values": "v"})
        assert list(out.columns) == ["i", "a", "b"]
        assert _vals(out["b"]) == [2.0, None]

    def test_pivot_several_value_columns_are_flattened(self):
        frame = pd.DataFrame({"i": [1, 1, 2], "c": ["a", "b", "a"], "v": [1, 2, 3], "w": [4, 5, 6]})
        out = execute_operation(frame, "pivot", {"index": "i", "columns": "c", "aggfunc": "sum"})
        assert list(out.columns) == ["i", "v_a", "v_b", "w_a", "w_b"]


# ---------------------------------------------------------------------------
# Row operations and cells (beyond the end-to-end tests in test_datasets.py)
# ---------------------------------------------------------------------------


class TestRowsAndCells:
    @pytest.mark.parametrize("position", [-1, 6])
    def test_insert_out_of_range(self, df, position):
        with pytest.raises(ValueError, match="out of range"):
            execute_operation(df, "insert_row", {"position": position})

    @pytest.mark.parametrize("kind", ["delete_rows", "duplicate_rows"])
    @pytest.mark.parametrize(("indices", "message"), [([], "No row indices"), ([0, 9], "out of range: \\[9\\]")])
    def test_bad_indices(self, df, kind, indices, message):
        with pytest.raises(ValueError, match=message):
            execute_operation(df, kind, {"indices": indices})

    def test_duplicate_rows_dedupes_indices(self, df):
        out = execute_operation(df, "duplicate_rows", {"indices": [1, 1]})
        assert len(out) == 6 and _vals(out["x"])[:3] == [1.0, 2.0, 2.0]

    @pytest.mark.parametrize(
        ("values", "value", "expected"),
        [
            ([True, False], "yes", True),
            ([True, False], "no", False),
            ([1, 2], "7", 7),
            ([1, 2], "", None),
            ([1, 2], "2.5", 2.5),
            ([1.0, 2.0], "not a number", "not a number"),
            (pd.to_datetime(["2024-01-01", "2024-01-02"]), "2025-06-01", pd.Timestamp("2025-06-01")),
            (pd.to_datetime(["2024-01-01", "2024-01-02"]), "garbage", "garbage"),
        ],
        ids=["bool-yes", "bool-no", "int", "int-blank", "int-gets-float", "float-gets-text", "datetime", "datetime-gets-text"],
    )
    def test_update_cell_coercion(self, values, value, expected):
        # Regressions: a bool column took the numeric branch (pandas counts
        # bool as numeric) and refused "yes"; text or a fraction in a typed
        # column raised under pandas 3 instead of widening the column.
        frame = pd.DataFrame({"c": values})
        out = execute_operation(frame, "update_cell", {"row_index": 0, "column": "c", "value": value})
        got = out["c"].iloc[0]
        assert (None if pd.isna(got) else got) == expected
        assert out["c"].iloc[1] == frame["c"].iloc[1]

    @pytest.mark.parametrize("row_index", [-1, 5])
    def test_update_cell_row_out_of_range(self, df, row_index):
        with pytest.raises(ValueError, match="Row index .* out of range"):
            execute_operation(df, "update_cell", {"row_index": row_index, "column": "x", "value": 1})

    @pytest.mark.parametrize(
        ("order", "message"),
        [(["x", "g", "nope"], "not in DataFrame"), (["x", "g"], "missing from new order"), (["x", "g", "s", "s"], "count mismatch")],
    )
    def test_reorder_refusals(self, df, order, message):
        with pytest.raises(ValueError, match=message):
            execute_operation(df, "reorder_columns", {"columns": order})


# ---------------------------------------------------------------------------
# Loading, saving, hashing, column inference
# ---------------------------------------------------------------------------


class TestFiles:
    @pytest.mark.parametrize("suffix", [".csv", ".tsv", ".tab", ".CSV"])
    def test_round_trip(self, tmp_path: Path, suffix):
        frame = pd.DataFrame({"a": [1, 2], "b": ["x, y", None], "c": [1.5, np.nan]})
        path = tmp_path / f"f{suffix}"
        save_dataframe(frame, path)
        text = path.read_text(encoding="utf-8")
        assert ("\t" in text) == (suffix.lower() in (".tsv", ".tab"))
        assert "\r" not in text
        back = load_dataframe(path)
        assert back["a"].tolist() == [1, 2]
        assert _vals(back["b"]) == ["x, y", None]
        assert _vals(back["c"]) == [1.5, None]

    def test_failed_write_leaves_original_and_no_temp_file(self, tmp_path: Path, monkeypatch):
        path = tmp_path / "f.csv"
        path.write_text("a\n1\n", encoding="utf-8")

        def boom(src, dst):
            raise OSError("disk full")

        monkeypatch.setattr("latris.repo.yaml_io.atomic_replace", boom)
        with pytest.raises(OSError, match="disk full"):
            save_dataframe(pd.DataFrame({"a": [9]}), path)
        assert path.read_text(encoding="utf-8") == "a\n1\n"
        assert [p.name for p in tmp_path.iterdir()] == ["f.csv"]

    def test_content_hash(self, tmp_path: Path):
        import hashlib

        path = tmp_path / "f.csv"
        path.write_bytes(b"a,b\n1,2\n")
        assert file_content_hash(path) == "sha256:" + hashlib.sha256(b"a,b\n1,2\n").hexdigest()

    def test_infer_column_specs(self):
        frame = pd.DataFrame(
            {
                "i": [1],
                "f": [1.5],
                "b": [True],
                "t": ["x"],
                "d": pd.to_datetime(["2024-01-01"]),
                "z": pd.to_datetime(["2024-01-01"]).tz_localize("UTC"),
                "c": pd.Series(["x"], dtype="category"),
                "n": pd.array([1], dtype="Int64"),
            }
        )
        dtypes = {spec.name: spec.dtype for spec in infer_column_specs(frame)}
        assert dtypes == {
            "i": "int64",
            "f": "float64",
            "b": "bool",
            "t": "string",
            "d": "datetime",
            "z": "datetime",
            "c": "category",
            "n": "int64",
        }

    @pytest.mark.parametrize(
        "name", ["datetime64[ns]", "datetime64[us]", "datetime64[ns, UTC]", "datetime64[us, Europe/Paris]"]
    )
    def test_every_datetime_resolution_and_zone_is_datetime(self, name):
        # Regression: pandas 3's datetime64[us] was reported as "string".
        assert engine._map_dtype(name) == "datetime"

    def test_unknown_dtype_maps_to_string(self):
        assert engine._map_dtype("complex128") == "string"


# ---------------------------------------------------------------------------
# Stats, correlations, paging
# ---------------------------------------------------------------------------


class TestColumnStats:
    def test_numeric(self, df):
        stats = compute_column_stats(df, "x")
        assert stats["count"] == 4 and stats["nulls"] == 1 and stats["total"] == 5 and stats["unique"] == 4
        assert stats["min"] == 1.0 and stats["max"] == 100.0 and stats["mean"] == pytest.approx(26.75)

    def test_text_has_no_numeric_stats(self, df):
        stats = compute_column_stats(df, "g")
        assert stats["dtype"] == "string" and stats["unique"] == 2
        assert "mean" not in stats

    def test_empty_numeric_column(self, empty):
        stats = compute_column_stats(empty, "x")
        assert stats["total"] == 0 and stats["min"] is None and stats["mean"] is None

    def test_missing_column(self, df):
        with pytest.raises(ValueError, match="Column 'nope' not found"):
            compute_column_stats(df, "nope")


class TestCorrelations:
    @pytest.fixture
    def frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "a": [1.0, 2.0, 3.0, 4.0, 5.0],
                "b": [2.0, 4.1, 6.0, 8.2, 9.9],
                "c": [5.0, 3.0, 4.0, 1.0, 2.0],
                "t": ["x"] * 5,
            }
        )

    @pytest.mark.parametrize("method", ["pearson", "spearman", "kendall"])
    def test_methods(self, frame, method):
        results = compute_correlations(frame, method=method, threshold=0.0)
        assert {(r["col_a"], r["col_b"]) for r in results} == {("a", "b"), ("a", "c"), ("b", "c")}
        assert all(r["method"] == method for r in results)
        coefs = [abs(r["coefficient"]) for r in results]
        assert coefs == sorted(coefs, reverse=True)

    def test_column_subset_ignores_unknown_and_text(self, frame):
        results = compute_correlations(frame, columns=["a", "b", "t", "nope"], threshold=0.0)
        assert [(r["col_a"], r["col_b"]) for r in results] == [("a", "b")]

    def test_fewer_than_two_numeric_columns(self, frame):
        assert compute_correlations(frame, columns=["a"]) == []

    def test_fewer_than_three_shared_rows_is_skipped(self):
        frame = pd.DataFrame({"a": [1.0, 2.0, np.nan, np.nan], "b": [np.nan, 1.0, 2.0, 3.0]})
        assert compute_correlations(frame, threshold=0.0) == []


class TestPage:
    def test_slice_and_missing_as_none(self, df):
        page = dataframe_to_page(df, offset=1, limit=2)
        assert page["columns"] == ["x", "g", "s"]
        assert page["rows"] == [[2.0, "a", "c"], [None, "b", None]]
        assert (page["total_rows"], page["offset"], page["limit"]) == (5, 1, 2)

    def test_offset_past_the_end(self, df):
        page = dataframe_to_page(df, offset=10)
        assert page["rows"] == [] and page["total_rows"] == 5


def test_missing_pandas_is_explained(monkeypatch):
    monkeypatch.setattr(engine, "pd", None)
    with pytest.raises(ImportError, match="pip install 'latris\\[data\\]'"):
        engine._require_pandas()
