"""System Dynamics CLI — classify, parameterise, check, simulate."""

from __future__ import annotations

import json
from dataclasses import asdict

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from latris.cli._errors import handle_cli_errors

app = typer.Typer(help="System Dynamics (stock-and-flow) operations.", no_args_is_help=True)
console = Console()

_ROLE_ORDER = {"stock": 0, "flow": 1, "auxiliary": 2, "constant": 3, "source_sink": 4}


def _labels() -> dict[str, str]:
    from latris.operations import nodes as node_ops

    return {e.id: e.label for e in node_ops.list_nodes()}


def _sha(sha: str) -> str:
    return f"commit [cyan]{sha[:10]}[/cyan]"


@app.command("set-role")
@handle_cli_errors
def set_role(
    target: str = typer.Argument(..., help="Node ID, ID prefix, or label."),
    role: str = typer.Argument(..., help="stock | flow | auxiliary | constant | source_sink"),
) -> None:
    """Classify a node for System Dynamics.

    Stocks accumulate; flows fill or drain stocks (connect them with flow edges,
    stock → flow → stock); auxiliaries and constants feed equations; a
    source_sink is a cloud outside the model boundary.
    """
    from latris.operations import sd as sd_ops

    target_id, sha = sd_ops.set_role(target, role)
    console.print(f"[green]set[/green] {_labels().get(target_id, target_id[:15])} → {role} · {_sha(sha)}")


@app.command("roles")
@handle_cli_errors
def roles() -> None:
    """List SD classifications."""
    from latris.operations import sd as sd_ops

    entries = sd_ops.get_roles().entries
    if not entries:
        console.print("[dim](no SD roles assigned)[/dim]")
        return
    labels = _labels()
    table = Table(show_header=True, header_style="bold")
    table.add_column("Node")
    table.add_column("Role")
    for e in sorted(entries, key=lambda e: (_ROLE_ORDER.get(e.value, 9), labels.get(e.target_id, ""))):
        table.add_row(labels.get(e.target_id, e.target_id[:12]), e.value)
    console.print(table)


@app.command("set-equation")
@handle_cli_errors
def set_equation(
    target: str = typer.Argument(..., help="Flow or auxiliary: ID, ID prefix, or label."),
    expression: str = typer.Argument(..., help="e.g. 'water * drain_rate' (names are slugified labels)."),
    units: str = typer.Option(..., "--units", "-u", help="Result units, e.g. 'liter/year' or 'dimensionless'."),
    origin: str = typer.Option("human-direct", "--origin", help="Provenance origin."),
    source: str | None = typer.Option(None, "--source", help="Source ID."),
) -> None:
    """Set a flow's or auxiliary's equation.

    Reference other variables by slugified label ("Drain Rate" → drain_rate) and
    TIME for the current time. Functions: MIN, MAX, ABS, IF_THEN_ELSE, STEP,
    TABLE, EXP, LN, SQRT. Units are checked: a flow's units must be its stock's
    units per time unit.
    """
    from latris.operations import sd as sd_ops

    entry, sha = sd_ops.set_equation(target, expression, units, origin=origin, source_id=source)
    console.print(
        f"[green]set[/green] {_labels().get(entry.target_id, entry.target_id[:15])} = "
        f"{entry.expression} [{entry.units}] · {_sha(sha)}"
    )


@app.command("equations")
@handle_cli_errors
def equations() -> None:
    """List flow and auxiliary equations."""
    from latris.operations import sd as sd_ops
    from latris.operations.sd_inference import role_map

    entries = sd_ops.get_equations().entries
    if not entries:
        console.print("[dim](no equations defined)[/dim]")
        return
    labels, rmap = _labels(), role_map(sd_ops.get_roles())
    table = Table(show_header=True, header_style="bold")
    table.add_column("Variable")
    table.add_column("Role")
    table.add_column("Equation")
    table.add_column("Units")
    table.add_column("Origin")
    for e in entries:
        table.add_row(labels.get(e.target_id, e.target_id[:12]), rmap.get(e.target_id, "?"), e.expression, e.units,
                      e.origin)
    console.print(table)


