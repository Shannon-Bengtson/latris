"""Equation model CLI — inputs, parameters, formulas, scenarios, ranges, check, evaluate, sweep, Monte Carlo."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from latris.cli._errors import handle_cli_errors
from latris.cli._options import ORIGIN_HELP, verification
from latris.cli._output import emit

app = typer.Typer(help="Equation model: quantities joined by sourced formulas, with units and no clock.",
                  no_args_is_help=True)
console = Console()

_MIN_HELP = "Bottom of the range the value is valid over (usually what its source covered)."
_MAX_HELP = "Top of the valid range."


def _sha(sha: str) -> str:
    return f"commit [cyan]{sha[:10]}[/cyan]"


def _g(x) -> str:
    return "—" if x is None else f"{x:,.4g}"


def _v(x, units: str | None) -> str:
    from latris.operations.equation_model import fmt

    return escape(fmt(x, units or "dimensionless"))


def _u(units: str) -> str:
    from latris.operations._units import display

    return escape(display(units))


def _set_value(role: str, target: str, value: float, units: str, valid_min, valid_max, source, origin, verified,
               notes) -> None:
    from latris.operations import equation_model as eq

    entry, sha = eq.set_value(target, value, units, role=role, valid_min=valid_min, valid_max=valid_max, notes=notes,
                              origin=origin, source_id=source, verification=verification(verified))
    emit(entry, human=lambda: console.print(f"[green]{role}[/green] {escape(target)} = {_v(value, entry.units)} · "
                                            f"{_sha(sha)}"), commit_sha=sha)


@app.command("input")
@handle_cli_errors
def input_(
    target: str = typer.Argument(..., help="Node ID, ID prefix, or label."),
    value: float = typer.Argument(..., help="Its reference value."),
    units: str = typer.Argument(..., help="Units, e.g. m, m/s, kg/m**3, dimensionless."),
    valid_min: float = typer.Option(None, "--min", help=_MIN_HELP),
    valid_max: float = typer.Option(None, "--max", help=_MAX_HELP),
    source: str = typer.Option(None, "--source", help="Source ID the value comes from."),
    origin: str = typer.Option("human-direct", "--origin", help=ORIGIN_HELP),
    verified: bool = typer.Option(False, "--verified", help="A person has checked it against its source."),
    notes: str = typer.Option(None, "--notes"),
) -> None:
    """Make a factor an input (something the model is given) and set its reference value."""
    _set_value("input", target, value, units, valid_min, valid_max, source, origin, verified, notes)


@app.command("parameter")
@handle_cli_errors
def parameter(
    target: str = typer.Argument(..., help="Node ID, ID prefix, or label."),
    value: float = typer.Argument(..., help="Its value."),
    units: str = typer.Argument(..., help="Units, e.g. s/m**(1/3), 1/year, dimensionless."),
    valid_min: float = typer.Option(None, "--min", help=_MIN_HELP),
    valid_max: float = typer.Option(None, "--max", help=_MAX_HELP),
    source: str = typer.Option(None, "--source", help="Source ID the value comes from."),
    origin: str = typer.Option("human-direct", "--origin", help=ORIGIN_HELP),
    verified: bool = typer.Option(False, "--verified", help="A person has checked it against its source."),
    notes: str = typer.Option(None, "--notes"),
) -> None:
    """Make a factor a parameter (a coefficient of the method) and set its value."""
    _set_value("parameter", target, value, units, valid_min, valid_max, source, origin, verified, notes)


@app.command("formula")
@handle_cli_errors
def formula(
    target: str = typer.Argument(..., help="Node ID, ID prefix, or label."),
    expression: str = typer.Argument(..., help="The formula, e.g. \"velocity * width * depth\"."),
    units: str = typer.Argument(..., help="The units the formula gives, e.g. m**3/s."),
    output: bool = typer.Option(False, "--output", help="This quantity is a result of the model."),
    source: str = typer.Option(None, "--source", help="Source ID the formula comes from."),
    origin: str = typer.Option("human-direct", "--origin", help=ORIGIN_HELP),
    verified: bool = typer.Option(False, "--verified", help="A person has checked it against its source."),
    notes: str = typer.Option(None, "--notes", help="The conditions the formula holds under."),
    no_link: bool = typer.Option(False, "--no-link", help="Don't add the links the formula needs to the map."),
) -> None:
    """Make a factor a computed quantity (or, with --output, a result) and set its formula.

    Other quantities are named by slugified label (Hydraulic radius →
    hydraulic_radius) and must be in the model already, so work from the
    inputs up. Arithmetic, ** and MIN, MAX, ABS, IF_THEN_ELSE, EXP, LN,
    LOG10, SQRT, SIN, COS, TAN, MODULO. The units are checked when the
    model is: a formula that adds metres to seconds is refused.
    """
    from latris.operations import equation_model as eq

    entry, sha = eq.set_formula(target, expression, units, role="output" if output else "computed", notes=notes,
                                origin=origin, source_id=source,  # type: ignore[arg-type]
                                verification=verification(verified), link=not no_link)
    emit(entry, human=lambda: console.print(f"[green]formula[/green] {escape(target)} = {escape(entry.expression)} "
                                            f"(in {_u(entry.units) or 'no units'}) · {_sha(sha)}"),
         commit_sha=sha)


@app.command("role")
@handle_cli_errors
def role(
    target: str = typer.Argument(..., help="Node ID, ID prefix, or label."),
    kind: str = typer.Argument(..., help="input | parameter | computed | output"),
) -> None:
    """Change a quantity's role (e.g. make a computed quantity an output)."""
    from latris.operations import equation_model as eq

    target_id, sha = eq.set_role(target, kind)
    emit({"target_id": target_id, "role": kind},
         human=lambda: console.print(f"[green]set[/green] {escape(target)} → {kind} · {_sha(sha)}"), commit_sha=sha)


