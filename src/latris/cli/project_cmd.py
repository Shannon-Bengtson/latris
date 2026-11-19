from __future__ import annotations

import typer
from rich.console import Console

from latris.cli._errors import handle_cli_errors
from latris.cli._output import emit, json_mode
from latris.operations.project import (
    load_foundation,
    set_foundation_field,
    set_question,
    update_selected_models,
)
from latris.repo import git
from latris.repo.git import GitError

app = typer.Typer(help="Inspect and update the project foundation.", no_args_is_help=True)
console = Console()


@app.command("show")
@handle_cli_errors
def show() -> None:
    """Print the current project foundation."""
    paths, foundation = load_foundation()

    if json_mode():
        emit(foundation, human=lambda: None)
        return
    console.print(f"[bold]project root:[/bold] {paths.root.as_posix()}")
    console.print(f"[bold]modelling question:[/bold] {foundation.statement}")
    models = ", ".join(foundation.selected_model_types) if foundation.selected_model_types else "(none)"
    console.print(f"[bold]selected models:[/bold] {models}")
    console.print(f"[bold]schema version:[/bold] {foundation.schema_version}")
    try:
        head = git.head_sha(paths.root)
        first_sha = git.run_git(
            ["rev-list", "--max-parents=0", "HEAD"], cwd=paths.root
        ).stdout.strip().splitlines()[0]
        console.print(f"[bold]created:[/bold] {git.commit_timestamp(first_sha, paths.root).isoformat()}")
        console.print(f"[bold]updated:[/bold] {git.commit_timestamp(head, paths.root).isoformat()}")
    except (GitError, IndexError):
        pass


@app.command("set-question")
@handle_cli_errors
def set_question_cmd(
    statement: str = typer.Argument(..., help="The modelling question to record."),
) -> None:
    """Set or update the project's modelling question and commit."""
    root, sha = set_question(None, statement)
    console.print(f"[green]updated[/green] question ([cyan]{sha[:10]}[/cyan])")


@app.command("set")
@handle_cli_errors
def set_field_cmd(
    field: str = typer.Argument(
        ...,
        help=(
            "Field to set: name | background | boundary | exclusions | predictions "
            "| coverage_dimensions | granularity_level | audience."
        ),
    ),
    value: str = typer.Argument(..., help="New value for the field."),
) -> None:
    """Set a free-text foundation field. Use `set-question` for the question itself."""
    root, sha = set_foundation_field(field, value)
    console.print(f"[green]set[/green] {field} ([cyan]{sha[:10]}[/cyan])")


@app.command("select-models")
@handle_cli_errors
def select_models_cmd(
    model_types: list[str] = typer.Argument(..., help="Model type IDs to select (e.g. cld dag)."),
) -> None:
    """Set the project's selected model types."""
    root, sha = update_selected_models(model_types)
    label = ", ".join(model_types) or "(none)"
    console.print(f"[green]selected[/green] model types: {label} ([cyan]{sha[:10]}[/cyan])")


@app.command("choose")
@handle_cli_errors
def choose_cmd(
    model_type: str = typer.Argument(..., help="Model type ID (e.g. sd)."),
    why: str = typer.Option(
        ..., "--why", help="Why this model type suits the question (the report's Modelling Approach)."
    ),
) -> None:
    """Choose a model type and record why (or record a new reason for one already chosen)."""
    from latris.operations.project import add_model_choice

    _root, sha = add_model_choice(model_type, why)
    console.print(f"[green]chose[/green] {model_type}: {why} ([cyan]{sha[:10]}[/cyan])", highlight=False)
