from __future__ import annotations

import typer
from rich.console import Console

from latris.cli._errors import handle_cli_errors
from latris.operations import attributes as ops

app = typer.Typer(help="Set attribute values on a target.", no_args_is_help=True)
console = Console()


@app.command("set")
@handle_cli_errors
def set_(
    target: str = typer.Argument(..., help="Node ID/label or edge ID."),
    attribute: str = typer.Argument(..., help="description | confidence"),
    value: str = typer.Argument(..., help="Attribute value."),
) -> None:
    """Upsert an attribute value on a target (node or edge).

    Maturity now lives on the parent entity/edge — see
    ``latris mature`` and docs/design/MATURITY_LADDER.md.
    """
    target_id, sha = ops.set_attribute(target, attribute, value)  # type: ignore[arg-type]
    console.print(f"[green]set[/green] {attribute} on [cyan]{target_id}[/cyan] · commit [cyan]{sha[:10]}[/cyan]")