@app.command("remove")
@handle_cli_errors
def remove(target: str = typer.Argument(..., help="Node ID, ID prefix, or label.")) -> None:
    """Take a factor out of the equation model (its role, value or formula and range); the factor itself stays."""
    from latris.operations import equation_model as eq

    target_id, removed, sha = eq.remove(target)
    emit({"target_id": target_id, "rows_removed": removed},
         human=lambda: console.print(f"[green]removed[/green] {escape(target)} from the equation model · {_sha(sha)}"),
         commit_sha=sha)


@app.command("show")
@handle_cli_errors
def show() -> None:
    """Print every quantity: its role, value or formula, units, valid range and source."""
    from latris.operations import equation_model as eq

    data = eq.snapshot()
    rows, problems = data["quantities"], data["problems"]

    def human() -> None:
        t = Table(show_header=True, header_style="bold")
        for c in ("Quantity", "Role", "Value", "Formula / valid range", "Source"):
            t.add_column(c)
        for r in rows:
            bounded = r["valid_min"] is not None or r["valid_max"] is not None
            span = f"{_g(r['valid_min'])} – {_g(r['valid_max'])}" if bounded else ""
            t.add_row(escape(r["quantity"]), r["role"], _v(r["value"], r["units"]),
                      escape(r["formula"] or span), escape(r["source"] or "—"))
        console.print(t)
        for p in problems:
            console.print(f"[yellow]![/yellow] {escape(p['label'])}: {escape(p['message'])}")

    emit(data, human=human)


@app.command("check")
@handle_cli_errors
def check() -> None:
    """Check every quantity has a value or formula, the formulas resolve, and the units agree. Exits 1 until so."""
    from latris.operations.readiness import assess_readiness

    r = assess_readiness("equation_model")
    gaps = [{"element": g.element_label, "gap_type": g.gap_type, "message": g.message} for g in r.gaps]

    def human() -> None:
        if r.can_switch:
            console.print("[green]The equation model is complete and its units agree.[/green]")
        for g in gaps:
            console.print(f"  - {escape(g['element'])}: {escape(g['message'])}")

    emit({"ready": r.can_switch, "gaps": gaps}, human=human)
    if not r.can_switch:
        raise typer.Exit(1)


@app.command("scenario")
@handle_cli_errors
def scenario(
    name: str = typer.Argument(..., help="The scenario's name, e.g. 'Design flood'."),
    set_: list[str] = typer.Option([], "--set", "-s", help="'Quantity=value [units]' (repeatable)."),
    description: str = typer.Option("", "--description", "-d", help="What the scenario represents."),
    reason: str = typer.Option("", "--reason", help="Why these values."),
    source: str = typer.Option(None, "--source", help="Source ID the values come from."),
    origin: str = typer.Option("human-direct", "--origin", help=ORIGIN_HELP),
    verified: bool = typer.Option(False, "--verified", help="A person has checked it."),
    remove_: bool = typer.Option(False, "--remove", help="Delete the scenario instead."),
) -> None:
    """Save a named set of input values to evaluate (or, with --remove, delete it)."""
    from latris.operations import equation_model as eq

    if remove_:
        sha = eq.remove_scenario(name)
        emit({"removed": name}, human=lambda: console.print(f"[green]removed[/green] scenario {escape(name)} · "
                                                            f"{_sha(sha)}"), commit_sha=sha)
        return
    saved, sha = eq.set_scenario(name, set_, description=description, reason=reason, source_id=source,
                                 origin=origin, verification=verification(verified))  # type: ignore[arg-type]
    emit(saved, human=lambda: console.print(f"[green]scenario[/green] {escape(saved.name)}: "
                                            f"{escape(', '.join(set_))} · {_sha(sha)}"), commit_sha=sha)


