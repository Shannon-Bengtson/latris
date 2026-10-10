from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from latris.cli._errors import handle_cli_errors
from latris.operations import edges as ops
from latris.operations import nodes as node_ops

app = typer.Typer(help="Create, list, remove edges.", no_args_is_help=True)
console = Console()


@app.command("add")
@handle_cli_errors
def add(
    from_node: str = typer.Argument(..., help="Source: node ID, prefix, or label."),
    to_node: str = typer.Argument(..., help="Target: node ID, prefix, or label."),
    kind: str = typer.Option(
        "causal",
        "--kind",
        "-k",
        help="causal | temporal | decomposition | conditional | informational | flow | support | logical | association",
    ),
) -> None:
    """Add an edge between two existing nodes."""
    edge, sha = ops.add_edge(from_node, to_node, kind=kind)  # type: ignore[arg-type]
    console.print(f"[green]added[/green] edge [cyan]{edge.id}[/cyan] ({edge.kind}) · commit [cyan]{sha[:10]}[/cyan]")


@app.command("list")
@handle_cli_errors
def list_() -> None:
    """List all edges."""
    edges = ops.list_edges()
    if not edges:
        console.print("[dim](no edges yet)[/dim]")
        return
    labels = {e.id: e.label for e in node_ops.list_nodes()}
    table = Table(show_header=True, header_style="bold")
    table.add_column("ID")
    table.add_column("Kind")
    table.add_column("From")
    table.add_column("→")
    table.add_column("To")
    for e in edges:
        table.add_row(
            e.id,
            e.kind,
            f"{labels.get(e.from_id, '?')} ({e.from_id[:12]}…)",
            "→",
            f"{labels.get(e.to_id, '?')} ({e.to_id[:12]}…)",
        )
    console.print(table)


@app.command("remove")
@handle_cli_errors
def remove(
    query: str = typer.Argument(..., help="Edge ID or prefix."),
) -> None:
    """Remove an edge."""
    edge, sha = ops.remove_edge(query)
    console.print(f"[green]removed[/green] edge {edge.id} · commit [cyan]{sha[:10]}[/cyan]")
