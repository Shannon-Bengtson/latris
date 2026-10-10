from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from latris.operations.init import ProjectAlreadyExistsError, init_project
from latris.repo.git import GitError, IdentityError

console = Console()


def init(
    name: str = typer.Argument(..., help="Project directory to create (relative or absolute)."),
    question: str = typer.Option(
        ...,
        "--question",
        "-q",
        help="Modelling question this project is organised around.",
    ),
    project_name: str = typer.Option(
        "",
        "--name",
        help="Display name for the project. Defaults to the directory basename.",
    ),
) -> None:
    """Scaffold a new latris project and initialise git."""
    root = Path(name).resolve() if Path(name).is_absolute() else (Path.cwd() / name).resolve()
    display_name = project_name or root.name

    try:
        paths = init_project(
            root,
            statement=question,
            name=display_name,
        )
    except IdentityError as exc:
        console.print(f"[red]identity error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except ProjectAlreadyExistsError as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except GitError as exc:
        console.print(f"[red]git error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]initialised[/green] project at [bold]{paths.root.as_posix()}[/bold]")