@app.command("scenarios")
@handle_cli_errors
def scenarios() -> None:
    """List the saved scenarios and what each changes."""
    from latris.operations import equation_model as eq

    data = eq.snapshot()["scenarios"]

    def human() -> None:
        if not data:
            console.print("No scenarios saved (`latris eq scenario <name> --set 'Quantity=value units'`).")
        for s in data:
            changes = ", ".join(f"{escape(c['quantity'])} = {_v(c['value'], c['units'])}" for c in s["changes"])
            console.print(f"[bold]{escape(s['name'])}[/bold]: {changes}"
                          + (f" — {escape(s['description'])}" if s["description"] else ""))

    emit(data, human=human)


@app.command("uncertainty")
@handle_cli_errors
def uncertainty(
    target: str = typer.Argument(..., help="An input or a parameter."),
    distribution: str = typer.Argument("triangular", help="triangular (default) | uniform | normal | lognormal | "
                                                          "beta | gamma"),
    min_: float | None = typer.Option(None, "--min"),
    mode: float | None = typer.Option(None, "--mode"),
    max_: float | None = typer.Option(None, "--max"),
    mean: float | None = typer.Option(None, "--mean"),
    sd: float | None = typer.Option(None, "--sd"),
    alpha: float | None = typer.Option(None, "--alpha"),
    beta: float | None = typer.Option(None, "--beta"),
    shape: float | None = typer.Option(None, "--shape"),
    scale: float | None = typer.Option(None, "--scale"),
    reason: str = typer.Option("", "--reason", help="Why this range (e.g. 'the spread across the cited studies')."),
    source: str | None = typer.Option(None, "--source", help="Source ID backing the range."),
    origin: str = typer.Option("human-direct", "--origin", help=ORIGIN_HELP),
    verified: bool = typer.Option(False, "--verified", help="Mark the range as checked by a person."),
    clear: bool = typer.Option(False, "--clear", help="Remove the range instead."),
) -> None:
    """Say how uncertain an input's or parameter's value is, in its own units, for `monte-carlo`.

    The range must include the current value.
    """
    from latris.operations import equation_model as eq

    if clear:
        sha = eq.clear_uncertainty(target)
        emit({"cleared": target}, human=lambda: console.print(f"[green]cleared[/green] {escape(target)} · {_sha(sha)}"),
             commit_sha=sha)
        return
    raw = {"min": min_, "mode": mode, "max": max_, "mean": mean, "sd": sd, "alpha": alpha, "beta": beta,
           "shape": shape, "scale": scale}
    entry, sha = eq.set_uncertainty(target, distribution, {k: v for k, v in raw.items() if v is not None},
                                    reason=reason, source_id=source, origin=origin,  # type: ignore[arg-type]
                                    verification=verification(verified))
    pretty = ", ".join(f"{k}={v:.4g}" for k, v in entry.params.items())
    emit(entry.model_dump(mode="json"),
         human=lambda: console.print(f"[green]uncertainty[/green] {escape(target)} ~ {entry.distribution}({pretty}) · "
                                     f"{_sha(sha)}"), commit_sha=sha)


def _warn_outside(arms: list[dict]) -> None:
    for a in arms:
        for o in a["outside"]:
            console.print(f"[yellow]![/yellow] {escape(o['quantity'])} = {_v(o['value'], o['units'])} under "
                          f"{escape(a['name'])} is outside its valid range ({_g(o['valid_min'])} – "
                          f"{_g(o['valid_max'])}): an extrapolation.")


@app.command("evaluate")
@handle_cli_errors
def evaluate(
    scenario_: list[str] = typer.Option([], "--scenario", help="A saved scenario to include (repeatable; default: "
                                                               "all of them)."),
    set_: list[str] = typer.Option([], "--set", "-s", help="Unsaved values to try: 'Quantity=value [units]'."),
    no_record: bool = typer.Option(False, "--no-record", help="Show the result without recording it for reports."),
) -> None:
    """Work the model out: every quantity at the reference values and under each scenario."""
    from latris.operations import equation_model as eq

    payload = eq.evaluate(scenarios=scenario_ or None, set=set_ or None)
    sha = None
    if not no_record and not payload["problems"]:
        sha, payload["run_id"] = eq.record(payload)

    def human() -> None:
        for p in payload["problems"]:
            console.print(f"[yellow]![/yellow] {escape(p['label'])}: {escape(p['message'])}")
        console.print(escape(eq.describe(payload)) + ".\n")
        if payload["problems"]:
            return
        arms = payload["arms"]
        t = Table(show_header=True, header_style="bold")
        t.add_column("Quantity")
        t.add_column("Role")
        for a in arms:
            t.add_column(a["name"], justify="right")
        for q in payload["quantities"]:
            t.add_row(escape(q["quantity"]), q["role"], *(_v(a["values"][q["quantity"]], q["units"]) for a in arms))
        console.print(t)
        _warn_outside(arms)
        if sha:
            console.print(f"\nrecorded · {_sha(sha)}")

    emit(payload, human=human, commit_sha=sha)


