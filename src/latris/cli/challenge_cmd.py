from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from latris.cli._errors import handle_cli_errors
from latris.operations import challenges as ops
from latris.schema.ids import id_timestamp

app = typer.Typer(
    help="Open, discuss, and resolve challenges against model elements.",
    no_args_is_help=True,
)
console = Console()


@app.command("open")
@handle_cli_errors
def open_(
    target: str = typer.Argument(..., help="Node ID/label or edge ID to challenge."),
    argument: str = typer.Argument(..., help="The argument against the target."),
    attribute: str = typer.Option(
        None,
        "--attribute",
        "-a",
        help="Specific attribute under challenge (e.g. 'polarity'). "
        "If set and the attribute exists, its maturity flips to 'challenged'.",
    ),
) -> None:
    """Open a challenge against a model element."""
    ch, sha = ops.open_challenge(target, argument, attribute=attribute)
    console.print(f"[green]opened[/green] challenge [cyan]{ch.id}[/cyan] · commit [cyan]{sha[:10]}[/cyan]")


@app.command("resolve")
@handle_cli_errors
def resolve(
    challenge: str = typer.Argument(..., help="Challenge ID or prefix."),
    state: str = typer.Option(
        ...,
        "--state",
        "-s",
        help="Terminal state: " + " | ".join(ops.TERMINAL_STATES),
    ),
    rationale: str = typer.Option(
        None,
        "--rationale",
        "-r",
        help="Why this outcome was reached.",
    ),
) -> None:
    """Close a challenge with a terminal state."""
    ch, sha = ops.resolve_challenge(challenge, state, rationale=rationale)  # type: ignore[arg-type]
    console.print(f"[green]resolved[/green] {ch.id} → [bold]{state}[/bold] · commit [cyan]{sha[:10]}[/cyan]")


@app.command("turn")
@handle_cli_errors
def turn(
    challenge: str = typer.Argument(..., help="Challenge ID or prefix."),
    message: str = typer.Argument(..., help="Your turn in the conversation."),
) -> None:
    """Append a conversation turn to an open challenge."""
    ch, sha = ops.add_turn(challenge, message)
    console.print(
        f"[green]added turn[/green] to {ch.id} (now {len(ch.conversation)} turn(s)) · commit [cyan]{sha[:10]}[/cyan]"
    )


@app.command("list")
@handle_cli_errors
def list_() -> None:
    """List all challenges."""
    entries = ops.list_challenges()
    if not entries:
        console.print("[dim](no challenges yet)[/dim]")
        return
    table = Table(show_header=True, header_style="bold")
    table.add_column("ID")
    table.add_column("State")
    table.add_column("Target")
    table.add_column("Attribute")
    table.add_column("Argument")
    for c in entries:
        state_style = "green" if c.state == "open" else "dim"
        table.add_row(
            c.id,
            f"[{state_style}]{c.state}[/{state_style}]",
            c.target_id[:20] + "…",
            c.target_attribute or "—",
            (c.argument[:60] + "…") if len(c.argument) > 60 else c.argument,
        )
    console.print(table)


@app.command("show")
@handle_cli_errors
def show(
    challenge: str = typer.Argument(..., help="Challenge ID or prefix."),
) -> None:
    """Show a single challenge with its full conversation."""
    ch = ops.get_challenge(challenge)
    console.print(f"[bold]id:[/bold] {ch.id}")
    console.print(f"[bold]state:[/bold] {ch.state}")
    console.print(f"[bold]target:[/bold] {ch.target_id}")
    if ch.target_attribute:
        console.print(f"[bold]attribute:[/bold] {ch.target_attribute}")
    console.print(f"[bold]argument:[/bold] {ch.argument}")
    console.print(f"[bold]opened:[/bold] {id_timestamp(ch.id).isoformat()} by {getattr(ch.opened_by, 'name', ch.opened_by)}")  # noqa: E501
    if ch.resolved_at:
        console.print(f"[bold]resolved:[/bold] {ch.resolved_at.isoformat()}")
        if ch.resolution_rationale:
            console.print(f"[bold]rationale:[/bold] {ch.resolution_rationale}")
    if ch.conversation:
        console.print("[bold]conversation:[/bold]")
        for i, t in enumerate(ch.conversation, 1):
            speaker = getattr(t.speaker, "name", None) or getattr(t.speaker, "model_id", "?")
            console.print(f"  {i}. [{t.at.isoformat()}] {speaker}: {t.message}")
