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
    notes = sd_ops.notes() if not gaps else []
    if json_mode():
        emit({"ready": not gaps, "gaps": [
            {"element": g.element_label or g.element_id, "gap": g.gap_type, "detail": g.message} for g in gaps
        ], "notes": notes}, human=lambda: None)
        return
    if not gaps:
        console.print("[green]✓[/green] SD model is complete, dimensionally consistent, and ready to simulate.")
        for n in notes:
            console.print(f"[yellow]⚠ {escape(n)}[/yellow]")
        return
    table = Table(show_header=True, header_style="bold")
    table.add_column("Element")
    table.add_column("Gap")
    table.add_column("Detail")
    for g in gaps:
        table.add_row(escape(g.element_label or g.element_id[:12]), g.gap_type, escape(g.message))
    console.print(table)
    raise typer.Exit(code=1)


@app.command("set-settings")
@handle_cli_errors
def set_settings(
    time_units: str | None = typer.Option(None, "--time-units", help="The clock: month, year, week, day, ..."),
    initial_time: float | None = typer.Option(None, "--initial-time", help="Start time."),
    final_time: float | None = typer.Option(None, "--final-time", help="End time, in the clock's units."),
    dt: float | None = typer.Option(None, "--dt", help="Time step."),
    saveper: float | None = typer.Option(None, "--saveper", help="Reporting interval."),
    method: str | None = typer.Option(None, "--method", help="euler | rk2 | rk4 | adaptive."),
) -> None:
    """Store the model's clock and run settings, so every run (and anyone opening it) uses them.

    Example for a monthly model over three years: sd set-settings --time-units month --final-time 36
    Options given to a run still override these for that run.
    """
    from latris.operations import sd as sd_ops

    stored, sha = sd_ops.set_settings(time_units=time_units, initial_time=initial_time, final_time=final_time,
                                      dt=dt, saveper=saveper, method=method)
    shown = {k: v for k, v in stored.model_dump(exclude_none=True).items() if k != "outcome"}
    if json_mode():
        emit(shown, human=lambda: None, commit_sha=sha)
        return
    console.print(f"[green]settings[/green] {escape(', '.join(f'{k}={v}' for k, v in shown.items()))} · {_sha(sha)}")


@app.command("settings")
@handle_cli_errors
def settings() -> None:
    """Show the model's stored clock and run settings (and the defaults used for anything unset)."""
    from latris.operations import sd as sd_ops

    stored = sd_ops.get_settings()
    effective = sd_ops.build_settings(base=stored)
    out = {"stored": stored.model_dump(exclude_none=True), "effective": effective.model_dump(
        include={"time_units", "initial_time", "final_time", "dt", "saveper", "integration_method"})}
    if json_mode():
        emit(out, human=lambda: None)
        return
    e = out["effective"]
    console.print(f"Clock: {e['initial_time']:g}–{e['final_time']:g} {e['time_units']}, dt {e['dt']:g}, "
                  f"{e['integration_method']}" + ("" if stored.time_units else " [dim](time units: the default)[/dim]"))


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


# ── uncertainty ──────────────────────────────────────────────────────


def _run_settings(final_time, dt, saveper, method) -> dict:
    return {k: v for k, v in {"final_time": final_time, "dt": dt, "saveper": saveper, "method": method}.items()
            if v is not None}


@app.command("set-uncertainty")
@handle_cli_errors
def set_uncertainty(
    target: str = typer.Argument(..., help="A constant or stock (ID, prefix or label)."),
    distribution: str = typer.Argument(..., help="uniform | triangular | normal | lognormal | beta | gamma"),
    min_: float | None = typer.Option(None, "--min", help="Lower bound (uniform, triangular; truncates others)."),
    mode: float | None = typer.Option(None, "--mode", help="Most likely value (triangular)."),
    max_: float | None = typer.Option(None, "--max", help="Upper bound (uniform, triangular; truncates others)."),
    mean: float | None = typer.Option(None, "--mean", help="Mean (normal, lognormal)."),
    sd: float | None = typer.Option(None, "--sd", help="Standard deviation (normal, lognormal)."),
    alpha: float | None = typer.Option(None, "--alpha", help="Beta shape α."),
    beta: float | None = typer.Option(None, "--beta", help="Beta shape β."),
    shape: float | None = typer.Option(None, "--shape", help="Gamma shape."),
    scale: float | None = typer.Option(None, "--scale", help="Gamma scale."),
    reason: str = typer.Option("", "--reason", help="Why this range (e.g. 'inventory reports 90–140')."),
    source: str | None = typer.Option(None, "--source", help="Source ID backing the range."),
    origin: str = typer.Option("human-direct", "--origin", help="Provenance origin."),
) -> None:
    """Say how uncertain a constant or initial value is, as a distribution in its own units.

    Monte Carlo samples from it; `sd sensitivity` swings it across its 5th–95th
    percentile. Example: sd set-uncertainty "Emission Rate" triangular --min 90 --mode 120 --max 140
    """
    from latris.operations import uncertainty

    raw = {"min": min_, "mode": mode, "max": max_, "mean": mean, "sd": sd, "alpha": alpha, "beta": beta,
           "shape": shape, "scale": scale}
    params = {k: v for k, v in raw.items() if v is not None}
    entry, sha = uncertainty.set_uncertainty(
        target, distribution, params, reason=reason, source_id=source, origin=origin,  # type: ignore[arg-type]
    )
    label = _labels().get(entry.target_id, entry.target_id)
    if json_mode():
        emit({"variable": label, "distribution": entry.distribution, "params": entry.params,
              "cell": entry.parameter_cell_id, "origin": entry.origin}, human=lambda: None, commit_sha=sha)
        return
    pretty = ", ".join(f"{k}={v:g}" for k, v in entry.params.items())
    console.print(f"[green]uncertainty[/green] {escape(label)} ~ {entry.distribution}({pretty}) · {_sha(sha)}")


