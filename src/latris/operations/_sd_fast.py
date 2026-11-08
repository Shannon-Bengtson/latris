"""Float fast path for SD simulation — compiled once per model structure.

The pint path in ``sd_inference`` is the reference: it proves every equation
is dimensionally consistent. Once a model has passed that check, the units
no longer need re-proving on every step. This module compiles each equation
into plain-float Python, so a run costs microseconds per step rather than
pint's hundreds — which is what makes Monte Carlo, sensitivity sweeps and
loop-dominance scoring practical.

How it stays exact
------------------
Every quantity is carried as its magnitude in **SI base units**. For
multiplicative units, pint's arithmetic on quantities is then ordinary
arithmetic on base magnitudes (pint converts ``liter + milliliter`` to a common
unit; in base units both are already common). Conversions happen only where
pint gives a *bare number* an implicit unit, and each one is placed by a
compile-time "shadow" evaluation with pint that records, for every AST node,
whether it is a bare number, a quantity or a boolean:

- an equation whose result is a bare number takes its declared units;
- a bare time argument to STEP/RAMP/PULSE is in the model's time units;
- a bare argument aligned with a quantity in MIN/MAX/IF_THEN_ELSE takes that
  quantity's units;
- TABLE converts its input to the table's x units and returns y units.

Anything this compiler can't place exactly (offset units such as degC, a
boolean operator over non-booleans, a node the shadow can't type) makes
:func:`compile_model` return ``None`` and the caller uses the pint path.
Equivalence with the pint path is pinned by tests.

Security: equations are already whitelisted by ``_sd_eval.parse``; this
module re-checks every node against the same whitelist before generating any
code, generates code only from those node types, and executes it with empty
builtins and an explicit namespace of float helpers.
"""

from __future__ import annotations

import ast
import math
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Any

from latris.operations._sd_eval import (
    _ALLOWED_NODES,
    _MAX_EXPONENT,
    _OPERATORS,
    FUNCTIONS,
    TIME,
    EquationError,
    _if_then_else,
    _max,
    _min,
    interpolate,
)
from latris.operations._units import Quantity

if TYPE_CHECKING:
    from latris.operations.sd_inference import SDModel


class _Unsupported(Exception):
    """This model can't be compiled exactly; use the pint path."""


def _factor(unit: Any) -> float:
    """Multiplier from ``unit`` to SI base units; refuses offset units (degC, degF)."""
    zero = Quantity(0.0, unit).to_base_units().magnitude
    if zero != 0:
        raise _Unsupported(f"offset unit {unit}")
    return float(Quantity(1.0, unit).to_base_units().magnitude)


# ── float helpers available to generated code ────────────────────────


def _pow(a: float, b: float) -> float:
    if abs(b) > _MAX_EXPONENT:
        raise EquationError(f"exponent {b} is too large")
    return a**b


def _ite(cond: Any, a: Any, b: Any) -> Any:  # eager, like the pint path
    return a if bool(cond) else b


def _step(t: float, height: Any, start: float) -> Any:
    return height if t >= start else 0.0


def _ramp(t: float, slope: float, start: float, end: float | None = None) -> float:
    if t <= start:
        return 0.0
    stop = t if end is None else min(t, end)
    return slope * (stop - start)


def _pulse(t: float, start: float, width: float) -> float:
    return 1.0 if start <= t < start + width else 0.0


def _ln(x: float) -> float:
    if x <= 0:
        raise EquationError(f"LN of a non-positive number ({x})")
    return math.log(x)


def _sqrt(x: float) -> float:
    if x < 0:
        raise EquationError(f"SQRT of a negative number ({x})")
    return math.sqrt(x)


_HELPERS: dict[str, Any] = {
    "_pow": _pow,
    "_ite": _ite,
    "_step": _step,
    "_ramp": _ramp,
    "_pulse": _pulse,
    "_exp": math.exp,
    "_ln": _ln,
    "_sqrt": _sqrt,
    "min": min,
    "max": max,
    "abs": abs,
}

