"""simpleeval adapter — the ONLY module that evaluates SD equation strings.

Equations are untrusted text (typed by a modeller, or proposed by an agent), so
they are never handed to Python's ``eval``. They are parsed with ``ast`` and
checked against a whitelist here, then evaluated by ``simpleeval``.

Names are bound to ``pint`` quantities rather than bare floats. That is the
whole dimensional-analysis engine: pint's operator overloads refuse to add
litres to people, and multiply ``liter`` by ``1/year`` into ``liter/year`` —
so a unit error surfaces as an evaluation error, with no hand-written unit
algebra anywhere in Latris.

Two adapter details matter:

- simpleeval's default ``*`` and ``**`` guard against string bombs by probing
  ``__len__``, which pint quantities expose and then raise on. We supply our own
  operator table (plain arithmetic plus an exponent bound).
- Mixing a bare number with a quantity is only allowed where it is unambiguous:
  scaling (``0.5 * stock``), a literal zero in ``MIN``/``MAX``/``IF_THEN_ELSE``,
  or a dimensionless context. Everything else is a unit error.
"""

from __future__ import annotations

import ast
import math
import operator as op
import re
from dataclasses import dataclass
from typing import Any

import simpleeval

from latris.operations._units import PINT_ERRORS, Quantity
from latris.schema.sd import SDTableEntry

TIME = "TIME"
FUNCTIONS: tuple[str, ...] = (
    "MIN", "MAX", "ABS", "IF_THEN_ELSE", "STEP", "TABLE", "EXP", "LN", "SQRT",
)

_MAX_EXPONENT = 100

_ALLOWED_NODES: tuple[type[ast.AST], ...] = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Compare, ast.BoolOp, ast.Call,
    ast.Name, ast.Constant, ast.Load,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.USub, ast.UAdd, ast.Not,
    ast.Gt, ast.Lt, ast.GtE, ast.LtE, ast.Eq, ast.NotEq, ast.And, ast.Or,
)


class EquationError(ValueError):
    """An equation that can't be parsed or evaluated. Messages name the model, not the backend."""

    def __init__(self, message: str, *, target_id: str | None = None) -> None:
        super().__init__(message)
        self.target_id = target_id


def slugify(label: str) -> str:
    """The identifier an equation uses for a variable: ``"Birth Rate"`` → ``birth_rate``."""
    slug = re.sub(r"[^0-9a-z]+", "_", label.strip().lower()).strip("_")
    if not slug:
        slug = "var"
    if slug[0].isdigit():
        slug = f"_{slug}"
    return slug


@dataclass(frozen=True)
class ParsedEquation:
    expression: str
    node: ast.AST
    names: frozenset[str]
    uses_table: bool


def parse(expression: str) -> ParsedEquation:
    """Parse and whitelist-check an equation; collect the variable names it reads."""
    text = (expression or "").strip()
    if not text:
        raise EquationError("equation is empty")
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise EquationError(f"cannot parse {text!r}: {exc.msg}") from exc

    names: set[str] = set()
    calls: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise EquationError(
                f"{type(node).__name__} is not allowed in an equation ({text!r}); "
                f"use arithmetic, comparisons, and the functions {', '.join(FUNCTIONS)}"
            )
        if isinstance(node, ast.Constant) and not isinstance(node.value, int | float):
            raise EquationError(f"only numeric literals are allowed in an equation, got {node.value!r}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise EquationError(f"unsupported call in {text!r}")
            if node.keywords:
                raise EquationError(f"keyword arguments are not supported in {text!r}")
            fname = node.func.id
            if fname not in FUNCTIONS:
                hint = f" (did you mean {fname.upper()}?)" if fname.upper() in FUNCTIONS else ""
                raise EquationError(f"unknown function {fname!r}{hint}; available: {', '.join(FUNCTIONS)}")
            calls.add(fname)

    called = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call)}  # type: ignore[union-attr]
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id not in called and node.id != TIME:
            names.add(node.id)

    parsed_node = _PARSER.parse(text)
    return ParsedEquation(expression=text, node=parsed_node, names=frozenset(names), uses_table="TABLE" in calls)


# ── evaluation ───────────────────────────────────────────────────────


def _is_number(x: Any) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool)


def _safe_pow(a: Any, b: Any) -> Any:
    exponent = b.to("dimensionless").magnitude if isinstance(b, Quantity) else b
    if _is_number(exponent) and abs(exponent) > _MAX_EXPONENT:
        raise EquationError(f"exponent {exponent} is too large")
    return op.pow(a, b)


_OPERATORS = {
    ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv, ast.Pow: _safe_pow,
    ast.USub: op.neg, ast.UAdd: op.pos, ast.Not: op.not_,
    ast.Gt: op.gt, ast.Lt: op.lt, ast.GtE: op.ge, ast.LtE: op.le, ast.Eq: op.eq, ast.NotEq: op.ne,
}

_PARSER = simpleeval.SimpleEval(operators=_OPERATORS)


def _align(args: tuple[Any, ...], fname: str) -> list[Any]:
    """Bring arguments to one unit so they can be compared; a bare 0 adopts that unit."""
    ref = next((a for a in args if isinstance(a, Quantity)), None)
    if ref is None:
        return list(args)
    out = []
    for a in args:
        if isinstance(a, Quantity):
            out.append(a.to(ref.units))
        elif _is_number(a) and (a == 0 or ref.dimensionless):
            out.append(Quantity(float(a), ref.units))
        else:
            raise EquationError(
                f"{fname} mixes the bare number {a!r} with a quantity in {ref.units}; "
                f"give the number units via a constant"
            )
    return out


