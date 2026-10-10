"""FCM CLI commands — set weights, run inference, compare scenarios."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from latris.cli._errors import handle_cli_errors

app = typer.Typer(help="Fuzzy Cognitive Map operations.", no_args_is_help=True)
console = Console()


@app.command("set-weight")
@handle_cli_errors
def set_weight(
    edge: str = typer.Argument(..., help="Edge ID, ID prefix, or 'from→to' label."),
    value: str = typer.Argument(..., help="Weight value in [-1, +1]."),
) -> None:
    """Set the FCM weight on an edge."""
    from latris.operations import view_attributes as va

    target_id, sha = va.set_view_attribute(edge, "fcm", "weight", value)
    console.print(f"[green]set[/green] FCM weight on {target_id[:15]}… = {value} · commit [cyan]{sha[:10]}[/cyan]")


@app.command("weights")
@handle_cli_errors
def weights() -> None:
    """List all FCM edge weights."""
    from latris.operations import edges as edge_ops
    from latris.operations import nodes as node_ops
    from latris.operations import view_attributes as va

    store = va.get_view_attributes("fcm", "weight")
    edges = edge_ops.list_edges()
    entities = node_ops.list_nodes()

    labels = {e.id: e.label for e in entities}
    weight_map = {e.target_id: e.value for e in store.entries}

    if not edges:
        console.print("[dim](no edges)[/dim]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Edge")
    table.add_column("Weight")
    table.add_column("Edge maturity")
    for e in edges:
        from_label = labels.get(e.from_id, e.from_id[:10])
        to_label = labels.get(e.to_id, e.to_id[:10])
        w = weight_map.get(e.id)
        weight_str = f"{w:+.2f}" if w is not None else "[dim]—[/dim]"
        table.add_row(f"{from_label} → {to_label}", weight_str, e.maturity)
    console.print(table)


@app.command("infer")
@handle_cli_errors
def infer(
    clamp: list[str] | None = typer.Option(None, "--clamp", "-c", help="Clamp entity=value (e.g. 'Price=1.0')."),
) -> None:
    """Run FCM inference to steady state."""
    from latris.operations import nodes as node_ops
    from latris.operations.analysis import infer_fcm

    entities = node_ops.list_nodes()
    entity_ids = [e.id for e in entities]
    labels = {e.id: e.label for e in entities}

    # Parse clamps
    clamped: dict[str, float] = {}
    if clamp:
        from latris.operations._resolve import resolve_target
        from latris.repo.project import require_project
        from latris.repo.yaml_io import load_model
        from latris.schema import Substrate

        paths = require_project(None)
        substrate = load_model(Substrate, paths.conceptual_yaml)
        for c in clamp:
            if "=" not in c:
                raise typer.BadParameter(f"Clamp must be 'entity=value', got {c!r}")
            name, val_str = c.rsplit("=", 1)
            eid = resolve_target(name.strip(), substrate)
            clamped[eid] = float(val_str.strip())

    result = infer_fcm(clamped=clamped or None)

    # Display
    status = "[green]converged[/green]" if result.converged else "[yellow]did not converge[/yellow]"
    console.print(f"FCM inference: {status} in {result.iterations} iteration(s)\n")

    table = Table(show_header=True, header_style="bold")
    table.add_column("Variable")
    table.add_column("Activation", justify="right")
    table.add_column("Status")
    for eid in entity_ids:
        label = labels.get(eid, eid[:12])
        val = result.activations.get(eid, 0.5)
        # Colour by activation level
        if val > 0.7:
            val_str = f"[green]{val:.3f}[/green]"
        elif val < 0.3:
            val_str = f"[red]{val:.3f}[/red]"
        else:
            val_str = f"{val:.3f}"
        status_str = "[bold]clamped[/bold]" if eid in clamped else ""
        table.add_row(label, val_str, status_str)
    console.print(table)
