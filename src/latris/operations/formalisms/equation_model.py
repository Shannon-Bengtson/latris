"""Equation model as a formalism plugin — sourced formulas with units, no clock (``operations/equation_model.py``)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from latris.operations.formalisms import (
    ChatOp,
    ChatTool,
    Formalism,
    ResultKind,
    default_origin,
    register,
    spec_verification,
)

_ROLE_NAMES = {"input": "Input", "parameter": "Parameter", "computed": "Computed", "output": "Output"}


def _g(x: float | None) -> str:
    return "—" if x is None else f"{x:,.4g}"


def _u(units: str) -> str:
    from latris.operations._units import display

    return display(units)


def _v(x: float | None, units: str) -> str:
    """A value with its units as a reader sees them."""
    from latris.operations._units import with_units

    return with_units(_g(x), units)


def _range(lo: float | None, hi: float | None, units: str = "") -> str:
    if lo is None and hi is None:
        return "—"
    tail = f" {_u(units)}" if units and _u(units) else ""
    if lo is None:
        return f"up to {_g(hi)}{tail}"
    if hi is None:
        return f"from {_g(lo)}{tail}"
    return f"{_g(lo)} – {_g(hi)}{tail}"


def _outside_lines(arms: list[dict[str, Any]]) -> list[str]:
    out = []
    for a in arms:
        for o in a["outside"]:
            out.append(f"{o['quantity']} = {_v(o['value'], o['units'])} under {a['name']} is outside its valid "
                       f"range ({_range(o['valid_min'], o['valid_max'], o['units'])})")
    return out


# ── report sections ──────────────────────────────────────────────────


def _render_evaluation(p: dict[str, Any]) -> list[str]:
    from latris.exporters import md
    from latris.operations.equation_model import describe

    out = [md.esc(describe(p)) + ".", ""]
    arms = p["arms"]
    ref = arms[0]["values"]
    rows = []
    for q in p["quantities"]:
        defined = f"`{q['formula']}`" if q["formula"] else _range(q["valid_min"], q["valid_max"])
        rows.append([q["quantity"], _ROLE_NAMES[q["role"]], _v(ref[q["quantity"]], q["units"]), defined,
                     (md.esc(q["source"]) if q["source"] else "—") + ("; not verified" if q["weak"] else "")])
    out += md.table(["Quantity", "Role", "Value", "Formula, or valid range", "Source"], rows)
    if len(arms) > 1:
        units = p["units"]
        rows = [[a["name"], ", ".join(f"{c['quantity']} = {_v(c['value'], c['units'])}" for c in a["changes"]) or "—",
                 *(_v(a["values"][o], units[o]) for o in p["outputs"])] for a in arms]
        out += ["Under each scenario:", ""]
        out += md.table(["Scenario", "What it changes", *p["outputs"]], rows)
    outside = _outside_lines(arms)
    if outside:
        out += ["Outside the range the sources cover (an extrapolation, shown as computed):", ""]
        out += [f"- {md.esc(line)}" for line in outside] + [""]
    return out


def _render_sweep(p: dict[str, Any]) -> list[str]:
    from latris.exporters import md
    from latris.operations.equation_model import describe_sweep

    out = [md.esc(describe_sweep(p)) + ".", ""]
    xs, ys = p["x"], p["series"][p["target"]]
    step = max(1, (len(xs) - 1) // (md.MAX_ROWS - 1))
    picks = sorted(set(range(0, len(xs), step)) | {len(xs) - 1})
    rows = [[_v(xs[i], p["input_units"]), "can't be evaluated" if ys[i] is None else _v(ys[i], p["target_units"])]
            for i in picks]
    out += md.table([p["input"], p["target"]], rows)
    out += [f"Reference: {p['input']} = {_v(p['reference']['x'], p['input_units'])} gives "
            f"{_v(p['reference']['y'], p['target_units'])}. Every other value is held at its reference.", ""]
    if p["valid_min"] is not None or p["valid_max"] is not None:
        out += [f"{p['input']} is valid over {_range(p['valid_min'], p['valid_max'], p['input_units'])}"
                + ("; the sweep goes beyond it, so part of the curve is an extrapolation." if p["extrapolated"]
                   else "; the sweep stays inside it."), ""]
    return out


def _render_monte_carlo(p: dict[str, Any]) -> list[str]:
    from latris.exporters import md
    from latris.operations.equation_model import describe_monte_carlo

    out = [md.esc(describe_monte_carlo(p)) + ".", ""]
    rows = [[o["output"] + (f" ({_u(o['units'])})" if _u(o["units"]) else ""), _g(o["point"]), _g(o["mean"]),
             _g(o["p5"]), _g(o["p50"]), _g(o["p95"])] for o in p["outputs"][:md.MAX_ROWS]]
    out += md.table(["Output", "At the reference values", "Mean", "5th pct", "Median", "95th pct"], rows)
    if p["drivers"]:
        rows = [[d["input"], f"{d['distribution']} (5th–95th: {_g(d['p5'])} – {_v(d['p95'], d['units'])})",
                 "—" if d["spearman"] is None else f"{d['spearman']:+.2f}", md.esc(d["reason"]) or "—",
                 "unverified" if d["weak"] else "verified"] for d in p["drivers"][:md.MAX_ROWS]]
        out += [f"What drives the spread in {p['primary']}: each uncertain value's range and its rank correlation "
                "with the result.", ""]
        out += md.table(["Value", "Range", "Rank correlation", "Why this range", "Range checked"], rows)
    beyond = [d for d in p["drivers"] if d["outside_valid"] > 0]
    if beyond:
        out += ["Ranges that reach outside the value's stated valid range: "
                + md.esc("; ".join(f"{d['input']} ({d['outside_valid']:.0%} of runs)" for d in beyond)) + ".", ""]
    if p["fixed"]:
        out += ["Held fixed (no range given): " + md.esc(", ".join(p["fixed"][:md.MAX_ROWS * 2])) + ".", ""]
    dropped = p["runs"] - p["evaluated"]
    out += [f"{p['runs']} runs, {'Latin hypercube' if p['sampling'] == 'lhs' else 'random'} sampling, seed "
            f"{p['seed']}" + (f"; {dropped} left out because the formulas couldn't be evaluated there" if dropped
                              else "") + ". Values are sampled independently.", ""]
    return out


# ── charts ───────────────────────────────────────────────────────────


def _charts_evaluation(p: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [("eq-scenarios", {})] if len(p.get("arms") or []) > 1 else []


# ── claims from results ──────────────────────────────────────────────


def _claims_evaluation(p: dict[str, Any], out: dict[str, list[str]]) -> None:
    from latris.operations.equation_model import describe

    out["answer_to_question"].append(describe(p) + ".")
    outside = _outside_lines(p["arms"])
    if outside:
        out["assumptions_limitations"].append(
            "Some values are outside the range their sources cover, so these results extrapolate: "
            + "; ".join(outside[:4]) + ".")
    if p["unverified"]:
        out["open_questions"].append(
            f"{len(p['unverified'])} value(s) or formula(s) haven't been checked against a source: "
            + ", ".join(p["unverified"][:6]) + ".")


def _claims_sweep(p: dict[str, Any], out: dict[str, list[str]]) -> None:
    from latris.operations.equation_model import describe_sweep

    out["sensitivity"].append(describe_sweep(p) + ".")
    if p["extrapolated"]:
        out["assumptions_limitations"].append(
            f"The sweep of {p['input']} goes beyond its valid range "
            f"({_range(p['valid_min'], p['valid_max'], p['input_units'])}); outside it the curve is an extrapolation.")


def _claims_monte_carlo(p: dict[str, Any], out: dict[str, list[str]]) -> None:
    from latris.operations.equation_model import describe_monte_carlo

    out["sensitivity"].append(describe_monte_carlo(p) + ".")
    main = next(o for o in p["outputs"] if o["output"] == p["primary"])
    out["confidence_assessment"].append(
        f"Given the stated ranges, {p['primary']} is between {_g(main['p5'])} and "
        f"{_v(main['p95'], main['units'])} in 90% of runs.")
    weak = [d["input"] for d in p["drivers"][:3] if d["weak"] and d["spearman"] and abs(d["spearman"]) >= 0.3]
    if weak:
        out["open_questions"].append(
            f"The ranges driving most of the uncertainty in {p['primary']} haven't been checked: {', '.join(weak)}.")
    if p["fixed"]:
        out["assumptions_limitations"].append(
            f"The Monte Carlo treats {len(p['fixed'])} value(s) as exact (no range given), so the spread it shows "
            "is a lower bound on the real uncertainty.")


# ── claims from the model itself ─────────────────────────────────────


def _claims(paths, section: str) -> list[str]:
    from latris.operations import equation_model as eq

    m = eq.load(root=paths.root)
    lab = m.labels
    if m.problems:
        first = m.problems[0]
        return [f"The equation model is incomplete: {len(m.problems)} structure problem(s) (e.g. "
                f"{lab.get(first.target_id or '', '(model)')}: {first.message})"] if section == "structure" else []
    count = {r: sum(1 for v in m.roles.values() if v == r) for r in ("input", "parameter", "computed", "output")}
    values = eq.compute(m)
    claims: list[str] = []
    if section == "structure":
        claims.append(f"{count['input']} input(s) and {count['parameter']} parameter(s) feed "
                      f"{count['computed'] + count['output']} formula(s); the result is "
                      + ", ".join(lab[i] for i in m.outputs) + ".")
        claims += [f"{lab[i]} = {m.formulas[i].expression}" + (f" [{_u(m.formulas[i].units)}]"
                   if _u(m.formulas[i].units) else "") for i in m.order][:8]
    elif section == "answer":
        claims.append("; ".join(f"{lab[i]} = {_v(values[i], m.quantity_units(i))}" for i in m.outputs)
                      + " at the reference values.")
    elif section == "sensitivity":
        ranges = eq.specs(paths)
        claims.append(f"{len(ranges)} of {len(m.values)} input(s) and parameter(s) carry an uncertainty range."
                      if ranges else "No input or parameter carries an uncertainty range yet.")
    elif section == "implications":
        outside = eq.outside_range(m, values)
        if outside:
            claims.append("The reference values are outside the range their sources cover for: "
                          + ", ".join(o["quantity"] for o in outside) + ". Treat the result as an extrapolation.")
        else:
            bounded = sum(1 for v in m.values.values() if v.valid_min is not None or v.valid_max is not None)
            claims.append(f"Every value with a stated valid range ({bounded} of {len(m.values)}) is inside it at "
                          "the reference values.")
    elif section == "gaps":
        unbounded = [lab[i] for i in eq._by_label(m.values, lab)
                     if m.values[i].valid_min is None and m.values[i].valid_max is None]
        if unbounded:
            claims.append(f"No valid range stated for: {', '.join(unbounded[:8])}.")
    return claims


# ── diagram ──────────────────────────────────────────────────────────

_SHAPES = {"input": ('(["', '"])'), "parameter": ('("', '")'), "computed": ('["', '"]'), "output": ('[["', '"]]')}


def _mermaid(paths, entities, edges) -> str:  # noqa: ANN001
    """Inputs and parameters on the left with their values, formulas to the right; an arrow is "is read by"."""
    from latris.exporters.mermaid import _mermaid_text
    from latris.operations import equation_model as eq

    m = eq.load(root=paths.root, check_units=False)
    if not m.roles:
        return ""
    ids = [i for i in eq._by_label(m.roles, m.labels)]
    alias = {i: f"q{k}" for k, i in enumerate(ids)}
    lines = ["flowchart LR"]
    for i in ids:
        left, right = _SHAPES[m.roles[i]]
        text = _mermaid_text(m.labels[i])
        if i in m.values:
            text += f"<br/>{_mermaid_text(_v(m.values[i].value, m.values[i].units))}"
        elif i in m.formulas and _u(m.formulas[i].units):
            text += f"<br/>{_mermaid_text(_u(m.formulas[i].units))}"
        lines.append(f"    {alias[i]}{left}{text}{right}")
    for i in ids:
        lines += [f"    {alias[d]} --> {alias[i]}" for d in m.reads.get(i, []) if d in alias]
    return "\n".join(lines) + "\n"


# ── readiness, outcome, scope ────────────────────────────────────────


def _problems(root: Path) -> list:
    from latris.operations import equation_model as eq

    return eq.structure_problems(root=root)


def _outcome_ids(paths) -> set[str]:
    from latris.operations import equation_model as eq

    return {i for i, r in eq.get_roles(root=paths.root).items() if r == "output"}


def _set_outcome(target: str, root: Path):
    from latris.operations import equation_model as eq

    return eq.set_role(target, "output", root=root)


def _parameterised_nodes(paths) -> set[str]:
    from latris.operations import equation_model as eq

    return set(eq.get_roles(root=paths.root))


def _parameter_sources(paths) -> dict[str, bool]:
    """The quantities whose value or formula names a source, and whether a person has verified it."""
    from latris.operations import equation_model as eq

    entries = [*eq.get_values(root=paths.root).entries, *eq.get_formulas(root=paths.root).entries]
    return {e.target_id: not e.is_weak for e in entries if e.source_id}


# ── build spec and share link ────────────────────────────────────────


def _check(block: Any, known: Any, outcome: str | None) -> list[str]:
    names = ([("equation_model value", v.node) for v in block.values]
             + [("equation_model formula", f.node) for f in block.formulas]
             + [("equation_model uncertainty", u.node) for u in block.uncertainty])
    return [f"{where}: no factor named {n!r}" for where, n in names if not known(n)]


def _info(block: Any, root: Path) -> list[str]:
    """Which factor each formula's names resolve to, so a misspelt name shows at once."""
    from latris.operations import equation_model as eq

    return [f"{f.node} reads: " + (", ".join(f"{k} = {v}" for k, v in reads.items()) or "nothing")
            for f in block.formulas for reads in [eq.formula_reads(f.expression, root=root)]]


