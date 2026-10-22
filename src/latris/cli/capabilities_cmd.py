"""``latris capabilities`` — agent-facing capability manifest."""

from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.table import Table

from latris.cli._errors import handle_cli_errors
from latris.operations.capabilities import build_capability_manifest

console = Console()


@handle_cli_errors
def capabilities(
    json_output: bool = typer.Option(
        False, "--json", help="Emit the manifest as JSON (for agents/scripts)."
    ),
) -> None:
    """Show what Latris can actually do today vs. planned or excluded.

    Registry-only — works outside a project directory. Check this (or
    ``--json``) before recommending a specific model type for a job: only
    types with ``can_use_today: true`` are switchable via ``latris view
    project``/``auto-project`` today; switching to a planned type raises.
    """
    manifest = build_capability_manifest()

    if json_output:
        # typer.echo, not console.print: rich would word-wrap long JSON
        # lines (sometimes inside string literals) and interpret [...]
        # sequences — same reasoning as ai_cmd.py's task_emit.
        typer.echo(json.dumps(manifest, indent=2, ensure_ascii=False))
        return

    table = Table(title="Latris model-type capabilities")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Status")
    table.add_column("Description")
    for mt in manifest["model_types"]:
        status = (
            "[green]available[/green]" if mt["can_use_today"] else "[yellow]planned[/yellow]"
        )
        table.add_row(mt["id"], mt["display_name"], status, mt["description"])
    console.print(table)

    console.print("\n[bold]Excluded by design[/bold] (not planned — won't be added):")
    for ex in manifest["excluded_by_design"]:
        console.print(f"  - {ex['category']} ({', '.join(ex['examples'])}): {ex['reason']}")
