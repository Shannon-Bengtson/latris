"""System Dynamics CLI — classify, parameterise, check, simulate."""

from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from latris.cli._errors import handle_cli_errors
from latris.cli._output import emit, json_mode

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
    if json_mode():
        emit({"target_id": target_id, "role": role}, human=lambda: None, commit_sha=sha)
        return
    console.print(f"[green]set[/green] {_labels().get(target_id, target_id[:15])} → {role} · {_sha(sha)}")


@app.command("roles")
@handle_cli_errors
def roles() -> None:
    """List SD classifications."""
    from latris.operations import sd as sd_ops

    entries = sd_ops.get_roles().entries
    if json_mode():
        labels = _labels()
        emit([{"node": labels.get(e.target_id, e.target_id), "role": e.value} for e in entries], human=lambda: None)
        return
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
    if json_mode():
        emit(entry, human=lambda: None, commit_sha=sha)
        return
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
    if json_mode():
        labels = _labels()
        emit([{"variable": labels.get(e.target_id, e.target_id), "equation": e.expression, "units": e.units,
               "origin": e.origin} for e in entries], human=lambda: None)
        return
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
    if json_mode():
        emit(entry, human=lambda: None, commit_sha=sha)
        return
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
    if json_mode():
        labels = _labels()
        emit([{"stock": labels.get(e.target_id, e.target_id), "initial_value": e.initial_value, "units": e.units,
               "non_negative": e.non_negative, "origin": e.origin} for e in entries], human=lambda: None)
        return
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
    if json_mode():
        emit(entry, human=lambda: None, commit_sha=sha)
        return
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
    if json_mode():
        labels = _labels()
        emit([{"constant": labels.get(e.target_id, e.target_id), "value": e.value, "units": e.units,
               "origin": e.origin} for e in entries], human=lambda: None)
        return
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
    if json_mode():
        emit(entry, human=lambda: None, commit_sha=sha)
        return
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
    if json_mode():
        labels = _labels()
        emit([{"variable": labels.get(e.target_id, e.target_id), "points": [[p.x, p.y] for p in e.points],
               "x_units": e.x_units, "y_units": e.y_units, "extrapolate": e.extrapolate} for e in entries],
             human=lambda: None)
        return
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
    if json_mode():
        emit({"ready": not gaps, "gaps": [
            {"element": g.element_label or g.element_id, "gap": g.gap_type, "detail": g.message} for g in gaps
        ]}, human=lambda: None)
        return
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


def _settings_options(initial_time, final_time, dt, saveper, method, time_units) -> dict:
    return {"initial_time": initial_time, "final_time": final_time, "dt": dt, "saveper": saveper,
            "method": method, "time_units": time_units}


def _change(c: dict | None) -> str:
    if not c:
        return ""
    pct = f" ({c['end_pct']:+.3g}%)" if c.get("end_pct") is not None else ""
    return f"{c['end']:+.6g}{pct}"