def _apply(block: Any, verified_by: str, root: Path) -> int:
    """Roles first (a formula may read a quantity defined after it), then values, formulas, ranges, scenarios."""
    from latris.operations import equation_model as eq

    origin = default_origin(verified_by)
    n = 0
    for f in block.formulas:
        eq.ensure_role(f.node, f.role, root=root)
    for v in block.values:
        eq.set_value(v.node, v.value, v.units, role=v.role, valid_min=v.valid_min, valid_max=v.valid_max,
                     notes=v.notes, origin=v.origin or origin, source_id=v.source,
                     verification=spec_verification(v.verified, verified_by), root=root)
        n += 1
    for f in block.formulas:
        eq.set_formula(f.node, f.expression, f.units, role=f.role, notes=f.notes, origin=f.origin or origin,
                       source_id=f.source, verification=spec_verification(f.verified, verified_by), root=root)
        n += 1
    for u in block.uncertainty:
        eq.set_uncertainty(u.node, u.distribution, dict(u.params), reason=u.reason, source_id=u.source,
                           origin=u.origin or origin, verification=spec_verification(u.verified, verified_by),
                           root=root)
        n += 1
    for s in block.scenarios:
        eq.set_scenario(s.name, list(s.set), description=s.description, reason=s.reason, origin=s.origin or origin,
                        source_id=s.source, verification=spec_verification(s.verified, verified_by), root=root)
        n += 1
    return n