@app.command("uncertainty")
@handle_cli_errors
def list_uncertainty() -> None:
    """List the uncertainty ranges on constants and initial values."""
    from latris.operations import uncertainty

    entries = uncertainty.list_uncertainty()
    labels = _labels()
    if json_mode():
        emit([{"variable": labels.get(e.target_id, e.target_id), "distribution": e.distribution, "params": e.params,
               "cell": e.parameter_cell_id, "reason": e.reason, "origin": e.origin, "verification": e.verification,
               "source_id": e.source_id} for e in entries], human=lambda: None)
        return
    if not entries:
        console.print("No uncertainty ranges yet. Add one with `latris sd set-uncertainty`.")
        return
    table = Table(show_header=True, header_style="bold")
    for col in ("Variable", "Distribution", "Origin", "Reason"):
        table.add_column(col)
    for e in entries:
        pretty = ", ".join(f"{k}={v:g}" for k, v in e.params.items())
        table.add_row(escape(labels.get(e.target_id, e.target_id)), f"{e.distribution}({pretty})", e.origin,
                      escape(e.reason))
    console.print(table)


@app.command("clear-uncertainty")
@handle_cli_errors
def clear_uncertainty(target: str = typer.Argument(..., help="A constant or stock (ID, prefix or label).")) -> None:
    """Remove a value's uncertainty range."""
    from latris.operations import uncertainty

    sha = uncertainty.clear_uncertainty(target)
    if json_mode():
        emit({"cleared": target}, human=lambda: None, commit_sha=sha)
        return
    console.print(f"[green]cleared[/green] uncertainty on {escape(target)} · {_sha(sha)}")