def _min(*args: Any) -> Any:
    if not args:
        raise EquationError("MIN needs at least one argument")
    return min(_align(args, "MIN"))


def _max(*args: Any) -> Any:
    if not args:
        raise EquationError("MAX needs at least one argument")
    return max(_align(args, "MAX"))


def _abs(x: Any) -> Any:
    return abs(x)


def _if_then_else(cond: Any, a: Any, b: Any) -> Any:
    a, b = _align((a, b), "IF_THEN_ELSE")
    return a if bool(cond) else b


def _dimensionless(x: Any, fname: str) -> float:
    if isinstance(x, Quantity):
        if not x.dimensionless:
            raise EquationError(f"{fname} needs a dimensionless argument, got {x.units}")
        return float(x.to("dimensionless").magnitude)
    return float(x)


def _exp(x: Any) -> Any:
    return Quantity(math.exp(_dimensionless(x, "EXP")), "dimensionless")


def _ln(x: Any) -> Any:
    v = _dimensionless(x, "LN")
    if v <= 0:
        raise EquationError(f"LN of a non-positive number ({v})")
    return Quantity(math.log(v), "dimensionless")


def _sqrt(x: Any) -> Any:
    if isinstance(x, Quantity):
        if x.magnitude < 0:
            raise EquationError(f"SQRT of a negative number ({x})")
        return x**0.5
    if x < 0:
        raise EquationError(f"SQRT of a negative number ({x})")
    return math.sqrt(x)


def interpolate(table: SDTableEntry, x: float) -> float:
    """Piecewise-linear lookup with clamp or linear extrapolation."""
    pts = table.points
    if x <= pts[0].x:
        if table.extrapolate == "clamp":
            return pts[0].y
        a, b = pts[0], pts[1]
    elif x >= pts[-1].x:
        if table.extrapolate == "clamp":
            return pts[-1].y
        a, b = pts[-2], pts[-1]
    else:
        i = next(i for i in range(1, len(pts)) if x <= pts[i].x)
        a, b = pts[i - 1], pts[i]
    return a.y + (b.y - a.y) * (x - a.x) / (b.x - a.x)


class Evaluator:
    """A reusable sandboxed evaluator. One per compiled model; rebinding names per step."""

    def __init__(self) -> None:
        self._table: SDTableEntry | None = None
        self._s = simpleeval.SimpleEval(
            operators=_OPERATORS,
            functions={
                "MIN": _min, "MAX": _max, "ABS": _abs, "IF_THEN_ELSE": _if_then_else,
                "STEP": self._step, "TABLE": self._table_lookup,
                "EXP": _exp, "LN": _ln, "SQRT": _sqrt,
            },
            names={},
        )

    def _step(self, height: Any, start: Any) -> Any:
        now = self._s.names[TIME]
        start_q = start if isinstance(start, Quantity) else Quantity(float(start), now.units)
        if isinstance(height, Quantity):
            return height if now >= start_q else height * 0
        return height if now >= start_q else 0.0

    def _table_lookup(self, x: Any) -> Any:
        table = self._table
        if table is None:
            raise EquationError("TABLE() is used but this variable has no table — add one with `sd set-table`")
        if isinstance(x, Quantity):
            x_val = float(x.to(table.x_units).magnitude)
        elif _is_number(x) and Quantity(1.0, table.x_units).dimensionless:
            x_val = float(x)
        else:
            raise EquationError(f"TABLE input is a bare number but the table expects {table.x_units}")
        return Quantity(interpolate(table, x_val), table.y_units)

    def evaluate(self, parsed: ParsedEquation, names: dict[str, Any], *, table: SDTableEntry | None = None) -> Any:
        self._s.names = names
        self._table = table
        try:
            return self._s.eval(parsed.expression, previously_parsed=parsed.node)
        except EquationError:
            raise
        except simpleeval.NameNotDefined as exc:
            raise EquationError(f"unknown variable {exc.name!r} in {parsed.expression!r}") from exc
        except simpleeval.InvalidExpression as exc:
            raise EquationError(f"invalid equation {parsed.expression!r}: {exc}") from exc
        except ZeroDivisionError as exc:
            raise EquationError(f"division by zero in {parsed.expression!r}") from exc
        except OverflowError as exc:
            raise EquationError(f"numeric overflow in {parsed.expression!r}") from exc
        except PINT_ERRORS as exc:
            detail = str(exc)
            if hasattr(exc, "units1") and hasattr(exc, "units2"):  # DimensionalityError
                detail = f"cannot combine {exc.units1 or 'dimensionless'} with {exc.units2 or 'dimensionless'}"
            raise EquationError(f"units don't match in {parsed.expression!r}: {detail}") from exc
        except (ValueError, TypeError) as exc:
            if "compare" in str(exc).lower():
                raise EquationError(
                    f"{parsed.expression!r} compares a quantity with units to a bare number; "
                    f"compare against a constant that has units, or use STEP(height, start_time) for time switches"
                ) from exc
            raise EquationError(f"cannot evaluate {parsed.expression!r}: {exc}") from exc
