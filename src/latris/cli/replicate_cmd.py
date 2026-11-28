"""``latris replicate`` — textbook models rebuilt in Latris, checked against their known results."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from latris.cli._errors import handle_cli_errors
from latris.cli._output import emit, json_mode
from latris.operations import replications as ops

console = Console()

app = typer.Typer(
    help="Textbook models rebuilt in Latris, checked against the results they are known to give.",
    no_args_is_help=True,
)

# Where each command sits in the workflow (schema/workflow.py; rules in docs/engineering/WORKFLOW_STRUCTURE.md).
PLACE = "project"


def _value(value: object) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, list):
        return "; ".join("{" + ", ".join(s) + "}" for s in value)
    return str(value)


@app.command("list")
@handle_cli_errors
def list_cmd() -> None:
    """List the replications that ship with Latris. Works outside a project."""
    reps = ops.list_replications()

    def human() -> None:
        table = Table(title="Replications")
        table.add_column("ID")
        table.add_column("Model type")
        table.add_column("Title")
        table.add_column("Checks", justify="right")
        for r in reps:
            table.add_row(r.id, r.model_type, r.title, str(len(r.checks)))
        console.print(table)
        console.print(
            "Run them with `latris replicate check`; rebuild one with `latris replicate build <id> <folder>`.",
            markup=False,
            highlight=False,
        )

    emit(reps, human=human)


@app.command("check")
@handle_cli_errors
def check_cmd(
    ids: list[str] = typer.Argument(None, help="Replications to check (default: all)."),
    keep: Path = typer.Option(
        None, "--keep", help="Build into this folder (one project per replication) and keep the projects."
    ),
) -> None:
    """Build each replication, run its analyses and compare every result with its expected value.

    Exits 1 if any check fails. Works outside a project; builds commit to git, so a git identity must be set.
    """
    names = ids or [r.id for r in ops.list_replications()]
    reports = [ops.check_replication(n, root=(keep / n) if keep else None) for n in names]

    def human() -> None:
        for rep in reports:
            mark = "[green]PASS[/green]" if rep.passed else "[red]FAIL[/red]"
            table = Table(title=f"{rep.title} ({rep.id}, {rep.model_type})", title_justify="left")
            table.add_column("Check")
            table.add_column("Expected", justify="right")
            table.add_column("Latris", justify="right")
            table.add_column("Basis")
            table.add_column("")
            for o in rep.outcomes:
                table.add_row(
                    o.claim, _value(o.expected), _value(o.actual), o.basis, "ok" if o.passed else "[red]differs[/red]"
                )
            console.print(table)
            console.print(f"{mark}  {rep.source}", highlight=False)
            if rep.root:
                console.print(f"Built at {rep.root}", markup=False, highlight=False)
            console.print()
        passed = sum(r.passed for r in reports)
        console.print(f"{passed} of {len(reports)} replications reproduce their expected results.", highlight=False)

    emit(reports, human=human)
    if not all(r.passed for r in reports):
        raise typer.Exit(code=1)


@app.command("build")
@handle_cli_errors
def build_cmd(
    rep_id: str = typer.Argument(..., help="The replication to build (see `latris replicate list`)."),
    folder: Path = typer.Argument(..., help="A new or empty folder for the project."),
) -> None:
    """Build a replication as a project of your own, analyses run, to inspect, report on or change."""
    ops.build_replication(rep_id, folder)
    rep = ops.get_replication(rep_id)
    if json_mode():
        emit({"id": rep.id, "root": str(folder)}, human=lambda: None)
        return
    console.print(f"[green]built[/green] {rep.title} at {folder}", highlight=False)
    console.print(
        f"Next: cd {folder} && latris results list, or latris export md for the report.",
        markup=False,
        highlight=False,
    )
