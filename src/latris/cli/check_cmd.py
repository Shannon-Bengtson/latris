"""Coherence-check CLI commands.

Surfaces cross-store contradictions a partner reviewer would catch on
the second read of the report — e.g. an edge whose substrate description
and CLD polarity rationale tell opposite causal stories.
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from latris.cli._errors import handle_cli_errors

app = typer.Typer(help="Cross-store coherence checks.", no_args_is_help=True)
console = Console()


@app.command("coherence")
@handle_cli_errors
def coherence() -> None:
    """Flag edges where the description and polarity tell opposite causal stories."""
    from latris.operations.analysis import run_coherence_check

    findings = run_coherence_check()

    if not findings:
        console.print("[green]No polarity ↔ description contradictions found.[/green]")
        return

    table = Table(show_header=True, header_style="bold", title="Coherence findings")
    table.add_column("#", style="dim")
    table.add_column("Severity")
    table.add_column("Edge ID")
    table.add_column("Polarity")
    table.add_column("Reason")
    for i, f in enumerate(findings, 1):
        sev_style = "red" if f.severity == "likely" else "yellow"
        table.add_row(
            str(i),
            f"[{sev_style}]{f.severity}[/{sev_style}]",
            f.target_id[:18] + ("…" if len(f.target_id) > 18 else ""),
            f.polarity,
            f.reason,
        )
    console.print(table)
    console.print(f"\n{len(findings)} finding(s).")
    likely = sum(1 for f in findings if f.severity == "likely")
    if likely:
        raise typer.Exit(code=1)