@app.command("monte-carlo")
@handle_cli_errors
def monte_carlo(
    runs: int = typer.Option(200, "--runs", "-n", help="Number of sampled runs (2–1000)."),
    seed: int = typer.Option(1234, "--seed", help="Random seed; the same seed gives the same runs."),
    sampling: str = typer.Option("lhs", "--sampling", help="lhs (Latin hypercube) | random."),
    variable: list[str] | None = typer.Option(None, "--var", "-v", help="Variable to summarise (default: stocks)."),
    scenario: str | None = typer.Option(None, "--scenario", "-s", help="Use a saved scenario, not the baseline."),
    final_time: float | None = typer.Option(None, "--final-time", help="End time (default 100)."),
    dt: float | None = typer.Option(None, "--dt", help="Time step (default 0.25)."),
    saveper: float | None = typer.Option(None, "--saveper", help="Reporting interval (default dt)."),
    method: str | None = typer.Option(None, "--method", help="euler | rk2 | rk4 (default) | adaptive."),
    max_seconds: float = typer.Option(60.0, "--max-seconds", help="Stop early if the runs would take longer."),
    record: bool = typer.Option(True, "--record/--no-record", help="Save the result for reports + log a run."),
) -> None:
    """Sample every value that has an uncertainty range and show the spread of outcomes.

    Each chosen variable gets percentile bands over time (50/75/95/100% of runs),
    and the uncertain values are ranked by how strongly they drive its end value.
    """
    from latris.operations import sd as sd_ops
    from latris.operations.sd_montecarlo import describe_end

    payload = sd_ops.run_monte_carlo(
        runs=runs, seed=seed, sampling=sampling, variables=variable, scenario=scenario, max_seconds=max_seconds,
        settings=_run_settings(final_time, dt, saveper, method),
    )
    recorded = sd_ops.record_monte_carlo(payload) if record else None
    if json_mode():
        emit({
            "runs": payload["runs"], "succeeded": payload["succeeded"], "failed": payload["failed"],
            "seed": payload["seed"], "sampling": payload["sampling"], "scenario": payload["scenario"],
            "time_units": payload["time_units"],
            "outcomes": [{
                "variable": payload["labels"][v], "units": payload["units"][v],
                "end": payload["end"][v], "summary": describe_end(payload, v),
                "drivers": [{"parameter": r["label"], "rank_correlation": r["rho"]} for r in payload["influence"][v]],
            } for v in payload["variables"]],
            "parameters": [{"parameter": p["label"], "distribution": p["distribution"], "params": p["params"],
                            "units": p["units"], "origin": p["origin"], "verification": p["verification"]}
                           for p in payload["parameters"]],
            "run_id": recorded[1] if recorded else None,
        }, human=lambda: None, commit_sha=recorded[0] if recorded else None)
        return
    on = f" · scenario {escape(payload['scenario'])}" if payload["scenario"] else ""
    console.print(f"[bold]Monte Carlo[/bold] {payload['succeeded']}/{payload['runs']} runs · {payload['sampling']} · "
                  f"seed {payload['seed']}{on}")
    for p in payload["parameters"]:
        pretty = ", ".join(f"{k}={v:g}" for k, v in p["params"].items())
        flag = "" if p["verification"] == "human-verified" else f" [yellow]({p['origin']}, unverified)[/yellow]"
        console.print(f"  {escape(p['label'])} ~ {p['distribution']}({pretty}) {escape(p['units'])}{flag}")
    for p in payload["skipped_parameters"]:
        console.print(f"  [dim]{escape(p['label'])}: {p['reason']}[/dim]")
    for v in payload["variables"]:
        console.print(f"\n{escape(describe_end(payload, v))}")
        e = payload["end"][v]
        console.print(f"  50% of runs {e['p25']:.4g}–{e['p75']:.4g}; baseline {e['baseline']:.4g}")
        drivers = [r for r in payload["influence"][v] if r["rho"] is not None][:3]
        if drivers:
            console.print("  driven by: " + ", ".join(f"{escape(r['label'])} (ρ={r['rho']:+.2f})" for r in drivers))
    if payload["failed"]:
        console.print(f"[yellow]⚠ {payload['failed']} run(s) failed[/yellow]")
    if recorded:
        console.print(f"\n[green]recorded[/green] · run [cyan]{recorded[1][:18]}…[/cyan] · {_sha(recorded[0])}")


@app.command("sensitivity")
@handle_cli_errors
def sensitivity(
    variable: str = typer.Argument(..., help="The result to explain: a stock, flow or auxiliary."),
    metric: str = typer.Option("final", "--metric", "-m", help="final | peak | peak-time | min | mean | at:T"),
    pct: float = typer.Option(10.0, "--pct", help="± percentage for values without an uncertainty range."),
    scenario: str | None = typer.Option(None, "--scenario", "-s", help="Use a saved scenario, not the baseline."),
    final_time: float | None = typer.Option(None, "--final-time", help="End time (default 100)."),
    dt: float | None = typer.Option(None, "--dt", help="Time step (default 0.25)."),
    method: str | None = typer.Option(None, "--method", help="euler | rk2 | rk4 (default) | adaptive."),
    top: int = typer.Option(15, "--top", help="Show the N most influential values."),
    record: bool = typer.Option(True, "--record/--no-record", help="Save the result for reports + log a run."),
) -> None:
    """Rank every constant and initial value by how much it moves one result (a tornado).

    Each value is swung across its uncertainty range (5th–95th percentile), or
    ±10% if it has none. Values that aren't human-verified are flagged weak, so
    you can see when the answer hinges on a number nobody has checked.
    """
    from latris.operations import sd as sd_ops

    payload = sd_ops.run_sensitivity(
        variable, metric=metric, pct=pct, scenario=scenario,
        settings=_run_settings(final_time, dt, None, method),
    )
    recorded = sd_ops.record_sensitivity(payload) if record else None
    rows = payload["parameters"][:top]
    if json_mode():
        emit({
            "variable": payload["label"], "metric": payload["metric_label"], "units": payload["units"],
            "baseline": payload["baseline"], "scenario": payload["scenario"],
            "parameters": [{
                "parameter": r["label"], "range": [r["low"], r["high"]], "range_from": r["range_source"],
                "result_range": [r.get("result_low"), r.get("result_high")], "swing": r["swing"],
                "origin": r["origin"], "verification": r["verification"], "weak": r["weak"],
                **({"error": r["error"]} if "error" in r else {}),
            } for r in rows],
            "weakly_grounded": [r["label"] for r in rows if r["weak"] and r["swing"]],
            "run_id": recorded[1] if recorded else None,
        }, human=lambda: None, commit_sha=recorded[0] if recorded else None)
        return
    console.print(f"[bold]Sensitivity of {escape(payload['label'])}[/bold] — {payload['metric_label']}, "
                  f"baseline {payload['baseline']:.6g} {escape(payload['units'])}\n")
    table = Table(show_header=True, header_style="bold")
    for col, justify in (("Value", "left"), ("Range", "right"), ("From", "left"), ("Result range", "right"),
                         ("Swing", "right"), ("Grounding", "left")):
        table.add_column(col, justify=justify)  # type: ignore[arg-type]
    for r in rows:
        grounding = f"[yellow]{r['origin']}, {r['verification']}[/yellow]" if r["weak"] else r["verification"]
        result = "error" if "error" in r else f"{r['result_low']:.4g} – {r['result_high']:.4g}"
        swing = "" if r["swing"] is None else f"{r['swing']:.4g}"
        table.add_row(escape(r["label"]), f"{r['low']:.4g} – {r['high']:.4g} {escape(r['units'])}",
                      r["range_source"], result, swing, grounding)
    console.print(table)
    if recorded:
        console.print(f"\n[green]recorded[/green] · run [cyan]{recorded[1][:18]}…[/cyan] · {_sha(recorded[0])}")