_BINOPS = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/"}
_CMPOPS = {ast.Gt: ">", ast.Lt: "<", ast.GtE: ">=", ast.LtE: "<=", ast.Eq: "==", ast.NotEq: "!="}


def _is_num(v: Any) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool)


# ── compiler ─────────────────────────────────────────────────────────


class _Compiler:
    """Turn one equation's AST into float code, typing each node by a pint shadow value."""

    def __init__(self, env: dict[str, Any], ref: Callable[[str], str], time_factor: float, table_names: dict[str, str]):
        self.env = env  # slug/TIME → pint value at the initial time
        self.ref = ref  # slug → expression reading its base magnitude
        self.tf = time_factor
        self.tables = table_names  # "current" → helper name for this equation's table
        self.table_entry = None

    def time_arg(self, code: str, val: Any) -> tuple[str, Any]:
        if isinstance(val, Quantity):
            return code, val
        return f"({code} * {self.tf!r})", Quantity(float(val), self.env[TIME].units)

    def align(self, items: list[tuple[str, Any]]) -> list[str]:
        ref = next((v for _, v in items if isinstance(v, Quantity)), None)
        if ref is None:
            return [c for c, _ in items]
        out = []
        for code, val in items:
            if isinstance(val, Quantity):
                out.append(code)
            elif _is_num(val):
                out.append(f"({code} * {_factor(ref.units)!r})")
            else:
                raise _Unsupported("non-numeric argument")
        return out

    def c(self, node: ast.AST) -> tuple[str, Any]:
        if not isinstance(node, _ALLOWED_NODES):
            raise _Unsupported(type(node).__name__)
        if isinstance(node, ast.Expression):
            return self.c(node.body)
        if isinstance(node, ast.Constant):
            if not _is_num(node.value):
                raise _Unsupported("non-numeric literal")
            return repr(node.value), node.value
        if isinstance(node, ast.Name):
            if node.id == TIME:
                return "_t", self.env[TIME]
            if node.id not in self.env:
                raise _Unsupported(f"unknown name {node.id}")
            return self.ref(node.id), self.env[node.id]
        if isinstance(node, ast.UnaryOp):
            code, val = self.c(node.operand)
            if isinstance(node.op, ast.USub):
                return f"(-{code})", -val
            if isinstance(node.op, ast.UAdd):
                return f"(+{code})", +val
            return f"(not {code})", not val
        if isinstance(node, ast.BinOp):
            (ca, va), (cb, vb) = self.c(node.left), self.c(node.right)
            val = _OPERATORS[type(node.op)](va, vb)
            if isinstance(node.op, ast.Pow):
                return f"_pow({ca}, {cb})", val
            return f"({ca} {_BINOPS[type(node.op)]} {cb})", val
        if isinstance(node, ast.Compare):
            code, left = self.c(node.left)
            parts, val, prev = [code], True, left
            for op_node, comp in zip(node.ops, node.comparators, strict=True):
                cc, cv = self.c(comp)
                parts.append(f"{_CMPOPS[type(op_node)]} {cc}")
                val = val and _OPERATORS[type(op_node)](prev, cv)
                prev = cv
            return f"({' '.join(parts)})", bool(val)
        if isinstance(node, ast.BoolOp):
            items = [self.c(v) for v in node.values]
            if not all(isinstance(v, bool) for _, v in items):
                raise _Unsupported("boolean operator over non-booleans")
            joiner = " and " if isinstance(node.op, ast.And) else " or "
            vals = [v for _, v in items]
            return f"({joiner.join(c for c, _ in items)})", all(vals) if isinstance(node.op, ast.And) else any(vals)
        if isinstance(node, ast.Call):
            return self.call(node)
        raise _Unsupported(type(node).__name__)

    def call(self, node: ast.Call) -> tuple[str, Any]:
        fname = node.func.id  # type: ignore[union-attr]
        if fname not in FUNCTIONS:
            raise _Unsupported(fname)
        args = [self.c(a) for a in node.args]
        vals = [v for _, v in args]
        if fname in ("MIN", "MAX"):
            if not args:
                raise _Unsupported("empty MIN/MAX")
            val = (_min if fname == "MIN" else _max)(*vals)
            return f"{fname.lower()}({', '.join(self.align(args))})", val
        if fname == "ABS":
            return f"abs({args[0][0]})", abs(vals[0])
        if fname == "IF_THEN_ELSE":
            cond, a, b = args
            ca, cb = self.align([a, b])
            return f"_ite({cond[0]}, {ca}, {cb})", _if_then_else(cond[1], a[1], b[1])
        now = self.env[TIME]
        if fname == "STEP":
            (ch, vh), start = args
            cs, vs = self.time_arg(*start)
            val = vh if now >= vs else (vh * 0 if isinstance(vh, Quantity) else 0.0)
            return f"_step(_t, {ch}, {cs})", val
        if fname == "RAMP":
            (cslope, vslope), *rest = args
            times = [self.time_arg(*a) for a in rest]
            start_q = times[0][1]
            stop = now if len(times) == 1 else min(now, times[1][1])
            val = vslope * (start_q - start_q) if now <= start_q else vslope * (stop - start_q)
            return f"_ramp(_t, {cslope}, {', '.join(c for c, _ in times)})", val
        if fname == "PULSE":
            (cs, vs), (cw, vw) = (self.time_arg(*a) for a in args)
            return f"_pulse(_t, {cs}, {cw})", 1.0 if vs <= now < vs + vw else 0.0
        if fname == "TABLE":
            table = self.table_entry
            if table is None:
                raise _Unsupported("TABLE without a table")
            ((cx, vx),) = args
            xf, yf = _factor(Quantity(1.0, table.x_units).units), _factor(Quantity(1.0, table.y_units).units)
            if isinstance(vx, Quantity):
                x_code, x_val = f"({cx} / {xf!r})", float(vx.to(table.x_units).magnitude)
            else:
                x_code, x_val = cx, float(vx)
            return f"({self.tables['current']}({x_code}) * {yf!r})", Quantity(interpolate(table, x_val), table.y_units)
        if fname in ("EXP", "LN"):
            ((cx, vx),) = args
            if isinstance(vx, Quantity) and not vx.dimensionless:
                raise _Unsupported(f"{fname} of a dimensional quantity")
            x = float(vx.to("dimensionless").magnitude) if isinstance(vx, Quantity) else float(vx)
            result = math.exp(x) if fname == "EXP" else math.log(x)
            return f"_{fname.lower()}({cx})", Quantity(result, "dimensionless")
        if fname == "SQRT":
            ((cx, vx),) = args
            return f"_sqrt({cx})", vx**0.5 if isinstance(vx, Quantity) else math.sqrt(vx)
        raise _Unsupported(fname)


