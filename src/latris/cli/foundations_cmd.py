"""``latris foundations`` — the methods-and-foundations registry."""

from __future__ import annotations

import json
from dataclasses import asdict

import typer
from rich.console import Console
from rich.table import Table

from latris.cli._errors import handle_cli_errors
from latris.cli._output import json_mode
from latris.operations.foundations import FOUNDATIONS

console = Console()


@handle_cli_errors
def foundations(
    json_output: bool = typer.Option(
        False, "--json", help="Emit the registry as JSON (for agents/scripts)."
    ),
) -> None:
    """Show the established methods Latris implements, with sources and stated limits.

    Registry-only — works outside a project directory. The same registry
    generates the report's Methods and foundations section and the capability
    manifest's ``foundations`` block, so the three cannot drift apart.
    ``latris docs foundations`` prints the prose companion.
    """
    if json_output or json_mode():
        # typer.echo, not console.print: rich would word-wrap long JSON
        # lines (sometimes inside string literals) — same reasoning as
        # capabilities_cmd.py.
        typer.echo(json.dumps([asdict(f) for f in FOUNDATIONS], indent=2, ensure_ascii=False))
        return

    table = Table(title="Methods and foundations")
    table.add_column("ID")
    table.add_column("Method")
    table.add_column("Citation")
    for f in FOUNDATIONS:
        table.add_row(f.id, f.method, f.citation)
    console.print(table)
    console.print(
        "\nThe report's Methods and foundations section and `latris capabilities` "
        "are generated from this same registry.",
        markup=False,
        highlight=False,
    )
