"""CLI wiring for the 7 provenance commands.

Concept doc pattern: one verb per log type. This module exposes a Typer app
per log kind, each with a single verb. They're registered on the root app
as ``assumption``, ``decision``, ``signoff``, ``session``, ``question``,
``exclusion``, ``prediction``.
"""

from __future__ import annotations

from datetime import date, datetime

import typer
from rich.console import Console

from latris.cli._errors import handle_cli_errors
from latris.operations import provenance as ops

console = Console()


# ---- assumption ----

assumption_app = typer.Typer(help="Log modelling assumptions.", no_args_is_help=True)


@assumption_app.command("add")
@handle_cli_errors
def assumption_add(
    statement: str = typer.Argument(..., help="The assumption being made."),
    rationale: str = typer.Option(None, "--rationale", "-r", help="Why this assumption holds."),
    target: str = typer.Option(None, "--target", "-t", help="Node or edge ID this assumption is about."),
) -> None:
    """Log a modelling assumption."""
    entry, sha = ops.add_assumption(statement, rationale, target_id=target)
    console.print(f"[green]logged assumption[/green] [cyan]{entry.id}[/cyan] · commit [cyan]{sha[:10]}[/cyan]")


# ---- decision ----

decision_app = typer.Typer(
    help="Log unforced modelling decisions (e.g. exclusions, scoping calls).",
    no_args_is_help=True,
)


@decision_app.command("log")
@handle_cli_errors
def decision_log(
    statement: str = typer.Argument(..., help="The decision taken."),
    rationale: str = typer.Option(..., "--rationale", "-r", help="Why this decision was taken."),
    target: str = typer.Option(None, "--target", "-t", help="Node or edge ID this decision is about."),
) -> None:
    """Log an unforced modelling decision."""
    entry, sha = ops.log_decision(statement, rationale, target_id=target)
    console.print(f"[green]logged decision[/green] [cyan]{entry.id}[/cyan] · commit [cyan]{sha[:10]}[/cyan]")


# ---- signoff ----

signoff_app = typer.Typer(help="Record formal review sign-offs.", no_args_is_help=True)


@signoff_app.command("record")
@handle_cli_errors
def signoff_record(
    role: str = typer.Option(..., "--role", help="Reviewer's role (e.g. 'Senior reviewer')."),
    scope: str = typer.Option(..., "--scope", help="What the sign-off covers."),
    notes: str = typer.Option(None, "--notes", help="Free-text notes."),
) -> None:
    """Record a formal review sign-off."""
    entry, sha = ops.record_signoff(role=role, scope=scope, notes=notes)
    console.print(f"[green]recorded sign-off[/green] [cyan]{entry.id}[/cyan] · commit [cyan]{sha[:10]}[/cyan]")


# ---- session ----

session_app = typer.Typer(help="Record working/workshop sessions.", no_args_is_help=True)


@session_app.command("record")
@handle_cli_errors
def session_record(
    held_at: str = typer.Option(..., "--date", help="Date the session was held (YYYY-MM-DD)."),
    attendee: list[str] = typer.Option(
        None,
        "--attendee",
        "-a",
        help="Attendee name. Repeat for multiple attendees.",
    ),
    notes: str = typer.Option(None, "--notes", help="Short notes."),
    notes_file: str = typer.Option(
        None,
        "--notes-file",
        help="Path to a separate notes/transcript file (relative to project).",
    ),
) -> None:
    """Record a working or workshop session."""
    try:
        parsed_date: date = datetime.strptime(held_at, "%Y-%m-%d").date()
    except ValueError as exc:
        raise typer.BadParameter(f"--date must be YYYY-MM-DD, got {held_at!r}") from exc
    attendees = list(attendee or [])
    entry, sha = ops.record_session(
        parsed_date,
        attendees,
        notes=notes,
        notes_file=notes_file,
    )
    console.print(f"[green]recorded session[/green] [cyan]{entry.id}[/cyan] · commit [cyan]{sha[:10]}[/cyan]")


# ---- question ----

question_app = typer.Typer(help="Log unresolved structural questions.", no_args_is_help=True)


@question_app.command("add")
@handle_cli_errors
def question_add(
    question: str = typer.Argument(..., help="The open question."),
    target: str = typer.Option(None, "--target", "-t", help="Node or edge ID this question is about."),
) -> None:
    """Log an unresolved structural question."""
    entry, sha = ops.add_question(question, target_id=target)
    console.print(f"[green]logged question[/green] [cyan]{entry.id}[/cyan] · commit [cyan]{sha[:10]}[/cyan]")


# ---- exclusion ----

exclusion_app = typer.Typer(
    help="Log scope boundaries / negative claims / validity limits.",
    no_args_is_help=True,
)


@exclusion_app.command("add")
@handle_cli_errors
def exclusion_add(
    statement: str = typer.Argument(..., help="What is being excluded."),
    rationale: str = typer.Option(..., "--rationale", "-r", help="Why it's excluded."),
) -> None:
    """Log a scope boundary, negative claim, or validity limit."""
    entry, sha = ops.add_exclusion(statement, rationale)
    console.print(f"[green]logged exclusion[/green] [cyan]{entry.id}[/cyan] · commit [cyan]{sha[:10]}[/cyan]")


# ---- prediction ----

prediction_app = typer.Typer(
    help="Record predictions for future outcome-tracking.",
    no_args_is_help=True,
)


@prediction_app.command("add")
@handle_cli_errors
def prediction_add(
    statement: str = typer.Argument(..., help="The prediction."),
    horizon: str = typer.Option(
        ...,
        "--horizon",
        help="Time horizon (free-form, e.g. '6 months', 'by 2027-Q1').",
    ),
) -> None:
    """Record a prediction for future outcome-tracking."""
    entry, sha = ops.add_prediction(statement, horizon)
    console.print(f"[green]logged prediction[/green] [cyan]{entry.id}[/cyan] · commit [cyan]{sha[:10]}[/cyan]")