@dataclass
class FastModel:
    """Generated float functions for one model structure (values are passed in)."""

    source: str
    const_ids: list[str]
    values: Callable[[float, list[float], list[float]], tuple[float, ...]]  # computed vars, base units
    deriv: Callable[[float, list[float], list[float]], list[float]]  # stock units per time unit
    out_factor: dict[str, float]  # computed var → base units per declared unit
    stock_factor: dict[str, float]
    time_factor: float
    equation: dict[str, Callable[[float, dict[str, float]], float]]  # per-variable, reads base values by slug

    def constants_vector(self, model: SDModel) -> list[float]:
        return [float(model.constants[c].to_base_units().magnitude) for c in self.const_ids]


def compile_model(model: SDModel) -> FastModel | None:
    """Compile ``model`` to float code, or ``None`` if it needs the pint path."""
    try:
        return _compile(model)
    except (_Unsupported, EquationError, ArithmeticError, ValueError, TypeError):
        return None
    except Exception:  # pint raises many types on odd inputs; any doubt → reference path
        return None


def _compile(model: SDModel) -> FastModel:
    from latris.operations.sd_inference import _base_names, _coerce

    tf = _factor(model.time_unit)
    stock_factor = {s: _factor(model.stock_units[s]) for s in model.stocks}
    out_factor = {v: _factor(model.eq_units[v]) for v in model.order}
    for c in model.constants.values():
        _factor(c.units)
    rate_factor = {s: _factor(model.stock_units[s] / model.time_unit) for s in model.stocks}

    const_ids = sorted(model.constants)
    var_of: dict[str, str] = {}
    for i, s in enumerate(model.stocks):
        var_of[model.slugs[s]] = f"s{i}"
    for i, c in enumerate(const_ids):
        var_of[model.slugs[c]] = f"c{i}"
    for i, v in enumerate(model.order):
        var_of[model.slugs[v]] = f"v{i}"

    y0 = [model.initial[s] for s in model.stocks]
    env = _base_names(model, model.settings.initial_time, y0)
    ns: dict[str, Any] = {"__builtins__": {}, **_HELPERS}
    body = ["    _t = t * TF"]
    body += [f"    s{i} = y[{i}] * {stock_factor[s]!r}" for i, s in enumerate(model.stocks)]
    body += [f"    c{i} = c[{i}]" for i in range(len(const_ids))]
    per_eq_src: dict[str, str] = {}

    for i, v in enumerate(model.order):
        table_name = f"_tab{i}"
        if v in model.tables:
            ns[table_name] = partial(interpolate, model.tables[v])
        comp = _Compiler(env, lambda slug: var_of[slug], tf, {"current": table_name})
        comp.table_entry = model.tables.get(v)
        tree = ast.parse(model.equations[v].expression, mode="eval")
        code, val = comp.c(tree)
        if isinstance(val, bool):
            raise _Unsupported("boolean equation")
        if _is_num(val):
            code = f"({code}) * {out_factor[v]!r}"
        body.append(f"    v{i} = {code}")
        env[model.slugs[v]] = _coerce(model, v, val)
        dict_comp = _Compiler(env, lambda slug: f"_e[{slug!r}]", tf, {"current": table_name})
        dict_comp.table_entry = model.tables.get(v)
        dcode, _ = dict_comp.c(tree)
        per_eq_src[v] = f"({dcode}) * {out_factor[v]!r}" if _is_num(val) else dcode

    ret_values = ", ".join(f"v{i}" for i in range(len(model.order)))
    derivs = []
    for s in model.stocks:
        terms = [f"v{model.order.index(f)}" for f in model.inflows.get(s, [])]
        terms += [f"-v{model.order.index(f)}" for f in model.outflows.get(s, [])]
        derivs.append(f"({' + '.join(terms) or '0.0'}) / {rate_factor[s]!r}")
    src = "\n".join(
        [
            "def _values(t, y, c):",
            *body,
            f"    return ({ret_values}{',' if len(model.order) == 1 else ''})",
            "def _deriv(t, y, c):",
            *body,
            f"    return [{', '.join(derivs)}]",
        ]
    )
    ns["TF"] = tf
    exec(compile(src, "<latris-sd-fast>", "exec"), ns)  # noqa: S102 - generated from whitelisted AST only
    equation = {}
    for v, code in per_eq_src.items():
        equation[v] = eval(compile(f"lambda _t, _e: {code}", "<latris-sd-eq>", "eval"), ns)  # noqa: S307
    return FastModel(
        source=src,
        const_ids=const_ids,
        values=ns["_values"],
        deriv=ns["_deriv"],
        out_factor=out_factor,
        stock_factor=stock_factor,
        time_factor=tf,
        equation=equation,
    )
