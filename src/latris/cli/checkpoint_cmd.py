"""``latris checkpoint`` — where an AI building a model stops and asks the person.

``show`` lists the five checkpoints (framing, structure, values, surprise, audience) and the one open now,
with questions built from the model. ``record`` keeps the person's answers, ``skip`` carries on without
them (with a reason the report shows), ``pace just-build`` stops asking for the rest of the model.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import typer
from rich.console import Console
from rich.markup import escape

from latris.cli._errors import handle_cli_errors
from latris.cli._output import emit
from latris.operations import checkpoints as ops

app = typer.Typer(
    help="Checkpoints: what to ask the person at each phase (`show`), and their answers (`record`, `skip`, `pace`).",
    no_args_is_help=True,
)
console = Console()

_STATE_TEXT = {
    "open": "[yellow]open — ask now[/yellow]",
    "answered": "[green]answered[/green]",
    "skipped": "[red]skipped[/red]",
    "not_reached": "[dim]not reached yet[/dim]",
    "not_needed": "[dim]not needed[/dim]",
    "not_asked": "[dim]not asked (just building)[/dim]",
}


def checkpoint_text(c: ops.Checkpoint) -> str:
    """An open checkpoint as rich text: what to ask, and how to record the answer."""
    lines = [f"[bold yellow]Checkpoint: {c.id}[/bold yellow] ({c.phase}) — {escape(c.why)}"]
    if c.before_asking:
        lines.append(f"  first: {escape(c.before_asking)}")
    lines += [f"  {i}. {escape(q)}" for i, q in enumerate(c.questions, 1)]
    lines.append(f"  [dim]{escape(c.how)}{' ' + escape(c.then) if c.then else ''}[/dim]")
    return "\n".join(lines)


def open_checkpoint_for_agent() -> ops.Checkpoint | None:
    """The open checkpoint when an AI agent is driving the CLI (people at a terminal aren't nagged)."""
    from latris.cli._agent import detected_agent

    if detected_agent() is None:
        return None
    try:
        return ops.open_checkpoint()
    except (OSError, ValueError, LookupError):
        return None


def _plain(c: ops.Checkpoint | None) -> dict[str, Any] | None:
    return asdict(c) if c else None


@app.command("show")
@handle_cli_errors
def show() -> None:
    """Every checkpoint's state, and the one to ask the person about now."""
    report = ops.checkpoint_report()

    def human() -> None:
        console.print(f"pace: {'just build (no checkpoints)' if report.pace == 'just_build' else 'ask the person'}")
        for s in report.checkpoints:
            console.print(f"  {s.id:<10} {s.phase:<24} {_STATE_TEXT[s.state]}")
        if report.open:
            console.print("\n" + checkpoint_text(report.open))
        else:
            console.print("\n[green]Nothing to ask the person right now.[/green]")

    emit({"pace": report.pace, "open": _plain(report.open),
          "checkpoints": [asdict(s) for s in report.checkpoints]}, human=human)


@app.command("record")
@handle_cli_errors
def record(
    checkpoint: str = typer.Argument(..., help="framing | structure | values | surprise | audience"),
    answers: str = typer.Option(..., "--answers", "-a", help="What the person said, in their words."),
    question: list[str] = typer.Option(
        None, "--question", "-q", help="A question you asked (repeatable; default: the checkpoint's own)."
    ),
    via: str = typer.Option(None, "--via", help="How the answers reached you, e.g. 'chat' (default: the agent)."),
) -> None:
    """Record the person's answers at a checkpoint."""
    entry, sha = ops.record_input(checkpoint, answers, questions=question or None, via=via)  # type: ignore[arg-type]
    emit(entry, commit_sha=sha, human=lambda: console.print(
        f"[green]recorded[/green] {checkpoint} [cyan]{entry.id}[/cyan] · commit [cyan]{sha[:10]}[/cyan]"))


@app.command("skip")
@handle_cli_errors
def skip(
    checkpoint: str = typer.Argument(..., help="framing | structure | values | surprise | audience"),
    reason: str = typer.Option(..., "--reason", "-r", help="Why you're carrying on without the person."),
    via: str = typer.Option(None, "--via", help="Who decided to carry on, e.g. 'chat' (default: the agent)."),
) -> None:
    """Carry on past a checkpoint without the person; the report says so, and why."""
    entry, sha = ops.skip_checkpoint(checkpoint, reason, via=via)  # type: ignore[arg-type]
    emit(entry, commit_sha=sha, human=lambda: console.print(
        f"[yellow]skipped[/yellow] {checkpoint} [cyan]{entry.id}[/cyan] · commit [cyan]{sha[:10]}[/cyan]"))


@app.command("pace")
@handle_cli_errors
def pace(
    value: str = typer.Argument(..., help="just-build (the person asked you to carry on alone) | ask"),
) -> None:
    """Stop asking for the rest of the model (``just-build``), or start again (``ask``)."""
    chosen = {"just-build": "just_build", "just_build": "just_build", "ask": "ask"}.get(value)
    if chosen is None:
        raise ValueError("pace must be 'just-build' or 'ask'")
    log, sha = ops.set_pace(chosen)  # type: ignore[arg-type]
    emit({"pace": log.pace}, commit_sha=sha, human=lambda: console.print(
        f"[green]pace:[/green] {value} · commit [cyan]{sha[:10]}[/cyan]"))