def _export(paths, labels: dict[str, str]):
    from latris.operations import equation_model as eq
    from latris.schema.build_spec import (
        SpecEquationFormula,
        SpecEquationModel,
        SpecEquationScenario,
        SpecEquationUncertainty,
        SpecEquationValue,
    )

    roles = {k: v for k, v in eq.get_roles(root=paths.root).items() if k in labels}
    if not roles:
        return None

    def verified(e) -> bool:
        return e.verification == "human-verified"

    values = [SpecEquationValue(node=labels[e.target_id], role=roles[e.target_id], value=e.value,  # type: ignore[arg-type]
                                units=e.units, valid_min=e.valid_min, valid_max=e.valid_max, notes=e.notes,
                                source=e.source_id, origin=e.origin, verified=verified(e))
              for e in eq.get_values(root=paths.root).entries if roles.get(e.target_id) in eq.VALUE_ROLES]
    formulas = [SpecEquationFormula(node=labels[e.target_id], role=roles[e.target_id],  # type: ignore[arg-type]
                                    expression=e.expression, units=e.units, notes=e.notes, source=e.source_id,
                                    origin=e.origin, verified=verified(e))
                for e in eq.get_formulas(root=paths.root).entries if roles.get(e.target_id) in eq.FORMULA_ROLES]
    ranges = [SpecEquationUncertainty(node=labels[e.target_id], distribution=e.distribution,  # type: ignore[arg-type]
                                      params=dict(e.params), reason=e.reason, source=e.source_id, origin=e.origin,
                                      verified=verified(e))
              for e in eq.specs(paths).values() if e.target_id in roles]
    scenarios = [SpecEquationScenario(name=s.name, description=s.description, reason=s.reason, source=s.source_id,
                                      origin=s.origin, verified=verified(s),
                                      set=[f"{labels[o.target_id]}={o.value!r} {o.units}" for o in s.overrides])
                 for s in eq.get_scenarios(root=paths.root).scenarios
                 if all(o.target_id in labels for o in s.overrides)]
    key = lambda x: x.node  # noqa: E731
    return SpecEquationModel(values=sorted(values, key=key), formulas=sorted(formulas, key=key),
                             uncertainty=sorted(ranges, key=key), scenarios=scenarios)


