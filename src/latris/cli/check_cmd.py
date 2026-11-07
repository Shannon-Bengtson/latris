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
from latris.cli._output import emit, json_mode

app = typer.Typer(help="Checks: `handover` (ready for a board?) and `coherence`.", no_args_is_help=True)
console = Console()


@app.command("coherence")
@handle_cli_errors
def coherence() -> None:
    """Flag edges where the description and polarity tell opposite causal stories."""
    from latris.operations.analysis import run_coherence_check

    findings = run_coherence_check()

    if json_mode():
        emit(findings, human=lambda: None)
        if any(f.severity == "likely" for f in findings):
            raise typer.Exit(code=1)
        return

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


@app.command("handover")
@handle_cli_errors
def handover(
    model_type: str = typer.Option(None, "--model-type", "-m", help="Model type to check (default: the first chosen)."),
) -> None:
    """Is the model ready to hand to a board? Lists what's left, and how to fix each.

    Checks: links with no source, citations nobody has checked against their
    source, findings waiting for approval, report sections without prose, and
    descriptions that contradict their link's polarity. Exits 1 if anything
    is left.
    """
    from dataclasses import asdict

    from latris.operations.handover import handover_check

    report = handover_check(model_type=model_type)

    def human() -> None:
        if report.ready:
            console.print("[green]Ready to hand over:[/green] every link sourced, every citation checked, "
                          "findings approved, every section written.")
            return
        n = len(report.items)
        console.print(f"[bold]Ready to hand over: no[/bold] — {n} thing{'s' if n != 1 else ''} to do\n")
        for i, item in enumerate(report.items, 1):
            console.print(f"[yellow]{i}.[/yellow] {item.message}", highlight=False)
            for ex in item.examples:
                console.print(f"     · {ex}", markup=False, highlight=False)
            if item.count > len(item.examples) and item.examples:
                console.print(f"     · … and {item.count - len(item.examples)} more", highlight=False)
            console.print(f"   [dim]fix: {item.fix}[/dim]\n", highlight=False)

    emit(asdict(report), human=human)
    if not report.ready:
        raise typer.Exit(code=1)