@app.command("sweep")
@handle_cli_errors
def sweep(
    input_: str = typer.Option(None, "--input", "-i", help="The input or parameter to vary (default: the first)."),
    target: str = typer.Option(None, "--target", "-t", help="The output to follow (default: the first output)."),
    low: float = typer.Option(None, "--low", help="Where the sweep starts (default: the bottom of the valid range)."),
    high: float = typer.Option(None, "--high", help="Where it ends (default: the top of the valid range)."),
    steps: int = typer.Option(25, "--steps", help="Number of points."),
    no_record: bool = typer.Option(False, "--no-record", help="Show the result without recording it for reports."),
) -> None:
    """How does an output respond as one input moves across a range, everything else held?"""
    from latris.operations import equation_model as eq

    payload = eq.sweep(input=input_, target=target, low=low, high=high, steps=steps)
    sha = None
    if not no_record:
        sha, payload["run_id"] = eq.record_sweep(payload)

    def human() -> None:
        console.print(escape(eq.describe_sweep(payload)) + ".\n")
        t = Table(show_header=True, header_style="bold")
        t.add_column(f"{payload['input']} ({_u(payload['input_units']) or '–'})", justify="right")
        t.add_column(f"{payload['target']} ({_u(payload['target_units']) or '–'})", justify="right")
        xs, ys = payload["x"], payload["series"][payload["target"]]
        step = max(1, (len(xs) - 1) // 9)
        for i in sorted(set(range(0, len(xs), step)) | {len(xs) - 1}):
            t.add_row(_g(xs[i]), _g(ys[i]))
        console.print(t)
        if sha:
            console.print(f"\nrecorded · {_sha(sha)}")

    emit(payload, human=human, commit_sha=sha)


@app.command("monte-carlo")
@handle_cli_errors
def monte_carlo(
    runs: int = typer.Option(2000, "--runs", "-n", help="Number of sampled runs."),
    seed: int = typer.Option(1234, "--seed", help="The same seed gives the same runs."),
    sampling: str = typer.Option("lhs", "--sampling", help="lhs (Latin hypercube) | random."),
    target: str = typer.Option(None, "--target", "-t", help="The output to headline (default: the first output)."),
    no_record: bool = typer.Option(False, "--no-record", help="Show the result without recording it for reports."),
) -> None:
    """How sure is the result? Sample every input and parameter that has a range and recompute.

    Gives each output's 5th–95th percentile, median and mean beside its
    value at the reference inputs, and ranks the uncertain values by how
    strongly they drive the headline output. Values without a range are
    held fixed and listed.
    """
    from latris.operations import equation_model as eq

    payload = eq.monte_carlo(runs=runs, seed=seed, sampling=sampling, target=target)
    sha = None
    if not no_record:
        sha, payload["run_id"] = eq.record_monte_carlo(payload)

    def human() -> None:
        console.print(escape(eq.describe_monte_carlo(payload)) + ".\n")
        t = Table(show_header=True, header_style="bold")
        for c in ("Output", "Reference", "Mean", "5th pct", "Median", "95th pct"):
            t.add_column(c, justify="left" if c == "Output" else "right")
        for o in payload["outputs"]:
            t.add_row(f"{escape(o['output'])} ({_u(o['units']) or '–'})", _g(o["point"]), _g(o["mean"]), _g(o["p5"]),
                      _g(o["p50"]), _g(o["p95"]))
        console.print(t)
        d = Table(show_header=True, header_style="bold", title=f"What drives {payload['primary']}")
        for c in ("Value", "Range (5th–95th)", "Rank correlation"):
            d.add_column(c)
        for r in payload["drivers"]:
            d.add_row(escape(r["input"]), f"{_g(r['p5'])} – {_v(r['p95'], r['units'])}",
                      "—" if r["spearman"] is None else f"{r['spearman']:+.2f}")
        console.print(d)
        if payload["fixed"]:
            console.print(f"[dim]Held fixed (no range): {escape(', '.join(payload['fixed']))}[/dim]")
        if sha:
            console.print(f"\nrecorded · {_sha(sha)}")

    emit(payload, human=human, commit_sha=sha)
