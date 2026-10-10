"""Analysis CLI commands — loops, propagation, d-separation, blanket, paths."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from latris.cli._errors import handle_cli_errors

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
    from latris.operations.analysis import analyse_loops

    classified = analyse_loops()
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