# ── running and replaying analyses ───────────────────────────────────


def _run_evaluate(a, root: Path) -> str:
    from latris.operations import equation_model as eq

    payload = eq.evaluate(scenarios=list(a.scenarios) or None, set=list(a.set) or None, root=root)
    if payload["problems"]:
        raise ValueError(eq.describe(payload))
    return eq.record(payload, root=root)[1]


def _def_evaluate(p: dict[str, Any]):
    from latris.schema.build_spec import make_analysis

    return make_analysis(kind="eq_evaluate", scenarios=list(p["scenarios"]), set=list(p["set"]))


def _run_sweep(a, root: Path) -> str:
    from latris.operations import equation_model as eq

    payload = eq.sweep(input=a.input, target=a.target, low=a.low, high=a.high, steps=a.steps or 25, root=root)
    return eq.record_sweep(payload, root=root)[1]


def _def_sweep(p: dict[str, Any]):
    from latris.schema.build_spec import make_analysis

    return make_analysis(kind="eq_sweep", input=p["input"], target=p["target"], low=p["low"], high=p["high"],
                         steps=p["steps"])


def _run_monte_carlo(a, root: Path) -> str:
    from latris.operations import equation_model as eq

    payload = eq.monte_carlo(runs=a.runs or 2000, seed=a.seed if a.seed is not None else 1234,
                             sampling=a.sampling or "lhs", target=a.target, root=root)
    return eq.record_monte_carlo(payload, root=root)[1]


