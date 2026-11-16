"""Safe evaluator for dataset derived-column expressions.

Internal module — never imported above the operations layer.

``DataFrame.eval`` is unsafe on user input: its ``@name`` syntax reaches
the caller's scope (and through ``pd`` the whole Python runtime), so an
expression like ``@pd.io.common.os.system(...)`` runs a shell command.
Derived-column expressions arrive over the HTTP API, so they are parsed
here with :mod:`ast` and evaluated by walking a small whitelist of nodes:

* column references — bare names, or ``\\`backticked names\\``` for
  columns with spaces or punctuation;
* numeric literals (always treated as floats, so no huge-int blow-ups);
* arithmetic ``+ - * / // % **``, unary ``-``/``+``;
* comparisons (chains allowed) and boolean ``and``/``or``/``not``,
  ``&``/``|``/``~`` — all element-wise;
* a fixed set of functions (:data:`_FUNCTIONS`).

Anything else — attributes, subscripts, ``@``, lambdas, keyword
arguments, strings, unknown names or functions — is rejected with a
``ValueError`` before any evaluation happens.
"""

from __future__ import annotations

import ast
import operator
import re
from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd

MAX_EXPRESSION_LENGTH = 1000
MAX_NODES = 200

_BIN_OPS: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.BitAnd: operator.and_,
    ast.BitOr: operator.or_,
}

_CMP_OPS: dict[type[ast.cmpop], Callable[[Any, Any], Any]] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}


def _where(cond: Any, a: Any, b: Any) -> Any:
    out = np.where(cond, a, b)
    index = next((x.index for x in (cond, a, b) if isinstance(x, pd.Series)), None)
    return pd.Series(out, index=index) if index is not None else out


_FUNCTIONS: dict[str, tuple[Callable[..., Any], int]] = {
    # name: (callable, number of positional arguments)
    "abs": (np.abs, 1),
    "sqrt": (np.sqrt, 1),
    "exp": (np.exp, 1),
    "log": (np.log, 1),
    "log10": (np.log10, 1),
    "log2": (np.log2, 1),
    "log1p": (np.log1p, 1),
    "expm1": (np.expm1, 1),
    "sin": (np.sin, 1),
    "cos": (np.cos, 1),
    "tan": (np.tan, 1),
    "arcsin": (np.arcsin, 1),
    "arccos": (np.arccos, 1),
    "arctan": (np.arctan, 1),
    "sinh": (np.sinh, 1),
    "cosh": (np.cosh, 1),
    "tanh": (np.tanh, 1),
    "floor": (np.floor, 1),
    "ceil": (np.ceil, 1),
    "minimum": (np.minimum, 2),
    "maximum": (np.maximum, 2),
    "where": (_where, 3),
}

_BACKTICK = re.compile(r"`([^`]+)`")


def _substitute_backticks(expression: str) -> tuple[str, dict[str, str]]:
    """Replace ``\\`col name\\``` with placeholder identifiers."""
    aliases: dict[str, str] = {}

    def repl(match: re.Match[str]) -> str:
        alias = f"__col{len(aliases)}__"
        aliases[alias] = match.group(1)
        return alias

    return _BACKTICK.sub(repl, expression), aliases


class _Evaluator:
    def __init__(self, df: pd.DataFrame, aliases: dict[str, str]) -> None:
        self._df = df
        self._aliases = aliases

    def _column(self, name: str) -> pd.Series:
        column = self._aliases.get(name, name)
        if column not in self._df.columns:
            raise ValueError(f"Unknown column {column!r}. Available: {list(self._df.columns)}")
        return self._df[column]

    def eval(self, node: ast.AST) -> Any:  # noqa: PLR0911, PLR0912 — one branch per node type
        if isinstance(node, ast.Expression):
            return self.eval(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                return node.value
            if isinstance(node.value, (int, float)):
                return float(node.value)
            raise ValueError(f"Unsupported literal {node.value!r}: only numbers are allowed")
        if isinstance(node, ast.Name):
            if node.id in ("True", "False"):
                return node.id == "True"
            return self._column(node.id)
        if isinstance(node, ast.BinOp):
            op = _BIN_OPS.get(type(node.op))
            if op is None:
                raise ValueError(f"Unsupported operator {type(node.op).__name__}")
            return op(self.eval(node.left), self.eval(node.right))
        if isinstance(node, ast.UnaryOp):
            operand = self.eval(node.operand)
            if isinstance(node.op, ast.USub):
                return -operand
            if isinstance(node.op, ast.UAdd):
                return +operand
            if isinstance(node.op, (ast.Not, ast.Invert)):
                return ~operand if isinstance(operand, pd.Series) else not operand
            raise ValueError(f"Unsupported unary operator {type(node.op).__name__}")
        if isinstance(node, ast.BoolOp):
            values = [self.eval(v) for v in node.values]
            combine = operator.and_ if isinstance(node.op, ast.And) else operator.or_
            result = values[0]
            for v in values[1:]:
                result = combine(result, v)
            return result
        if isinstance(node, ast.Compare):
            left = self.eval(node.left)
            result: Any = None
            for op_node, comparator in zip(node.ops, node.comparators, strict=True):
                op = _CMP_OPS.get(type(op_node))
                if op is None:
                    raise ValueError(f"Unsupported comparison {type(op_node).__name__}")
                right = self.eval(comparator)
                part = op(left, right)
                result = part if result is None else (result & part)
                left = right
            return result
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCTIONS:
                raise ValueError(
                    f"Unsupported function call. Allowed functions: {', '.join(sorted(_FUNCTIONS))}"
                )
            if node.keywords:
                raise ValueError("Keyword arguments are not supported")
            func, arity = _FUNCTIONS[node.func.id]
            if len(node.args) != arity:
                raise ValueError(f"{node.func.id}() takes {arity} argument(s), got {len(node.args)}")
            return func(*(self.eval(a) for a in node.args))
        raise ValueError(f"Unsupported syntax in expression: {type(node).__name__}")


def evaluate_expression(df: pd.DataFrame, expression: str) -> Any:
    """Evaluate a derived-column *expression* against *df* safely.

    Returns a Series (or a scalar, which pandas broadcasts on assignment).
    Raises ``ValueError`` for anything outside the whitelist.
    """
    if not isinstance(expression, str) or not expression.strip():
        raise ValueError("Expression must be a non-empty string")
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise ValueError(f"Expression is too long (max {MAX_EXPRESSION_LENGTH} characters)")
    if "@" in _BACKTICK.sub("", expression):
        raise ValueError("'@' references are not supported in expressions")

    text, aliases = _substitute_backticks(expression)
    try:
        tree = ast.parse(text.strip(), mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Invalid expression: {exc.msg}") from exc

    if sum(1 for _ in ast.walk(tree)) > MAX_NODES:
        raise ValueError(f"Expression is too complex (max {MAX_NODES} syntax nodes)")

    with np.errstate(all="ignore"):
        return _Evaluator(df, aliases).eval(tree)
