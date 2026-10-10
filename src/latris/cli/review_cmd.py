from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from latris.cli._errors import handle_cli_errors
from latris.operations import review as review_ops

app = typer.Typer(help="Review pack import.", no_args_is_help=True)
console = Console()


@app.command("import")
@handle_cli_errors
def import_review(
    file: str = typer.Argument(..., help="Path to the completed review HTML file."),
) -> None:
    """Import a completed review HTML file and create provenance objects."""
    path = Path(file)
    if not path.exists():
        raise typer.BadParameter(f"File not found: {file}")

    html = path.read_text(encoding="utf-8")
    result = review_ops.import_review(html)

    console.print(f"[green]Imported review from {result.session.reviewer.name}[/green]")
    console.print(f"  Challenges: {result.challenges_created}")
    console.print(f"  Questions:  {result.questions_created}")
    console.print(f"  Sign-offs:  {result.signoffs_created}")
    if result.version_drift:
        console.print("[yellow]  Warning: model has changed since this review was exported[/yellow]")
    for w in result.warnings:
        console.print(f"  [dim]{w}[/dim]")
    console.print(f"  Commit: {result.commit_sha[:12]}")