def _def_monte_carlo(p: dict[str, Any]):
    from latris.schema.build_spec import make_analysis

    return make_analysis(kind="eq_monte_carlo", runs=p["runs"], seed=p["seed"], sampling=p["sampling"],
                         target=p["primary"])


# How a chat assistant runs each analysis (latris-app generates the tool from the manifest).
_TOOLS = {
    "eq-evaluation": ("evaluate_equations",
        "Work out an equation model: the value of every quantity at the model's reference inputs and under each "
        "saved scenario (scenarios: names, default all; set: unsaved 'Quantity=value [units]' values to try), "
        "flagging any input or parameter outside its valid range. Recorded with a chart."),
    "eq-sweep": ("sweep_equations",
        "How does an equation model's output respond to one input? Moves input from low to high (default: its "
        "valid range) in steps, holding everything else at its reference value, and gives the curve for target "
        "(default: the first output), its shape and the elasticity at the reference value. Recorded with a chart."),
    "eq-monte-carlo": ("monte_carlo_equations",
        "How sure is an equation model's result? Samples every input and parameter given an uncertainty range, "
        "recomputes the formulas, and gives each output's percentiles and which values drive the spread (runs, "
        "seed, sampling; target: the output to headline). Recorded with a chart."),
}

# How a chat assistant writes this type's build-spec block (latris-app generates each operation).
_CHAT_OPS = (
    ChatOp("set_equation_value", ("values",),
        "Make a factor an input (something the model is given) or a parameter (a coefficient of the method) and "
        "set its value and units, the range it is valid over (valid_min, valid_max) and its source."),
    ChatOp("set_equation_formula", ("formulas",),
        "Make a factor a computed quantity or an output and set its formula and the units it gives. The formula "
        "names other quantities by slugified label (Hydraulic radius → hydraulic_radius); arithmetic, ** and "
        "MIN, MAX, ABS, IF_THEN_ELSE, EXP, LN, LOG10, SQRT, SIN, COS, TAN, MODULO. Give the formula's source."),
    ChatOp("set_equation_uncertainty", ("uncertainty",),
        "Give an input or parameter a distribution over its value (uniform, triangular, normal, lognormal, beta, "
        "gamma) with the reason for it, for the Monte Carlo."),
    ChatOp("set_equation_scenario", ("scenarios",),
        "Save a named set of input values to evaluate ('Quantity=value [units]' assignments), e.g. a design case."),
)