@app.command("simulate")
@handle_cli_errors
def simulate(
    scenario: list[str] | None = typer.Option(
        None, "--scenario", "-s", help="Also run a saved scenario and compare it with the baseline (repeatable)."),
    assignments: list[str] | None = typer.Option(
        None, "--set", help="Ad-hoc what-if, not saved: 'Variable=value [units]' (repeatable)."),
    initial_time: float | None = typer.Option(None, "--initial-time", help="Start time (default 0)."),
    final_time: float | None = typer.Option(None, "--final-time", help="End time (default 100)."),
    dt: float | None = typer.Option(None, "--dt", help="Time step (default 0.25)."),
    saveper: float | None = typer.Option(None, "--saveper", help="Reporting interval (default dt)."),
    method: str | None = typer.Option(None, "--method", help="euler | rk2 | rk4 (default) | adaptive."),
    time_units: str | None = typer.Option(None, "--time-units", help="Time unit (default years)."),
    record: bool = typer.Option(True, "--record/--no-record", help="Save the result for reports + log a run."),
    json_output: bool = typer.Option(False, "--json", help="Emit the full time series as JSON (for agents/scripts)."),
) -> None:
    """Run the model (baseline, plus any scenarios) and summarise each variable's trajectory.

    With --scenario or --set, every run is compared with the baseline: the end
    value of each variable and its change. Recorded results appear in reports.
    """
    from latris.operations import sd as sd_ops

    payload, runs = sd_ops.simulate_scenarios(
        scenario or [], assignments or [],
        **_settings_options(initial_time, final_time, dt, saveper, method, time_units),
    )
    recorded = sd_ops.record_comparison(payload, runs) if record else None
    base = runs[0].result
    success = all(r.result.success for r in runs)

    if json_mode() and not json_output:
        # One compact object for agents: each variable's trajectory summarised,
        # with the series thinned to at most ~50 points.
        step = max(1, len(base.times) // 50)

        def variables(res, change=None):
            return [
                {"variable": res.labels[v], "role": res.roles[v], "units": res.units[v],
                 "start": vals[0], "end": vals[-1], "min": min(vals), "max": max(vals),
                 **({"change_vs_baseline": change[v]} if change and v in change else {}),
                 "series": vals[::step]}
                for v, vals in res.series.items() if vals
            ]

        scenarios = []
        for r, sc in zip(runs[1:], payload["scenarios"][1:], strict=True):
            scenarios.append({
                "scenario": r.name, "success": r.result.success, "message": r.result.message,
                "changes": [f"{o['label']}: {o['baseline']} → {o['value']:g} {o['units']}" for o in sc["overrides"]],
                "variables": variables(r.result, sc.get("change_vs_baseline")),
                "warnings": r.result.warnings,
            })
        emit({
            "success": success, "message": base.message, "algorithm": base.algorithm,
            "time_units": base.time_units, "times": base.times[::step],
            "variables": variables(base), "scenarios": scenarios,
            "warnings": base.warnings, "run_id": recorded[1] if recorded else None,
        }, human=lambda: None, commit_sha=recorded[0] if recorded else None)
    elif json_output:
        # The baseline's full, unthinned series stay at the top level (as before scenarios existed).
        out = {**payload, "success": success, "message": base.message, "series": base.series,
               "warnings": base.warnings}
        if recorded:
            out["commit_sha"], out["run_id"] = recorded
        typer.echo(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        t = base.times
        span = f"{t[0]:g}–{t[-1]:g} {base.time_units}" if t else "(no output)"
        console.print(f"[bold]Simulation[/bold] {span} · {base.algorithm} · {len(t)} report point(s)\n")
        table = Table(show_header=True, header_style="bold")
        for col, justify in (("Variable", "left"), ("Role", "left"), ("Start", "right"), ("End", "right"),
                             ("Min", "right"), ("Max", "right"), ("Units", "left")):
            table.add_column(col, justify=justify)  # type: ignore[arg-type]
        order = sorted(base.series, key=lambda i: (_ROLE_ORDER.get(base.roles[i], 9), base.labels[i]))
        for vid in order:
            vals = base.series[vid]
            if not vals:
                continue
            table.add_row(base.labels[vid], base.roles[vid], f"{vals[0]:.6g}", f"{vals[-1]:.6g}",
                          f"{min(vals):.6g}", f"{max(vals):.6g}", base.units[vid])
        console.print(table)
        for r, sc in zip(runs[1:], payload["scenarios"][1:], strict=True):
            title = f"\n[bold]Scenario {escape(r.name)}[/bold]"
            console.print(title + (f" — {escape(sc['description'])}" if sc.get("description") else ""))
            for o in sc["overrides"]:
                console.print(f"  {escape(o['label'])}: {escape(o['baseline'])} → {o['value']:g} {escape(o['units'])}")
            ct = Table(show_header=True, header_style="bold")
            for col, justify in (("Variable", "left"), ("Baseline end", "right"), ("Scenario end", "right"),
                                 ("Change", "right"), ("Units", "left")):
                ct.add_column(col, justify=justify)  # type: ignore[arg-type]
            for vid in order:
                if not base.series[vid] or not r.result.series[vid]:
                    continue
                ct.add_row(base.labels[vid], f"{base.series[vid][-1]:.6g}", f"{r.result.series[vid][-1]:.6g}",
                           _change(sc.get("change_vs_baseline", {}).get(vid)), base.units[vid])
            console.print(ct)
        for r in runs:
            for w in r.result.warnings:
                console.print(f"[yellow]⚠ {escape(r.name)}: {escape(w)}[/yellow]")
            if not r.result.success:
                console.print(f"[red]{escape(r.name)} failed:[/red] {escape(r.result.message)}")
        if recorded:
            sha, run_id = recorded
            console.print(f"\n[green]recorded[/green] · run [cyan]{run_id[:18]}…[/cyan] · {_sha(sha)}")

    if not success:
        raise typer.Exit(code=1)


# ── scenarios ────────────────────────────────────────────────────────


def _changes(overrides, labels) -> list[dict]:
    return [{"variable": labels.get(o.target_id, o.target_id), "attribute": o.attribute,
             "value": o.value, "units": o.units} for o in overrides]


@app.command("set-scenario")
@handle_cli_errors
def set_scenario(
    name: str = typer.Argument(..., help="Scenario name, e.g. 'Congestion charge'."),
    assignments: list[str] = typer.Option(
        ..., "--set", help="'Variable=value [units]' for a constant or a stock's initial value (repeatable)."),
    description: str = typer.Option("", "--description", "-d", help="What the scenario represents."),
    reason: str = typer.Option("", "--reason", help="Why these values (assumption, policy, source)."),
    source: str | None = typer.Option(None, "--source", help="Source ID backing the values."),
    origin: str = typer.Option("human-direct", "--origin", help="Provenance origin."),
) -> None:
    """Save a named what-if: the model with some constants or initial values changed.

    Values are unit-checked: a delay declared in years can be set as '6 month',
    but not as '6 person'. Run it with `sd simulate --scenario NAME`.
    """
    from latris.operations import sd_scenarios

    scenario, sha = sd_scenarios.set_scenario(
        name, assignments, description=description, reason=reason, source_id=source,
        origin=origin,  # type: ignore[arg-type]
    )
    labels = _labels()
    if json_mode():
        emit({"name": scenario.name, "description": scenario.description, "origin": scenario.origin,
              "changes": _changes(scenario.overrides, labels)}, human=lambda: None, commit_sha=sha)
        return
    changes = ", ".join(f"{labels.get(o.target_id, o.target_id)} = {o.value:g} {o.units}" for o in scenario.overrides)
    console.print(f"[green]scenario[/green] {escape(scenario.name)}: {escape(changes)} · {_sha(sha)}")


@app.command("scenarios")
@handle_cli_errors
def scenarios() -> None:
    """List saved scenarios and what each one changes."""
    from latris.operations import sd_scenarios

    items = sd_scenarios.list_scenarios()
    labels = _labels()
    if json_mode():
        emit([{"name": s.name, "description": s.description, "reason": s.reason, "origin": s.origin,
               "verification": s.verification, "source_id": s.source_id,
               "changes": _changes(s.overrides, labels)} for s in items], human=lambda: None)
        return
    if not items:
        console.print("No scenarios yet. Add one with `latris sd set-scenario NAME --set 'Variable=value'`.")
        return
    table = Table(show_header=True, header_style="bold")
    for col in ("Scenario", "Changes", "Description", "Origin"):
        table.add_column(col)
    for s in items:
        changes = "; ".join(f"{labels.get(o.target_id, o.target_id)} = {o.value:g} {o.units}" for o in s.overrides)
        table.add_row(escape(s.name), escape(changes), escape(s.description), s.origin)
    console.print(table)


@app.command("remove-scenario")
@handle_cli_errors
def remove_scenario(name: str = typer.Argument(..., help="Scenario name.")) -> None:
    """Delete a saved scenario."""
    from latris.operations import sd_scenarios

    sha = sd_scenarios.remove_scenario(name)
    if json_mode():
        emit({"removed": name}, human=lambda: None, commit_sha=sha)
        return
    console.print(f"[green]removed[/green] scenario {escape(name)} · {_sha(sha)}")