@app.command("set-initial-value")
@handle_cli_errors
def set_initial_value(
    stock: str = typer.Argument(..., help="Stock: ID, ID prefix, or label."),
    value: float = typer.Argument(..., help="Value at the initial time."),
    units: str = typer.Option(..., "--units", "-u", help="Stock units, e.g. 'liter' or 'person'."),
    non_negative: bool = typer.Option(False, "--non-negative", help="Warn if a run drives this stock below zero."),
    origin: str = typer.Option("human-direct", "--origin", help="Provenance origin."),
    source: str | None = typer.Option(None, "--source", help="Source ID."),
) -> None:
    """Set a stock's initial value."""
    from latris.operations import sd as sd_ops

    entry, sha = sd_ops.set_initial_value(
        stock, value, units, non_negative=non_negative, origin=origin, source_id=source
    )
    console.print(
        f"[green]set[/green] {_labels().get(entry.target_id, entry.target_id[:15])}(0) = "
        f"{entry.initial_value:g} {entry.units} · {_sha(sha)}"
    )


@app.command("stocks")
@handle_cli_errors
def stocks() -> None:
    """List stock initial values."""
    from latris.operations import sd as sd_ops

    entries = sd_ops.get_stocks().entries
    if not entries:
        console.print("[dim](no initial values defined)[/dim]")
        return
    labels = _labels()
    table = Table(show_header=True, header_style="bold")
    table.add_column("Stock")
    table.add_column("Initial", justify="right")
    table.add_column("Units")
    table.add_column("Non-negative")
    table.add_column("Origin")
    for e in entries:
        table.add_row(labels.get(e.target_id, e.target_id[:12]), f"{e.initial_value:g}", e.units,
                      "✓" if e.non_negative else "", e.origin)
    console.print(table)


@app.command("set-constant")
@handle_cli_errors
def set_constant(
    target: str = typer.Argument(..., help="Constant: ID, ID prefix, or label."),
    value: float = typer.Argument(..., help="The constant's value."),
    units: str = typer.Option(..., "--units", "-u", help="Units, e.g. '1/year' or 'dimensionless'."),
    origin: str = typer.Option("human-direct", "--origin", help="Provenance origin."),
    source: str | None = typer.Option(None, "--source", help="Source ID."),
) -> None:
    """Set a constant's value."""
    from latris.operations import sd as sd_ops

    entry, sha = sd_ops.set_constant(target, value, units, origin=origin, source_id=source)
    console.print(
        f"[green]set[/green] {_labels().get(entry.target_id, entry.target_id[:15])} = "
        f"{entry.value:g} {entry.units} · {_sha(sha)}"
    )


@app.command("constants")
@handle_cli_errors
def constants() -> None:
    """List constants."""
    from latris.operations import sd as sd_ops

    entries = sd_ops.get_constants().entries
    if not entries:
        console.print("[dim](no constants defined)[/dim]")
        return
    labels = _labels()
    table = Table(show_header=True, header_style="bold")
    table.add_column("Constant")
    table.add_column("Value", justify="right")
    table.add_column("Units")
    table.add_column("Origin")
    for e in entries:
        table.add_row(labels.get(e.target_id, e.target_id[:12]), f"{e.value:g}", e.units, e.origin)
    console.print(table)


@app.command("set-table")
@handle_cli_errors
def set_table(
    target: str = typer.Argument(..., help="Flow or auxiliary that calls TABLE(): ID, ID prefix, or label."),
    point: list[str] = typer.Option(..., "--point", "-p", help="A point as 'x:y' (repeatable, ≥2, x increasing)."),
    x_units: str = typer.Option(..., "--x-units", help="Units of the TABLE() input."),
    y_units: str = typer.Option(..., "--y-units", help="Units of the TABLE() output."),
    extrapolate: str = typer.Option("clamp", "--extrapolate", help="Outside the points: 'clamp' or 'linear'."),
    origin: str = typer.Option("human-elicited", "--origin", help="Provenance origin."),
    source: str | None = typer.Option(None, "--source", help="Source ID."),
) -> None:
    """Set the piecewise-linear lookup a flow/auxiliary calls as TABLE(x).

    Example: `sd set-table "Effect of Crowding" -p 0:1 -p 0.5:0.8 -p 1:0 --x-units dimensionless
    --y-units dimensionless`
    """
    from latris.operations import sd as sd_ops

    if extrapolate not in ("clamp", "linear"):
        raise typer.BadParameter("--extrapolate must be 'clamp' or 'linear'")
    points: list[tuple[float, float]] = []
    for raw in point:
        if ":" not in raw:
            raise typer.BadParameter(f"--point must be 'x:y', got {raw!r}")
        x, y = raw.split(":", 1)
        try:
            points.append((float(x), float(y)))
        except ValueError as exc:
            raise typer.BadParameter(f"--point {raw!r} is not two numbers") from exc

    entry, sha = sd_ops.set_table(
        target, points, x_units, y_units, extrapolate=extrapolate, origin=origin, source_id=source
    )
    console.print(
        f"[green]set[/green] table on {_labels().get(entry.target_id, entry.target_id[:15])} "
        f"({len(entry.points)} point(s), {entry.x_units} → {entry.y_units}) · {_sha(sha)}"
    )


