"""Analysis CLI commands — loops, propagation, d-separation, blanket, paths, adjustment sets, effect estimates."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from latris.cli._errors import handle_cli_errors
from latris.cli._output import emit, json_mode

app = typer.Typer(help="Graph analysis operations.", no_args_is_help=True)
console = Console()


def _labels() -> dict[str, str]:
    from latris.operations import nodes as node_ops

    return {e.id: e.label for e in node_ops.list_nodes()}


def _resolve(query: str) -> str:
    from latris.operations._resolve import resolve_target
    from latris.repo.project import require_project
    from latris.repo.yaml_io import load_model
    from latris.schema import Substrate

    paths = require_project(None)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    return resolve_target(query, substrate)


@app.command("loops")
@handle_cli_errors
def loops() -> None:
    """List all feedback loops with R/B classification."""
    from latris.operations.analysis import analyse_loops, loop_model_types

    classified = analyse_loops()
    if json_mode():
        labels = _labels()
        tags = loop_model_types(classified)
        emit([
            {"type": loop.classification, "length": len(loop.node_ids),
             "variables": [labels.get(n, n) for n in loop.node_ids], "ids": list(loop.node_ids),
             "model_types": tag}
            for loop, tag in zip(classified, tags, strict=True)
        ], human=lambda: None)
        return
    if not classified:
        console.print("[dim](no feedback loops found)[/dim]")
        return

    labels = _labels()
    table = Table(show_header=True, header_style="bold")
    table.add_column("#", style="dim")
    table.add_column("Type")
    table.add_column("Length")
    table.add_column("Variables")
    for i, loop in enumerate(classified, 1):
        type_str = {"R": "[green]R[/green]", "B": "[red]B[/red]", "unknown": "[dim]?[/dim]"}[loop.classification]
        node_labels = " → ".join(labels.get(nid, nid[:12]) for nid in loop.node_ids)
        table.add_row(str(i), type_str, str(len(loop.node_ids)), node_labels)
    console.print(table)
    console.print(f"\n{len(classified)} loop(s) found.")


@app.command("propagate")
@handle_cli_errors
def propagate(
    variable: str = typer.Argument(..., help="Variable to trace from (ID, label, or prefix)."),
) -> None:
    """Trace qualitative impact from a variable through the graph."""
    from latris.operations.analysis import analyse_propagation

    target_id = _resolve(variable)
    effects = analyse_propagation(target_id)
    if json_mode():
        labels = _labels()
        ambiguous = sum(e.effect == "ambiguous" for e in effects)
        emit({"from": labels.get(target_id, target_id), "effects": [
            {"variable": labels.get(e.entity_id, e.entity_id), "effect": e.effect,
             "positive_paths": e.paths_positive, "negative_paths": e.paths_negative,
             "direct_effect": e.direct_effect, "direct_steps": e.direct_steps}
            for e in effects
        ], **({"note": (
            f"{ambiguous} of {len(effects)} effects are ambiguous: routes of both signs reach them, usually "
            "because feedback loops carry the change back round. direct_effect is the sign along the shortest "
            "route — what happens first, before the loops respond; which wins later depends on strengths and "
            "delays, which only a quantified model (a simulation) can say."
        )} if ambiguous else {})}, human=lambda: None)
        return
    if not effects:
        console.print("[dim](no reachable nodes with known polarity)[/dim]")
        return

    labels = _labels()
    source_label = labels.get(target_id, target_id[:12])

    table = Table(
        title=f"Qualitative effects from [bold]{source_label}[/bold] ↑",
        show_header=True,
        header_style="bold",
    )
    table.add_column("Variable")
    table.add_column("Effect")
    table.add_column("+ paths")
    table.add_column("− paths")
    for eff in effects:
        effect_str = {
            "+": "[green]+[/green]",
            "-": "[red]−[/red]",
            "ambiguous": "[yellow]ambiguous[/yellow]",
        }[eff.effect]
        table.add_row(
            labels.get(eff.entity_id, eff.entity_id[:12]),
            effect_str,
            str(eff.paths_positive),
            str(eff.paths_negative),
        )
    console.print(table)


@app.command("d-sep")
@handle_cli_errors
def d_sep(
    x: str = typer.Argument(..., help="Source variable (ID, label, or prefix)."),
    y: str = typer.Argument(..., help="Target variable (ID, label, or prefix)."),
    given: list[str] | None = typer.Option(None, "--given", "-g", help="Conditioning variable(s)."),
) -> None:
    """Test d-separation between two variables given a conditioning set."""
    from latris.operations.analysis import analyse_d_separation

    x_id = _resolve(x)
    y_id = _resolve(y)
    z_ids = {_resolve(g) for g in given} if given else set()

    result = analyse_d_separation({x_id}, {y_id}, z_ids)

    labels = _labels()
    if json_mode():
        emit({"x": labels.get(x_id, x_id), "y": labels.get(y_id, y_id),
              "given": sorted(labels.get(z, z) for z in z_ids), "d_separated": bool(result)}, human=lambda: None)
        return
    x_label = labels.get(x_id, x_id[:12])
    y_label = labels.get(y_id, y_id[:12])
    z_labels = ", ".join(labels.get(zid, zid[:12]) for zid in z_ids) if z_ids else "(nothing)"

    if result:
        console.print(
            f"[green]d-separated[/green]: {x_label} ⊥ {y_label} | {{{z_labels}}}\n"
            f"These variables are conditionally independent given the conditioning set."
        )
    else:
        console.print(
            f"[red]NOT d-separated[/red]: {x_label} ⫫̸ {y_label} | {{{z_labels}}}\n"
            f"There is an active path between these variables given the conditioning set."
        )


@app.command("blanket")
@handle_cli_errors
def blanket(
    variable: str = typer.Argument(..., help="Variable to compute Markov blanket for."),
) -> None:
    """Show the Markov blanket of a variable."""
    from latris.operations.analysis import analyse_blanket

    target_id = _resolve(variable)
    mb = analyse_blanket(target_id)
    labels = _labels()
    target_label = labels.get(target_id, target_id[:12])
    if json_mode():
        emit({"variable": labels.get(target_id, target_id), "blanket": sorted(labels.get(n, n) for n in mb)},
             human=lambda: None)
        return

    if not mb:
        console.print(f"[dim]Markov blanket of {target_label} is empty (isolated node).[/dim]")
        return

    console.print(f"Markov blanket of [bold]{target_label}[/bold]:")
    for nid in sorted(mb):
        console.print(f"  • {labels.get(nid, nid[:12])}")


@app.command("paths")
@handle_cli_errors
def paths_cmd(
    from_var: str = typer.Argument(..., help="Source variable."),
    to_var: str = typer.Argument(..., help="Target variable."),
) -> None:
    """Enumerate all paths between two variables with classification."""
    from latris.operations.analysis import analyse_paths

    from_id = _resolve(from_var)
    to_id = _resolve(to_var)

    found = analyse_paths(from_id, to_id)
    labels = _labels()
    from_label = labels.get(from_id, from_id[:12])
    to_label = labels.get(to_id, to_id[:12])
    if json_mode():
        emit({"from": labels.get(from_id, from_id), "to": labels.get(to_id, to_id), "paths": [
            {"directed": p.is_directed,
             "nodes": [{"variable": labels.get(n.entity_id, n.entity_id), "role": n.classification} for n in p.nodes]}
            for p in found
        ]}, human=lambda: None)
        return

    if not found:
        console.print(f"[dim]No paths found between {from_label} and {to_label}.[/dim]")
        return

    console.print(f"Paths from [bold]{from_label}[/bold] to [bold]{to_label}[/bold]:\n")
    for i, path in enumerate(found, 1):
        directed_str = " [green](directed)[/green]" if path.is_directed else ""
        parts = []
        for pn in path.nodes:
            label = labels.get(pn.entity_id, pn.entity_id[:12])
            if pn.classification == "endpoint":
                parts.append(f"[bold]{label}[/bold]")
            elif pn.classification == "collider":
                parts.append(f"[red]{label}[/red] (collider)")
            elif pn.classification == "fork":
                parts.append(f"[yellow]{label}[/yellow] (fork)")
            else:
                parts.append(f"{label} (chain)")
        console.print(f"  {i}. {' → '.join(parts)}{directed_str}")

    console.print(f"\n{len(found)} path(s) found.")


@app.command("adjustment-sets")
@handle_cli_errors
def adjustment_sets_cmd(
    treatment: str = typer.Argument(..., help="Treatment/exposure variable."),
    outcome: str = typer.Argument(..., help="Outcome variable."),
) -> None:
    """Find valid adjustment sets via the backdoor criterion."""
    from latris.operations.analysis import analyse_adjustment_sets

    treatment_id = _resolve(treatment)
    outcome_id = _resolve(outcome)

    sets = analyse_adjustment_sets(treatment_id, outcome_id)
    labels = _labels()
    treatment_label = labels.get(treatment_id, treatment_id[:12])
    outcome_label = labels.get(outcome_id, outcome_id[:12])
    if json_mode():
        emit({"treatment": labels.get(treatment_id, treatment_id), "outcome": labels.get(outcome_id, outcome_id),
              "adjustment_sets": [sorted(labels.get(n, n) for n in st) for st in sets]}, human=lambda: None)
        return

    if not sets:
        console.print(f"[dim]No valid adjustment sets found for {treatment_label} → {outcome_label}.[/dim]")
        return

    console.print(f"Adjustment sets for [bold]{treatment_label}[/bold] → [bold]{outcome_label}[/bold]:\n")
    for i, s in enumerate(sets, 1):
        if not s:
            console.print(f"  {i}. (empty set — no adjustment needed)")
        else:
            members = ", ".join(sorted(labels.get(nid, nid[:12]) for nid in s))
            console.print(f"  {i}. {{{members}}}")


@app.command("estimate")
@handle_cli_errors
def estimate_cmd(
    treatment: str = typer.Argument(..., help="The factor whose effect you want (the treatment / exposure)."),
    outcome: str = typer.Argument(..., help="The factor it affects."),
    dataset: str = typer.Option(..., "--dataset", "-d", help="A registered dataset (`latris data` / the app)."),
    adjust: list[str] = typer.Option(None, "--adjust", help="Adjust for exactly these (checked against the DAG); "
                                                            "repeatable. Default: the smallest valid measured set."),
    column: list[str] = typer.Option(None, "--column", help="'Factor=column' where the names differ; repeatable."),
    estimator: str = typer.Option("auto", "--model", help="auto | linear | logistic (auto: logistic for a "
                                                         "two-valued outcome)."),
    no_adjust: bool = typer.Option(False, "--no-adjust", help="Adjust for nothing (checked: only valid when no "
                                                              "backdoor path is open)."),
    no_record: bool = typer.Option(False, "--no-record", help="Show the estimate without recording it."),
) -> None:
    """Estimate how big the effect of TREATMENT on OUTCOME is, from a dataset, adjusting as the DAG requires.

    Factors map to dataset columns by name (label or id, any case), or with
    --column. The adjustment set is the smallest valid backdoor set the
    dataset measures, unless you give one; if every valid set needs
    something the dataset lacks, it says what to measure instead of
    estimating something biased. Linear regression (robust standard errors)
    for a numeric outcome, logistic for a yes/no one; the unadjusted
    association is shown beside it. The estimate is causal only under the
    DAG's assumptions, which the output repeats.
    """
    from latris.operations import estimation

    columns = {}
    for c in column or []:
        if "=" not in c:
            raise typer.BadParameter(f"--column takes 'Factor=column', not {c!r}")
        k, v = c.split("=", 1)
        columns[k.strip()] = v.strip()
    payload = estimation.estimate(treatment, outcome, dataset, adjust=[] if no_adjust else (adjust or None),
                                  columns=columns or None, estimator=estimator)  # type: ignore[arg-type]
    sha = None
    if not no_record:
        sha, payload["run_id"] = estimation.record(payload)

    def human() -> None:
        e, u = payload["effect"], payload["unadjusted"]
        console.print(estimation.describe(payload) + ".\n")
        adj = ", ".join(payload["adjustment"]) or "nothing"
        console.print(f"Adjusted for: {adj} ({payload['adjustment_how']})")
        if payload["minimal_sets"]:
            sets = "; ".join("{" + ", ".join(s) + "}" if s else "{}" for s in payload["minimal_sets"])
            console.print(f"[dim]Minimal valid sets in the DAG: {sets}[/dim]")
        t = Table(show_header=True, header_style="bold")
        logistic = payload["model"] == "logistic"
        for col in ("", "Odds ratio" if logistic else "Estimate", "95% CI", "p"):
            t.add_column(col, justify="left" if not col else "right")
        for name, r in (("Adjusted", e), ("Unadjusted", u)):
            if logistic:
                t.add_row(name, f"{r['odds_ratio']:.4g}", f"{r['or_ci_low']:.4g} – {r['or_ci_high']:.4g}",
                          f"{r['p']:.3g}")
            else:
                t.add_row(name, f"{r['estimate']:.4g}", f"{r['ci_low']:.4g} – {r['ci_high']:.4g}", f"{r['p']:.3g}")
        console.print(t)
        console.print(f"{payload['model']} regression, {payload['se_type']} standard errors, n = {payload['n']}"
                      + (f" ({payload['dropped']} dropped)" if payload["dropped"] else ""))
        for w in payload["warnings"]:
            console.print(f"[yellow]caution:[/yellow] {w}")
        console.print("\n[dim]Causal only if: " + " ".join(payload["assumptions"]) + "[/dim]")
        if sha:
            console.print(f"\nrecorded · commit [cyan]{sha[:10]}[/cyan]")

    emit(payload, human=human, commit_sha=sha)


@app.command("global-sensitivity")
@handle_cli_errors
def global_sensitivity_cmd(
    model_type: str = typer.Argument(..., help="fault_tree | bow_tie | event_tree | decision_tree | markov | sd"),
    method: str = typer.Option("sobol", "--method", help="sobol (variance shares) | morris (a cheaper screen)."),
    n: int | None = typer.Option(None, "-n", help="Sobol: base samples, a power of two (default 512; SD 128). "
                                                   "Morris: trajectories (default 20; SD 10)."),
    seed: int = typer.Option(1234, "--seed", help="The same seed gives the same runs."),
    output: str | None = typer.Option(None, "--output", help="The result to headline (default: the model's main "
                                                             "one — the top event, the best option's advantage, "
                                                             "the net benefit at the willingness to pay)."),
    variable: str | None = typer.Option(None, "--variable", help="SD: the variable (default: the first stock)."),
    metric: str | None = typer.Option(None, "--metric",
                                      help="SD: final | peak | peak-time | min | mean | total | at:T."),
    no_record: bool = typer.Option(False, "--no-record", help="Show the result without recording it."),
) -> None:
    """Which uncertain inputs does the result depend on, alone and through interactions?

    Varies every input that has a range (`ft|bowtie|et uncertainty`, `dt|markov
    range`, `sd set-uncertainty`) together over its distribution. Sobol
    indices give the share of the result's variance each input explains on
    its own (S1) and with its interactions (ST); an input with ST near 0
    could be fixed anywhere in its range. Morris screening ranks inputs in
    far fewer runs (μ*), with σ flagging interactions or non-linearity.
    """
    from rich.markup import escape

    from latris.operations import global_sensitivity as gs

    payload = gs.analyse(model_type, method=method, n=n, seed=seed, output=output, variable=variable, metric=metric)
    sha = None
    if not no_record:
        sha, payload["run_id"] = gs.record(payload)

    def g(x, pct=False) -> str:
        return "—" if x is None else (f"{x:.0%}" if pct else f"{x:.3g}")

    def human() -> None:
        console.print(escape(gs.describe(payload)) + ".\n")
        main = next(o for o in payload["outputs"] if o["output"] == payload["primary"])
        t = Table(show_header=True, header_style="bold", title=f"Global sensitivity of {payload['primary']}")
        if payload["method"] == "sobol":
            for col in ("Input", "Total (ST)", "Alone (S1)", "Range checked"):
                t.add_column(col, justify="left" if col == "Input" else "right")
            for r in main["indices"]:
                t.add_row(escape(r["input"]), f"{g(r['ST'], True)} ± {g(r['ST_conf'], True)}",
                          f"{g(r['S1'], True)} ± {g(r['S1_conf'], True)}",
                          "[yellow]no[/yellow]" if r["weak"] else "yes")
        else:
            for col in ("Input", "μ*", "± (95%)", "σ", "Range checked"):
                t.add_column(col, justify="left" if col == "Input" else "right")
            for r in main["indices"]:
                t.add_row(escape(r["input"]), g(r["mu_star"]), g(r["mu_star_conf"]), g(r["sigma"]),
                          "[yellow]no[/yellow]" if r["weak"] else "yes")
        console.print(t)
        for note in payload["notes"]:
            console.print(f"[dim]{escape(note)}[/dim]")
        if payload["fixed"]:
            console.print("[dim]Held at their value (no range): " + escape(", ".join(payload["fixed"])) + "[/dim]")
        console.print(f"[dim]{payload['runs']} model runs, seed {payload['seed']}[/dim]")
        if sha:
            console.print(f"\nrecorded · commit [cyan]{sha[:10]}[/cyan]")

    emit(payload, human=human, commit_sha=sha)
