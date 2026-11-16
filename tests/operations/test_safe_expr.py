"""Derived-column expressions must never reach Python objects.

Regression for a code-execution hole: ``DataFrame.eval`` resolved
``@pd...`` to the pandas module, so ``@pd.io.common.os.system(...)`` ran
shell commands from an HTTP request.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from latris.operations._data_engine import _apply_derived_column
from latris.operations._safe_expr import evaluate_expression


@pytest.fixture
def df() -> pd.DataFrame:
    return pd.DataFrame({"a": [1.0, 2.0, 4.0], "b": [2.0, 2.0, 2.0], "flow rate": [10.0, 20.0, 30.0]})


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("a + b", [3.0, 4.0, 6.0]),
        ("a * 2 - b / 2", [1.0, 3.0, 7.0]),
        ("a ** 2", [1.0, 4.0, 16.0]),
        ("-a", [-1.0, -2.0, -4.0]),
        ("a // b", [0.0, 1.0, 2.0]),
        ("a % b", [1.0, 0.0, 0.0]),
        ("`flow rate` / a", [10.0, 10.0, 7.5]),
        ("sqrt(a)", [1.0, np.sqrt(2.0), 2.0]),
        ("log(a)", [0.0, np.log(2.0), np.log(4.0)]),
        ("abs(b - a)", [1.0, 0.0, 2.0]),
        ("maximum(a, b)", [2.0, 2.0, 4.0]),
        ("where(a > b, a, b)", [2.0, 2.0, 4.0]),
        ("1.5", [1.5, 1.5, 1.5]),
    ],
)
def test_allowed_expressions(df: pd.DataFrame, expression: str, expected: list[float]) -> None:
    out = _apply_derived_column(df, {"expression": expression, "target": "x"})
    assert out["x"].tolist() == pytest.approx(expected)


def test_comparisons_and_boolean_ops(df: pd.DataFrame) -> None:
    assert evaluate_expression(df, "a > b").tolist() == [False, False, True]
    assert evaluate_expression(df, "a >= 2 and b == 2").tolist() == [False, True, True]
    assert evaluate_expression(df, "(a < 2) | (a > 3)").tolist() == [True, False, True]
    assert evaluate_expression(df, "not (a > b)").tolist() == [True, True, False]
    assert evaluate_expression(df, "1 < a < 4").tolist() == [False, True, False]


@pytest.mark.parametrize(
    "expression",
    [
        "@pd.io.common.os.system('echo pwned')",
        "@pd",
        "@__builtins__",
        "__import__('os').system('echo pwned')",
        "a.__class__",
        "a.sum()",
        "pd.io.common.os.getcwd()",
        "open('/etc/passwd')",
        "eval('1')",
        "a[0]",
        "lambda: 1",
        "'text'",
        "[a, b]",
        "(x := 1)",
        "a if b else a",
        "sqrt(x=a)",
        "sqrt(a, b)",
        "unknown_column + 1",
        "a +",
        "",
    ],
)
def test_rejected_expressions(df: pd.DataFrame, expression: str) -> None:
    with pytest.raises(ValueError):
        _apply_derived_column(df, {"expression": expression, "target": "x"})


def test_huge_integer_power_does_not_hang(df: pd.DataFrame) -> None:
    # Python ints would build a gigantic number; literals are floats here.
    with pytest.raises(ValueError):
        _apply_derived_column(df, {"expression": "10 ** 10 ** 10", "target": "x"})


def test_length_and_complexity_limits(df: pd.DataFrame) -> None:
    with pytest.raises(ValueError, match="too long"):
        evaluate_expression(df, "a + " * 400 + "a")
    with pytest.raises(ValueError, match="too complex"):
        evaluate_expression(df, "+".join(["a"] * 150))


def test_original_dataframe_untouched(df: pd.DataFrame) -> None:
    _apply_derived_column(df, {"expression": "a + 1", "target": "a"})
    assert df["a"].tolist() == [1.0, 2.0, 4.0]