# ── loop dominance ───────────────────────────────────────────────────


@app.command("loops")
@handle_cli_errors
def loops(
    scenario: str | None = typer.Option(None, "--scenario", "-s", help="Use a saved scenario, not the baseline."),
    start: float | None = typer.Option(None, "--from", help="Start of the window to analyse (default: run start)."),
    end: float | None = typer.Option(None, "--to", help="End of the window to analyse (default: run end)."),
    final_time: float | None = typer.Option(None, "--final-time", help="End time (default 100)."),
    dt: float | None = typer.Option(None, "--dt", help="Time step (default 0.25)."),
    method: str | None = typer.Option(None, "--method", help="euler | rk2 | rk4 (default) | adaptive."),
    record: bool = typer.Option(True, "--record/--no-record", help="Save the result for reports + log a run."),
) -> None:
    """Which feedback loop drives the behaviour, and when (Loops That Matter).

    Every loop through the stocks and equations is scored at each step; a loop
    (or the fewest loops) holding at least half the total score dominates.
    Loops built on unsourced or contested links are flagged.
    """
    from latris.operations import sd as sd_ops
    from latris.operations import sd_loops

    payload = sd_ops.run_loops(scenario=scenario, start=start, end=end,
                               settings=_run_settings(final_time, dt, None, method))
    recorded = sd_ops.record_loops(payload) if record else None
    if json_mode():
        emit({
            "summary": sd_loops.describe(payload), "time_units": payload["time_units"], "window": payload["window"],
            "scenario": payload["scenario"],
            "loops": [{"loop": lp["id"], "polarity": "reinforcing" if lp["polarity"] == "R" else "balancing",
                       "path": lp["members"], "average_share": lp["average_share"],
                       "polarity_changes": lp["polarity_changes"], "weak_links": lp["weak_links"]}
                      for lp in payload["loops"]],
            "dominance": [p for s in payload["sets"] for p in s["dominant_periods"]],
            "run_id": recorded[1] if recorded else None,
        }, human=lambda: None, commit_sha=recorded[0] if recorded else None)
        return
    if not payload["loops"]:
        console.print("This model has no feedback loops: every effect runs one way.")
        return
    lo, hi = payload["window"]
    on = f" · scenario {escape(payload['scenario'])}" if payload["scenario"] else ""
    console.print(f"[bold]Loop dominance[/bold] {lo:g}–{hi:g} {payload['time_units']}{on}\n")
    table = Table(show_header=True, header_style="bold")
    for col, justify in (("Loop", "left"), ("Path", "left"), ("Avg share", "right"), ("Weak links", "left")):
        table.add_column(col, justify=justify)  # type: ignore[arg-type]
    for lp in payload["loops"]:
        weak = "; ".join(f"{w['link']} ({w['why']})" for w in lp["weak_links"])
        path = " → ".join(lp["members"]) + f" → {lp['members'][0]}"
        table.add_row(lp["id"], escape(path), f"{lp['average_share'] * 100:.0f}%",
                      f"[yellow]{escape(weak)}[/yellow]" if weak else "")
    console.print(table)
    console.print(f"\n{escape(sd_loops.describe(payload))}")
    if recorded:
        console.print(f"\n[green]recorded[/green] · run [cyan]{recorded[1][:18]}…[/cyan] · {_sha(recorded[0])}")
