from __future__ import annotations

import typer
from rich.console import Console

from latris.operations.project import (
    load_foundation,
    set_foundation_field,
    set_question,
    update_selected_models,
)
from latris.repo import git
from latris.repo.git import GitError, IdentityError
from latris.repo.project import NotAProjectError

app = typer.Typer(help="Inspect and update the project foundation.", no_args_is_help=True)
console = Console()


@app.command("show")
def show() -> None:
    """Print the current project foundation."""
    try:
        paths, foundation = load_foundation()
    except NotAProjectError as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

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
def set_question_cmd(
    statement: str = typer.Argument(..., help="The modelling question to record."),
) -> None:
    """Set or update the project's modelling question and commit."""
    try:
        root, sha = set_question(None, statement)
    except NotAProjectError as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except IdentityError as exc:
        console.print(f"[red]identity error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except GitError as exc:
        console.print(f"[red]git error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(f"[green]updated[/green] question ([cyan]{sha[:10]}[/cyan])")


@app.command("set")
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
    try:
        root, sha = set_foundation_field(field, value)
    except ValueError as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=2) from exc
    except NotAProjectError as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except IdentityError as exc:
        console.print(f"[red]identity error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except GitError as exc:
        console.print(f"[red]git error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(f"[green]set[/green] {field} ([cyan]{sha[:10]}[/cyan])")


@app.command("select-models")
def select_models_cmd(
    model_types: list[str] = typer.Argument(..., help="Model type IDs to select (e.g. cld dag)."),
) -> None:
    """Set the project's selected model types."""
    try:
        root, sha = update_selected_models(model_types)
    except NotAProjectError as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except ValueError as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except IdentityError as exc:
        console.print(f"[red]identity error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except GitError as exc:
        console.print(f"[red]git error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    label = ", ".join(model_types) or "(none)"
    console.print(f"[green]selected[/green] model types: {label} ([cyan]{sha[:10]}[/cyan])")
