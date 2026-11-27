"""Data CLI — register a dataset and look at what's registered.

The app's data workspace has the full set of cleaning and reshaping
operations; these commands cover what an analysis needs from the command
line: bring a CSV/TSV in, and see its columns.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from latris.cli._errors import handle_cli_errors
from latris.cli._output import emit, json_mode

app = typer.Typer(help="Datasets: register a CSV/TSV and list what's registered.", no_args_is_help=True)

# Where each command sits in the workflow (schema/workflow.py; rules in docs/engineering/WORKFLOW_STRUCTURE.md).
PLACE = "data"
console = Console()


@app.command("add")
@handle_cli_errors
def add(
    file: Path = typer.Argument(..., help="A CSV or TSV file (copied into the project's data/files)."),
    name: str = typer.Option(None, "--name", help="Name to refer to it by; default: the file name."),
    description: str = typer.Option("", "--description"),
) -> None:
    """Register a dataset. Name columns like the factors they measure and analyses find them by name."""
    from latris.operations import datasets as data_ops

    ds, sha = data_ops.upload_dataset(file, name=name, description=description)
    if json_mode():
        emit(ds, human=lambda: None, commit_sha=sha)
        return
    console.print(f"[green]added[/green] dataset {escape(ds.name)}: {ds.rows} rows, {len(ds.columns)} columns · "
                  f"commit [cyan]{sha[:10]}[/cyan]")


@app.command("list")
@handle_cli_errors
def list_cmd() -> None:
    """List registered datasets."""
    from latris.operations import datasets as data_ops

    items = data_ops.list_datasets()

    def human() -> None:
        if not items:
            console.print("[dim](no datasets — `latris data add <file>`)[/dim]")
            return
        t = Table(show_header=True, header_style="bold")
        for col in ("Name", "Rows", "Columns", "File"):
            t.add_column(col)
        for d in items:
            t.add_row(escape(d.name), str(d.rows or "—"), str(len(d.columns)), escape(d.location))
        console.print(t)

    emit([d.model_dump(mode="json") for d in items], human=human)


@app.command("show")
@handle_cli_errors
def show(dataset: str = typer.Argument(..., help="Dataset name or id.")) -> None:
    """Show a dataset's columns and types."""
    from latris.operations import datasets as data_ops

    d = data_ops.get_dataset(dataset)

    def human() -> None:
        console.print(f"[bold]{escape(d.name)}[/bold] — {d.rows} rows · {escape(d.location)}")
        if d.description:
            console.print(escape(d.description))
        t = Table(show_header=True, header_style="bold")
        t.add_column("Column")
        t.add_column("Type")
        for c in d.columns:
            t.add_row(escape(c.name), escape(str(c.dtype)))
        console.print(t)

    emit(d.model_dump(mode="json"), human=human)
