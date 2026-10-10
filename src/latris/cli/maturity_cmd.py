"""Maturity CLI — propose / review / approve modelling artifacts.

Single chokepoint per docs/design/MATURITY_LADDER.md. ``approve``
atomically writes a ``Signoff`` row.
"""

from __future__ import annotations

import typer
from rich.console import Console

from latris.cli._errors import handle_cli_errors
from latris.operations import maturity as ops

app = typer.Typer(help="Advance an artifact's maturity (proposed → reviewed → approved).", no_args_is_help=True)
console = Console()


@app.command("propose")
@handle_cli_errors
def propose_cmd(
    target: str = typer.Argument(..., help="Entity/edge/finding/mapping/milestone/lineage-node ID or label."),
) -> None:
    """Set the target's maturity to ``proposed``."""
    new_level, sha = ops.propose(target)
    console.print(f"[dim]proposed[/dim] [cyan]{target}[/cyan] · commit [cyan]{sha[:10]}[/cyan]")


@app.command("review")
@handle_cli_errors
def review_cmd(
    target: str = typer.Argument(..., help="Entity/edge/finding/mapping/milestone/lineage-node ID or label."),
) -> None:
    """Mark the target as ``reviewed``."""
    new_level, sha = ops.mark_reviewed(target)
    console.print(f"[blue]reviewed[/blue] [cyan]{target}[/cyan] · commit [cyan]{sha[:10]}[/cyan]")


@app.command("approve")
@handle_cli_errors
def approve_cmd(
    target: str = typer.Argument(..., help="Entity/edge/finding/mapping/milestone/lineage-node ID or label."),
    role: str = typer.Option("Reviewer", "--role", "-r", help="Reviewer role (defaults to 'Reviewer')."),
    scope: str = typer.Option("Model", "--scope", "-s", help="Approval scope (defaults to 'Model')."),
    notes: str = typer.Option(None, "--notes", "-n", help="Optional notes."),
) -> None:
    """Approve the target — sets maturity to ``approved`` and writes a Signoff row."""
    new_level, sha = ops.approve(target, role=role, scope=scope, notes=notes)
    console.print(f"[green]approved[/green] [cyan]{target}[/cyan] · commit [cyan]{sha[:10]}[/cyan]")
