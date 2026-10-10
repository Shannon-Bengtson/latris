from __future__ import annotations

from datetime import date

import typer
from rich.console import Console
from rich.table import Table

from latris.cli._errors import handle_cli_errors
from latris.operations import elicitation as elicit_ops

app = typer.Typer(help="Expert elicitation sessions.", no_args_is_help=True)
console = Console()


@app.command("start")
@handle_cli_errors
def elicit_start(
    protocol: str = typer.Option(
        ...,
        "--protocol",
        "-p",
        help="Protocol: delphi | shelf | idea | cooke | ahp | direct | workshop | other.",
    ),
    facilitator: str = typer.Option(..., "--facilitator", "-f", help="Facilitator name."),
    expert: list[str] = typer.Option([], "--expert", "-e", help="Expert name (repeatable)."),
    target: list[str] = typer.Option(
        [],
        "--target",
        "-t",
        help="Target as 'target_id/attribute' (repeatable).",
    ),
    held_at: str = typer.Option(None, "--date", help="Session date (YYYY-MM-DD)."),
) -> None:
    """Start a new elicitation session."""
    targets = []
    for t in target:
        parts = t.split("/", 1)
        if len(parts) != 2:
            console.print(f"[red]Invalid target format: {t!r} — expected 'target_id/attribute'[/red]")
            raise typer.Exit(code=2)
        targets.append((parts[0], parts[1]))

    parsed_date = date.fromisoformat(held_at) if held_at else None
    session, sha = elicit_ops.start_session(
        protocol,
        facilitator,
        expert,
        targets,
        held_at=parsed_date,
    )
    console.print(f"Started session [cyan]{session.id[:20]}…[/cyan] ({protocol})")


@app.command("round")
@handle_cli_errors
def elicit_round(
    session_id: str = typer.Argument(..., help="Session ID."),
    expert: str = typer.Option(..., "--expert", "-e", help="Expert name."),
    input_text: str = typer.Option(..., "--input", "-i", help="Expert's raw input."),
    rationale: str = typer.Option(None, "--rationale", "-r", help="Expert's rationale."),
    round_num: int = typer.Option(1, "--round", "-n", help="Round number."),
) -> None:
    """Add an expert response to a session."""
    session, sha = elicit_ops.add_round(
        session_id,
        expert,
        input_text,
        rationale=rationale,
        round_num=round_num,
    )
    console.print(f"Added round {round_num} from {expert}")


@app.command("aggregate")
@handle_cli_errors
def elicit_aggregate(
    session_id: str = typer.Argument(..., help="Session ID."),
    result: str = typer.Option(..., "--result", "-r", help="Aggregated result (JSON or text)."),
    confidence: str = typer.Option(None, "--confidence", "-c", help="Confidence summary."),
) -> None:
    """Set the aggregated result for a session."""
    import json

    try:
        parsed = json.loads(result)
    except json.JSONDecodeError:
        parsed = {"value": result}

    session, sha = elicit_ops.aggregate_session(
        session_id,
        parsed,
        confidence_summary=confidence,
    )
    console.print(f"Aggregated session [cyan]{session_id[:20]}…[/cyan]")


@app.command("finalise")
@handle_cli_errors
def elicit_finalise(
    session_id: str = typer.Argument(..., help="Session ID."),
) -> None:
    """Finalise a session — bind results to attributes, set provenance."""
    session, sha = elicit_ops.finalise_session(session_id)
    console.print(f"Finalised session [cyan]{session_id[:20]}…[/cyan]")


@app.command("list")
@handle_cli_errors
def elicit_list() -> None:
    """List all elicitation sessions."""
    entries = elicit_ops.list_sessions()
    if not entries:
        console.print("[dim](no elicitation sessions)[/dim]")
        return
    table = Table(show_header=True, header_style="bold")
    table.add_column("ID", style="cyan")
    table.add_column("File")
    for e in entries:
        table.add_row(e.id[:25] + "…", e.file_path)
    console.print(table)


@app.command("show")
@handle_cli_errors
def elicit_show(
    session_id: str = typer.Argument(..., help="Session ID."),
) -> None:
    """Show a single elicitation session."""
    session = elicit_ops.get_session(session_id)
    console.print(f"[bold]id:[/bold] {session.id}")
    console.print(f"[bold]phase:[/bold] {session.phase}")
    console.print(f"[bold]held_at:[/bold] {session.held_at}")
    console.print(f"[bold]facilitator:[/bold] {session.facilitator.name}")
    console.print(f"[bold]protocol:[/bold] {session.protocol.name}")
    console.print(f"[bold]experts:[/bold] {', '.join(e.name for e in session.experts)}")
    console.print("[bold]targets:[/bold]")
    for ta in session.target_attributes:
        console.print(f"  • {ta.target_id}/{ta.attribute}")
    console.print(f"[bold]responses:[/bold] {len(session.raw_responses)}")
    if session.aggregated_result:
        console.print(f"[bold]aggregated:[/bold] {session.aggregated_result}")
    if session.confidence_summary:
        console.print(f"[bold]confidence:[/bold] {session.confidence_summary}")
