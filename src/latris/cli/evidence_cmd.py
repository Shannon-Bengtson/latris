from __future__ import annotations

import typer
from rich.console import Console

from latris.cli._errors import handle_cli_errors
from latris.operations import evidence as ops

app = typer.Typer(help="Attach citations to attributes.", no_args_is_help=True)
console = Console()


@app.command("add")
@handle_cli_errors
def add(
    target: str = typer.Argument(..., help="Node ID/label or edge ID."),
    attribute: str = typer.Argument(..., help="Attribute name (e.g. description, polarity)."),
    bibkey: str = typer.Argument(..., help="Existing reference key."),
    verified_by: str = typer.Option(
        "human",
        "--verified-by",
        help="human | ai — who verified the citation applies.",
    ),
    notes: str = typer.Option(None, "--notes", help="Free-text notes on the link."),
) -> None:
    """Attach a citation to a (target, attribute) pair."""
    if verified_by not in {"human", "ai"}:
        console.print("[red]error:[/red] --verified-by must be 'human' or 'ai'.")
        raise typer.Exit(code=2)
    link, sha = ops.add_evidence(
        target,
        attribute,
        bibkey,
        verified_by=verified_by,  # type: ignore[arg-type]
        notes=notes,
    )
    console.print(
        f"[green]attached[/green] {bibkey} → {link.target_id[:15]}…/{attribute} · commit [cyan]{sha[:10]}[/cyan]"
    )
