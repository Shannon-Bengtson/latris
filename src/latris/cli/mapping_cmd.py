from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from latris.cli._agent import CONFIRMED_BY_PERSON, require_person
from latris.cli._errors import handle_cli_errors
from latris.operations import mappings as mapping_ops

app = typer.Typer(help="Map substrate elements to formal views.", no_args_is_help=True)

# Where each command sits in the workflow (schema/workflow.py; rules in docs/engineering/WORKFLOW_STRUCTURE.md).
PLACE = {
    "*": "build.structure",
    "mapping_approve": "ai",
}
console = Console()


@app.command("add")
@handle_cli_errors
def mapping_add(
    l2_id: str = typer.Argument(..., help="Substrate entity/edge (ID / prefix / label)."),
    view: str = typer.Argument(..., help="Model type (e.g. cld, sd)."),
    ai_proposed: bool = typer.Option(False, "--ai-proposed", help="Mark as AI-proposed."),
) -> None:
    """Put a factor or link in a model type's view (back in, if it was left out)."""
    mapping, sha = mapping_ops.map_to_view(l2_id, view, ai_proposed=ai_proposed)
    console.print(f"Mapped [cyan]{mapping.l2_id[:20]}…[/cyan] → {view}")


@app.command("leave-out")
@handle_cli_errors
def mapping_leave_out(
    l2_id: str = typer.Argument(..., help="Substrate entity/edge (ID / prefix / label)."),
    view: str = typer.Argument(..., help="Model type to leave it out of (e.g. cld, sd)."),
    reason: str = typer.Option(None, "--reason", "-r", help="Why it doesn't belong in this model type."),
) -> None:
    """Leave a factor or link out of a model type, and keep it out (`mapping add` puts it back)."""
    entry, sha = mapping_ops.leave_out(l2_id, view, reason=reason)
    console.print(f"Left [cyan]{l2_id}[/cyan] out of {view} ([cyan]{sha[:10]}[/cyan])", highlight=False)


@app.command("list")
@handle_cli_errors
def mapping_list(
    view: str = typer.Option(None, "--view", "-v", help="Filter by view kind."),
) -> None:
    """List mappings, and what's been left out, optionally filtered by view."""
    mappings = mapping_ops.list_mappings(view_kind=view)
    left_out = mapping_ops.list_left_out(view_kind=view)
    for x in left_out:
        why = f" — {x.reason}" if x.reason else ""
        console.print(f"left out of {x.l3_view}: [cyan]{x.l2_id}[/cyan]{why}", highlight=False)
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
    confirmed_by_person: bool = CONFIRMED_BY_PERSON,
) -> None:
    """Approve an AI-proposed mapping."""
    require_person(confirmed_by_person, "Approving a mapping")
    mapping, sha = mapping_ops.approve_mapping(l2_id, view)
    console.print(f"Approved mapping [cyan]{mapping.l2_id[:20]}…[/cyan] ↔ {view}")
