"""CLI: log, status, diff — all semantic."""

from __future__ import annotations

import typer
from rich.console import Console

from latris.cli._errors import handle_cli_errors
from latris.diff.semantic import (
    SemanticEvent,
    diff_commits,
    diff_working_tree,
    read_log,
)
from latris.repo.project import require_project

console = Console()


def _print_events(events: list[SemanticEvent], header: str | None = None) -> None:
    if header:
        console.print(header)
    if not events:
        console.print("[dim](no changes)[/dim]")
        return
    for ev in events:
        console.print(f"  • {ev.summary}")


@handle_cli_errors
def log_cmd(
    limit: int = typer.Option(
        20,
        "--limit",
        "-n",
        help="Number of commits to show (most recent first).",
    ),
) -> None:
    """Show the project's semantic commit history (most recent first)."""
    paths = require_project()
    entries = read_log(paths.root, limit=limit)
    if not entries:
        console.print("[dim](no commits yet)[/dim]")
        return
    for c in entries:
        short = c["sha"][:10]
        date = c["date"][:10]  # YYYY-MM-DD portion
        console.print(f"[cyan]{short}[/cyan] [dim]{date}[/dim] [magenta]{c['author']}[/magenta] · {c['subject']}")


@handle_cli_errors
def status_cmd() -> None:
    """Summarise uncommitted changes against HEAD, semantically."""
    paths = require_project()
    events = diff_working_tree(paths.root)
    if not events:
        console.print("[green]clean[/green] — no uncommitted changes.")
        return
    _print_events(events, header="[bold]uncommitted changes:[/bold]")


@handle_cli_errors
def diff_cmd(
    revrange: str | None = typer.Argument(
        None,
        help="Blank = working tree vs HEAD. Single SHA = just that commit. 'A..B' = range from A to B.",
    ),
) -> None:
    """Show semantic changes, optionally for a commit or range."""
    paths = require_project()
    if revrange is None:
        events = diff_working_tree(paths.root)
        header = "[bold]working tree vs HEAD:[/bold]"
    elif ".." in revrange:
        base, head = revrange.split("..", 1)
        events = diff_commits(paths.root, base, head)
        header = f"[bold]{base}..{head}:[/bold]"
    else:
        events = diff_commits(paths.root, f"{revrange}^", revrange)
        header = f"[bold]commit {revrange}:[/bold]"
    _print_events(events, header=header)
