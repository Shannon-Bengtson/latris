from __future__ import annotations

import typer
from rich.console import Console

from latris.cli._errors import handle_cli_errors
from latris.operations import views as view_ops

app = typer.Typer(help="View projection operations.", no_args_is_help=True)
console = Console()


@app.command("project")
@handle_cli_errors
def view_project(
    kind: str = typer.Argument(..., help="View kind: cld | dag."),
) -> None:
    """Project the current mappings into a formal view."""
    view = view_ops.project_view(kind)
    console.print(f"Projected {kind} view: {len(view.entity_ids)} entities, {len(view.edge_ids)} edges")


@app.command("auto-project")
@handle_cli_errors
def view_auto_project(
    kind: str = typer.Argument(..., help="View kind: cld | dag."),
) -> None:
    """Map all substrate elements to a view and project it."""
    created = view_ops.auto_project(kind)
    console.print(f"Auto-projected {kind} view: {len(created)} new mappings created")
