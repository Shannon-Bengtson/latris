"""Delay and smoothing functions — SMOOTH, SMOOTH3, DELAY1, DELAY3 — as hidden stocks and flows.

Every SD tool has these: a perceived value that lags the real one (SMOOTH), or
material that takes time to arrive (DELAY). They have memory, so they can't be
pure functions of the current step. Rather than teach every part of the engine
about them, each call is expanded into ordinary model structure before
analysis — hidden stocks with their flows and equations — so units, the fast
path, Monte Carlo and loop dominance all work on them unchanged:

- ``SMOOTH(x, T)``: a stock ``s`` in x's units, starting at x's initial value,
  with inflow ``(x − s) / T``; the function's value is ``s``.
- ``DELAY1(x, T)``: a stock ``L`` of material in transit (x's units × time),
  starting at ``x·T``, with inflow ``x`` and outflow ``L / T``; the function's
  value is the outflow.
- ``SMOOTH3`` / ``DELAY3``: three of those in a chain, each with ``T / 3``.

The variable that calls the function keeps its diagram links: its equation
becomes ``(value + 0·(x)) · (T / T)``, so it still reads exactly the inputs
drawn into it, while the hidden structure carries the dynamics. ``T`` must be a
time; a bare number is in the model's clock units, as for STEP.

Expansion needs x's units and initial value and T's value, so it runs after a
first analysis in which each call stands in for its input (``x · (T / T)``).
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Any

from latris.schema import Edge, Entity, RoleEntry
from latris.schema.sd import SDConstantEntry, SDEquationEntry, SDStockEntry

DELAY_FUNCTIONS = ("SMOOTH", "SMOOTH3", "DELAY1", "DELAY3")
_PATTERN = re.compile(r"\b(SMOOTH3?|DELAY[13])\s*\(")
HIDDEN_PREFIX = "sdhidden_"


def uses_delays(expressions: list[str]) -> bool:
    return any(_PATTERN.search(e or "") for e in expressions)


@dataclass
class Call:
    owner: str
    fname: str
    x: str  # source text of the input
    t: str  # source text of the delay time
    k: int
    # Filled in from the first pass:
    x_units: str = ""
    x0: float = 0.0  # x at the initial time, in x_units
    t0: float = 1.0  # the delay time at the initial time, in clock units
    t_bare: bool = False
    x_reads: list[str] = field(default_factory=list)  # variable ids x reads
    t_reads: list[str] = field(default_factory=list)  # variable ids T reads
    owner_label: str = ""

    @property
    def stages(self) -> int:
        return 3 if self.fname.endswith("3") else 1

    @property
    def smooth(self) -> bool:
        return self.fname.startswith("SMOOTH")

    def ident(self, part: str) -> str:
        return f"{HIDDEN_PREFIX}{self.k}_{part}"

    def label(self, part: str) -> str:
        """Readable in loop paths ("Smooth of Price [1.s1]"); unique per call and stage."""
        kind = "Smooth" if self.smooth else "Delay"
        return f"{kind} of {self.owner_label or self.owner} [{self.k + 1}.{part}]"

    def slug(self, part: str) -> str:
        from latris.operations._sd_eval import slugify

        return slugify(self.label(part))

    @property
    def out_part(self) -> str:
        return f"s{self.stages}" if self.smooth else f"out{self.stages}"


class _Replace(ast.NodeTransformer):
    def __init__(self, owner: str, start: int, mode: str, owner_label: str = ""):
        self.owner, self.k, self.mode, self.owner_label = owner, start, mode, owner_label
        self.calls: list[Call] = []

    def visit_Call(self, node: ast.Call) -> Any:  # noqa: N802 - ast API
        if isinstance(node.func, ast.Name) and node.func.id in DELAY_FUNCTIONS:
            if len(node.args) != 2 or node.keywords:
                raise ValueError(f"{node.func.id} takes two arguments: {node.func.id}(input, delay_time)")
            for a in node.args:
                for inner in ast.walk(a):
                    if (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name)
                            and inner.func.id in DELAY_FUNCTIONS):
                        raise ValueError(
                            f"{inner.func.id} inside {node.func.id} isn't supported; give the inner one its own "
                            "auxiliary"
                        )
            x, t = (ast.unparse(a) for a in node.args)
            call = Call(self.owner, node.func.id, x, t, self.k, owner_label=self.owner_label)
            self.k += 1
            self.calls.append(call)
            ratio = f"(({t}) / ({t}))"
            value = x if self.mode == "stand-in" else call.slug(call.out_part)
            text = f"(({x}) * {ratio})" if self.mode == "stand-in" else f"(({value}) + 0 * ({x})) * {ratio}"
            return ast.parse(text, mode="eval").body
        return self.generic_visit(node)


def rewrite(expression: str, owner: str, start: int, mode: str, owner_label: str = "") -> tuple[str, list[Call]]:
    """``mode='stand-in'``: each call → its input (first pass). ``'expanded'``: → the hidden value."""
    tree = ast.parse(expression, mode="eval")
    r = _Replace(owner, start, mode, owner_label)
    new = r.visit(tree)
    return ast.unparse(ast.fix_missing_locations(new)), r.calls


@dataclass
class Expansion:
    entities: list[Entity] = field(default_factory=list)
    roles: list[RoleEntry] = field(default_factory=list)
    equations: list[SDEquationEntry] = field(default_factory=list)
    stocks: list[SDStockEntry] = field(default_factory=list)
    constants: list[SDConstantEntry] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    hidden: set[str] = field(default_factory=set)


def expand(calls: list[Call], *, clock: str) -> Expansion:
    """The hidden stocks, flows, equations and links for every call (first-pass facts filled in)."""
    out = Expansion()

    def node(call: Call, part: str, role: str) -> str:
        eid = call.ident(part)
        out.entities.append(Entity(id=eid, kind="variable", label=call.label(part)))
        out.roles.append(RoleEntry(target_id=eid, value=role))
        out.hidden.add(eid)
        return eid

    def link(a: str, b: str, kind: str) -> None:
        out.edges.append(Edge(id=f"{HIDDEN_PREFIX}e{len(out.edges)}", from_id=a, to_id=b, kind=kind))

    for call in calls:
        n = call.stages
        t_text, t_reads = call.t, list(call.t_reads)
        if call.t_bare:
            tid = node(call, "time", "constant")
            out.constants.append(SDConstantEntry(target_id=tid, value=call.t0, units=clock))
            t_text, t_reads = call.slug("time"), [tid]
        stage_t = f"(({t_text}) / {n})"
        source_text, source_reads = f"({call.x})", list(call.x_reads)
        if call.smooth:
            for i in range(1, n + 1):
                s, f = node(call, f"s{i}", "stock"), node(call, f"adj{i}", "flow")
                out.stocks.append(SDStockEntry(target_id=s, initial_value=call.x0, units=call.x_units))
                out.equations.append(SDEquationEntry(
                    target_id=f, expression=f"({source_text} - {call.slug(f's{i}')}) / {stage_t}",
                    units=f"({call.x_units}) / ({clock})",
                ))
                link(f, s, "flow")
                for r in dict.fromkeys([*source_reads, *t_reads]):
                    link(r, f, "causal")
                source_text, source_reads = call.slug(f"s{i}"), [s]
        else:
            cloud = node(call, "cloud", "source_sink")
            inflow = node(call, "in1", "flow")
            out.equations.append(SDEquationEntry(target_id=inflow, expression=source_text, units=call.x_units))
            link(cloud, inflow, "flow")
            for r in dict.fromkeys(source_reads):
                link(r, inflow, "causal")
            upstream = inflow
            for i in range(1, n + 1):
                stock, outflow = node(call, f"l{i}", "stock"), node(call, f"out{i}", "flow")
                out.stocks.append(SDStockEntry(
                    target_id=stock, initial_value=call.x0 * call.t0 / n, units=f"({call.x_units}) * ({clock})",
                ))
                out.equations.append(SDEquationEntry(
                    target_id=outflow, expression=f"{call.slug(f'l{i}')} / {stage_t}", units=call.x_units,
                ))
                link(upstream, stock, "flow")
                link(stock, outflow, "flow")
                for r in dict.fromkeys(t_reads):
                    link(r, outflow, "causal")
                upstream = outflow
            link(upstream, cloud, "flow")
        link(call.ident(call.out_part), call.owner, "causal")
    return out