register(Formalism(
    model_type="equation_model",
    outcome_role="output",
    outcome_refusal=("An equation model's results are its outputs: mark one with `latris eq formula <factor> "
                     "\"<formula>\" <units> --output` (or `latris eq role <factor> output`)."),
    outcome_ids=_outcome_ids,
    set_outcome=_set_outcome,
    structure_problems=_problems,
    validators={
        "eq_quantities_complete": ("eq_no_output", "eq_no_value", "eq_no_formula"),
        "eq_formulas_valid": ("eq_formula_invalid", "eq_unknown_reference", "eq_name_collision", "eq_circular",
                              "eq_units"),
        "eq_links_match": ("eq_missing_link", "eq_unused_link"),
    },
    claims=_claims,
    centrality=False,
    own_implications=True,
    sensitivity_fallback="Give the inputs and parameters uncertainty ranges and run the Monte Carlo to see how "
                         "sure the result is.",
    results=(
        ResultKind(tool=ChatTool(*_TOOLS["eq-evaluation"]), kind="eq-evaluation", title="Equation model: results",
                   render=_render_evaluation, analysis="eq_evaluate", run=_run_evaluate, definition=_def_evaluate,
                   claims=_claims_evaluation, charts=_charts_evaluation, chart_kinds=("eq-scenarios",)),
        ResultKind(tool=ChatTool(*_TOOLS["eq-sweep"]), kind="eq-sweep", title="Equation model: response to an input",
                   render=_render_sweep, analysis="eq_sweep", run=_run_sweep, definition=_def_sweep,
                   claims=_claims_sweep, charts=lambda p: [("eq-response", {})], chart_kinds=("eq-response",),
                   subtitle=lambda p: f"{p['target']} against {p['input']}"),
        ResultKind(tool=ChatTool(*_TOOLS["eq-monte-carlo"]), kind="eq-monte-carlo",
                   title="Equation model: uncertainty (Monte Carlo)", render=_render_monte_carlo,
                   analysis="eq_monte_carlo", run=_run_monte_carlo, definition=_def_monte_carlo,
                   claims=_claims_monte_carlo, charts=lambda p: [("mc-strip", {})], chart_kinds=("mc-strip",)),
    ),
    scope_noun="equation model",
    source_label="Equations",
    parameterised_nodes=_parameterised_nodes,
    parameter_sources=_parameter_sources,
    links_from_values=True,
    scenario_store="latris.operations.equation_model_scenarios",
    spec_field="equation_model",
    spec_check=_check,
    spec_apply=_apply,
    spec_export=_export,
    spec_info=_info,
    chat_ops=_CHAT_OPS,
    mermaid=_mermaid,
    cli=("latris.cli.eq_cmd", "eq"),
    routes="latris.server.routes.equation_model",
))
