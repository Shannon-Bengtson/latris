from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from latris.cli._errors import handle_cli_errors
from latris.operations import nodes as ops
from latris.schema.ids import id_timestamp

app = typer.Typer(help="Create, list, rename, remove nodes.", no_args_is_help=True)
console = Console()


@app.command("add")
@handle_cli_errors
def add(
    label: str = typer.Argument(..., help="Human-readable label for the node."),
    kind: str = typer.Option(
        "concept",
        "--kind",
        "-k",
        help="concept | variable | event | actor | state | decision | hazard",
    ),
) -> None:
    """Add a node to the substrate."""
    entity, sha = ops.add_node(label, kind=kind)  # type: ignore[arg-type]
    console.print(
        f"[green]added[/green] {entity.kind} [bold]{entity.label}[/bold] "
        f"([cyan]{entity.id}[/cyan]) · commit [cyan]{sha[:10]}[/cyan]"
    )


@app.command("list")
@handle_cli_errors
def list_() -> None:
    """List all nodes."""
    entities = ops.list_nodes()
    if not entities:
        console.print("[dim](no nodes yet — add one with `latris node add ...`)[/dim]")
        return
    table = Table(show_header=True, header_style="bold")
    table.add_column("ID")
    table.add_column("Kind")
    table.add_column("Label")
    for e in entities:
        table.add_row(e.id, e.kind, e.label)
    console.print(table)


@app.command("show")
@handle_cli_errors
def show(
    query: str = typer.Argument(..., help="Node ID, ID prefix, or label."),
) -> None:
    """Show a single node."""
    e = ops.get_node(query)
    console.print(f"[bold]id:[/bold] {e.id}")
    console.print(f"[bold]kind:[/bold] {e.kind}")
    console.print(f"[bold]label:[/bold] {e.label}")
    console.print(f"[bold]created:[/bold] {id_timestamp(e.id).isoformat()}")


@app.command("rename")
@handle_cli_errors
def rename(
    query: str = typer.Argument(..., help="Node ID, ID prefix, or current label."),
    new_label: str = typer.Argument(..., help="New label."),
) -> None:
    """Rename a node's human-readable label (ID stays stable)."""
    entity, sha = ops.rename_node(query, new_label)
    console.print(f"[green]renamed[/green] {entity.id} → [bold]{entity.label}[/bold] · commit [cyan]{sha[:10]}[/cyan]")


@app.command("remove")
@handle_cli_errors
def remove(
    query: str = typer.Argument(..., help="Node ID, ID prefix, or label."),
) -> None:
    """Remove a node and cascade-delete edges that touch it."""
    entity, edges, sha = ops.remove_node(query)
    console.print(
        f"[green]removed[/green] [bold]{entity.label}[/bold] "
        f"({entity.id}) + {len(edges)} edge(s) · commit [cyan]{sha[:10]}[/cyan]"
    )
