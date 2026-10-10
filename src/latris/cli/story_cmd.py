"""Story (Communicate phase) CLI — draft, prose, emphasis, export.

Mirrors ``server/routes/story.py`` so the scrollytelling artifact can be
produced from a script: draft the deterministic beat skeleton, generate
public-register prose per beat, then export self-contained HTML.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from latris.cli._errors import handle_cli_errors

app = typer.Typer(
    help="Story: self-contained scrollytelling HTML for non-technical audiences.",
    no_args_is_help=True,
)
console = Console()

_DEFAULT_SECTIONS = ["key_findings", "answer_to_question", "open_questions", "implications"]


@app.command("draft")
@handle_cli_errors
def draft(
    model: str = typer.Option(..., "--model", "-m", help="Model type to narrate (e.g. cld)."),
    sections: str = typer.Option(
        "", "--sections", help="Comma-separated Interpret sections to feature. Defaults to the stakeholder set."
    ),
) -> None:
    """Build the deterministic beat skeleton for a model type's story."""
    from latris.operations.story import draft_story
    from latris.schema.story import StoryGenerationRequest

    picked = [s.strip() for s in sections.split(",") if s.strip()] or list(_DEFAULT_SECTIONS)
    doc, sha = draft_story(model, StoryGenerationRequest(include_sections=picked))
    console.print(
        f"[green]drafted[/green] story for [cyan]{model}[/cyan] · {len(doc.beats)} beats · commit [cyan]{sha[:10]}[/cyan]"  # noqa: E501
    )
    for b in doc.beats:
        console.print(f"  · [cyan]{b.id[:20]}[/cyan]  {b.kind}  “{b.title}”")


@app.command("list")
@handle_cli_errors
def list_stories() -> None:
    """List stories (one per model type)."""
    from latris.operations.story import load_story

    store = load_story()
    if not store.docs:
        console.print("[dim](no stories — run `story draft --model <type>`)[/dim]")
        return
    for d in store.docs:
        console.print(
            f"[cyan]{d.model_type}[/cyan]  “{d.title}”  beats={len(d.beats)}  state=[bold]{d.generation_state}[/bold]"
        )


@app.command("show")
@handle_cli_errors
def show(model: str = typer.Option(..., "--model", "-m")) -> None:
    """Show a story's beats with their prose length and emphasis."""
    from latris.operations.story import load_story

    store = load_story()
    doc = next((d for d in store.docs if d.model_type == model), None)
    if doc is None:
        console.print(f"[yellow]no story for {model} — run `story draft` first[/yellow]")
        raise typer.Exit(1)
    console.print(f"[bold]{doc.title}[/bold] — {doc.standfirst}")
    for b in doc.beats:
        emph = f"{len(b.emphasis.node_ids)}n/{len(b.emphasis.edge_ids)}e"
        console.print(
            f"  · [cyan]{b.id[:20]}[/cyan] {b.kind} “{b.title}” prose={len(b.prose)}c emphasis={emph}"
        )


@app.command("generate-prose")
@handle_cli_errors
def generate_prose(
    beat: str = typer.Argument(..., help="Beat ID (prefix ok)."),
    model: str = typer.Option(..., "--model", "-m"),
) -> None:
    """Generate public-register prose for one beat."""
    from latris.operations.story import generate_beat_prose

    b, sha = generate_beat_prose(model, beat)
    console.print(f"[green]generated[/green] {b.kind} · prose={len(b.prose)}c · commit [cyan]{sha[:10]}[/cyan]")


@app.command("generate-all")
@handle_cli_errors
def generate_all(model: str = typer.Option(..., "--model", "-m")) -> None:
    """Generate prose for every beat of a story."""
    from latris.operations.story import generate_beat_prose, load_story

    store = load_story()
    doc = next((d for d in store.docs if d.model_type == model), None)
    if doc is None:
        console.print(f"[yellow]no story for {model} — run `story draft` first[/yellow]")
        raise typer.Exit(1)
    for b in list(doc.beats):
        nb, _ = generate_beat_prose(model, b.id)
        console.print(f"  · {nb.kind}: ok ({len(nb.prose)}c)")
    console.print("[green]done[/green]")


@app.command("set-prose")
@handle_cli_errors
def set_prose(
    beat: str = typer.Argument(..., help="Beat ID (prefix ok)."),
    text: str = typer.Argument(..., help="Prose text."),
    model: str = typer.Option(..., "--model", "-m"),
) -> None:
    """Set a beat's prose (a human edit, versioned)."""
    from latris.operations.story import set_beat_prose

    b, sha = set_beat_prose(model, beat, text)
    console.print(f"[green]updated[/green] {b.kind} · commit [cyan]{sha[:10]}[/cyan]")


@app.command("export")
@handle_cli_errors
def export(
    model: str = typer.Option(..., "--model", "-m"),
    output: Path = typer.Option(None, "--output", "-o", help="Output HTML path. Omit to print to stdout."),
    theme: str = typer.Option(None, "--theme", help="Theme name (default: the story's theme)."),
) -> None:
    """Render the story to a self-contained HTML file."""
    from latris.exporters import story_html
    from latris.repo.project import require_project

    paths = require_project()
    html = story_html.render(paths, model, theme=theme)
    if output is None:
        typer.echo(html)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8", newline="")
    console.print(f"[green]exported[/green] → [cyan]{output}[/cyan] ({len(html)} bytes)")