@app.command("tables")
@handle_cli_errors
def tables() -> None:
    """List table functions."""
    from latris.operations import sd as sd_ops

    entries = sd_ops.get_tables().entries
    if not entries:
        console.print("[dim](no tables defined)[/dim]")
        return
    labels = _labels()
    table = Table(show_header=True, header_style="bold")
    table.add_column("Variable")
    table.add_column("Points")
    table.add_column("x units")
    table.add_column("y units")
    table.add_column("Outside range")
    for e in entries:
        pts = ", ".join(f"({p.x:g}, {p.y:g})" for p in e.points)
        table.add_row(labels.get(e.target_id, e.target_id[:12]), pts, e.x_units, e.y_units, e.extrapolate)
    console.print(table)


@app.command("check")
@handle_cli_errors
def check() -> None:
    """Check SD readiness: classification, stock-flow plumbing, equations, values, tables, units."""
    from latris.operations import sd as sd_ops

    gaps = sd_ops.check()
    if not gaps:
        console.print("[green]✓[/green] SD model is complete, dimensionally consistent, and ready to simulate.")
        return
    table = Table(show_header=True, header_style="bold")
    table.add_column("Element")
    table.add_column("Gap")
    table.add_column("Detail")
    for g in gaps:
        table.add_row(escape(g.element_label or g.element_id[:12]), g.gap_type, escape(g.message))
    console.print(table)
    raise typer.Exit(code=1)


@app.command("simulate")
@handle_cli_errors
def simulate(
    initial_time: float | None = typer.Option(None, "--initial-time", help="Start time (default 0)."),
    final_time: float | None = typer.Option(None, "--final-time", help="End time (default 100)."),
    dt: float | None = typer.Option(None, "--dt", help="Time step (default 0.25)."),
    saveper: float | None = typer.Option(None, "--saveper", help="Reporting interval (default dt)."),
    method: str | None = typer.Option(None, "--method", help="euler | rk2 | rk4 (default) | adaptive."),
    time_units: str | None = typer.Option(None, "--time-units", help="Time unit (default years)."),
    record: bool = typer.Option(True, "--record/--no-record", help="Save the series + log an AnalysisRun."),
    json_output: bool = typer.Option(False, "--json", help="Emit the full time series as JSON (for agents/scripts)."),
) -> None:
    """Run one deterministic simulation and summarise each variable's trajectory."""
    from latris.operations import sd as sd_ops

    result = sd_ops.simulate(
        initial_time=initial_time, final_time=final_time, dt=dt, saveper=saveper,
        method=method, time_units=time_units,
    )
    recorded = sd_ops.record_simulation(result) if record else None

    if json_output:
        payload = asdict(result)
        if recorded:
            payload["commit_sha"], payload["run_id"] = recorded
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        t = result.times
        span = f"{t[0]:g}–{t[-1]:g} {result.time_units}" if t else "(no output)"
        console.print(f"[bold]Simulation[/bold] {span} · {result.algorithm} · {len(t)} report point(s)\n")
        table = Table(show_header=True, header_style="bold")
        for col, justify in (("Variable", "left"), ("Role", "left"), ("Start", "right"), ("End", "right"),
                             ("Min", "right"), ("Max", "right"), ("Units", "left")):
            table.add_column(col, justify=justify)  # type: ignore[arg-type]
        order = sorted(result.series, key=lambda i: (_ROLE_ORDER.get(result.roles[i], 9), result.labels[i]))
        for vid in order:
            vals = result.series[vid]
            if not vals:
                continue
            table.add_row(result.labels[vid], result.roles[vid], f"{vals[0]:.6g}", f"{vals[-1]:.6g}",
                          f"{min(vals):.6g}", f"{max(vals):.6g}", result.units[vid])
        console.print(table)
        for w in result.warnings:
            console.print(f"[yellow]⚠ {escape(w)}[/yellow]")
        if not result.success:
            console.print(f"[red]simulation failed:[/red] {escape(result.message)}")
        if recorded:
            sha, run_id = recorded
            console.print(f"\n[green]recorded[/green] · run [cyan]{run_id[:18]}…[/cyan] · {_sha(sha)}")

    if not result.success:
        raise typer.Exit(code=1)
