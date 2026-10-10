from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from latris.cli._errors import handle_cli_errors
from latris.operations import mappings as mapping_ops

app = typer.Typer(help="Map substrate elements to formal views.", no_args_is_help=True)
console = Console()


@app.command("add")
@handle_cli_errors
def mapping_add(
    l2_id: str = typer.Argument(..., help="Substrate entity/edge (ID / prefix / label)."),
    view: str = typer.Argument(..., help="Target view: cld | dag."),
    ai_proposed: bool = typer.Option(False, "--ai-proposed", help="Mark as AI-proposed."),
) -> None:
    """Map a substrate element to a view."""
    mapping, sha = mapping_ops.map_to_view(l2_id, view, ai_proposed=ai_proposed)
    console.print(f"Mapped [cyan]{mapping.l2_id[:20]}…[/cyan] → {view}")


@app.command("remove")
@handle_cli_errors
def mapping_remove(
    l2_id: str = typer.Argument(..., help="Substrate entity/edge (ID / prefix / label)."),
    view: str = typer.Argument(..., help="View to unmap from: cld | dag."),
) -> None:
    """Remove a mapping from a view."""
    removed, sha = mapping_ops.unmap_from_view(l2_id, view)
    console.print(f"Unmapped [cyan]{removed.l2_id[:20]}…[/cyan] from {view}")


@app.command("list")
@handle_cli_errors
def mapping_list(
    view: str = typer.Option(None, "--view", "-v", help="Filter by view kind."),
) -> None:
    """List mappings, optionally filtered by view."""
    mappings = mapping_ops.list_mappings(view_kind=view)
    if not mappings:
        console.print("[dim](no mappings)[/dim]")
        return
    table = Table(show_header=True, header_style="bold")
    table.add_column("L2 ID", style="cyan")
    table.add_column("View")
    table.add_column("L3 ID")
    table.add_column("Origin")
    table.add_column("Maturity")
    for m in mappings:
        table.add_row(
            m.l2_id[:25] + ("…" if len(m.l2_id) > 25 else ""),
            m.l3_view,
            m.l3_id[:25] + ("…" if len(m.l3_id) > 25 else ""),
            m.origin,
            m.maturity,
        )
    console.print(table)


@app.command("approve")
@handle_cli_errors
def mapping_approve(
    l2_id: str = typer.Argument(..., help="Substrate entity/edge (ID / prefix / label)."),
    view: str = typer.Argument(..., help="View: cld | dag."),
) -> None:
    """Approve an AI-proposed mapping."""
    mapping, sha = mapping_ops.approve_mapping(l2_id, view)
    console.print(f"Approved mapping [cyan]{mapping.l2_id[:20]}…[/cyan] ↔ {view}")
