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

app = typer.Typer(
    help="Checks: `handover` (ready for a board?), `coherence` and `integrity`.", no_args_is_help=True
)
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
    model_type: str = typer.Option(
        None, "--model-type", "-m",
        help="Model type to check (default: every model type the model is).",
    ),
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


_SEVERITY_STYLE = {"error": "red", "warning": "yellow", "info": "dim"}


@app.command("integrity")
@handle_cli_errors
def integrity(
    show_info: bool = typer.Option(
        False, "--all", help="Also list history (challenges, findings, signoffs) about removed elements."
    ),
    fix: bool = typer.Option(
        False, "--fix", help="First remove rows about nodes/links that no longer exist (one commit; history kept)."
    ),
) -> None:
    """Does every reference between the project's files resolve?

    Errors: a link to a missing node, a row about a missing node or link, a
    citation of a source not in the library, a dataset that isn't
    registered, two nodes with one label, duplicate links, malformed IDs.
    Warnings: a source_id that doesn't match its origin or doesn't resolve,
    an over-long stored extract. Exits 1 if there are errors.
    """
    from dataclasses import asdict

    from latris.operations.integrity import check_integrity, remove_dangling_rows

    if fix:
        removed, sha = remove_dangling_rows()
        if removed and not json_mode():
            console.print(
                f"[green]removed[/green] {removed} row(s) about deleted nodes/links · commit [cyan]{sha[:10]}[/cyan]"
            )
    report = check_integrity()

    def human() -> None:
        shown = [p for p in report.problems if show_info or p.severity != "info"]
        hidden = len(report.problems) - len(shown)
        if not shown:
            console.print("[green]Every reference resolves.[/green]")
        for p in shown:
            style = _SEVERITY_STYLE[p.severity]
            console.print(f"[{style}]{p.severity}[/{style}] {p.where}: {p.message}", highlight=False)
            if p.ids and p.severity != "info":
                console.print(f"   [dim]{', '.join(p.ids[:5])}{' …' if len(p.ids) > 5 else ''}[/dim]")
        if hidden:
            console.print(f"[dim]{hidden} note(s) about history on removed elements — `--all` lists them.[/dim]")

    emit({"ok": report.ok, "problems": [asdict(p) for p in report.problems]}, human=human)
    if not report.ok:
        raise typer.Exit(code=1)
