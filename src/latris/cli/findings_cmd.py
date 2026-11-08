"""Findings CLI — add, list, show, advance maturity, check-stale."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from latris.cli._errors import handle_cli_errors
from latris.cli._output import emit, json_mode
from latris.schema.ids import id_timestamp

app = typer.Typer(help="Model findings — analysis results and interpretations.", no_args_is_help=True)
console = Console()

_MATURITY_STYLE = {
    "proposed": "yellow",
    "reviewed": "blue",
    "approved": "green",
}


@app.command("add")
@handle_cli_errors
def add_cmd(
    statement: str = typer.Argument(..., help="The finding, in one sentence."),
    category: str = typer.Option(
        "structure",
        "--category",
        "-c",
        help="structure | dynamics | sensitivity | inference | diagnostics | recommendations",
    ),
    model_type: str = typer.Option("cld", "--model-type", "-m", help="Model type the finding is about."),
    detail: str = typer.Option("", "--detail", help="Supporting detail or reasoning."),
    target: list[str] = typer.Option(
        None, "--target", "-t", help="Node or edge the finding concerns (ID, or a node label). Repeatable."
    ),
) -> None:
    """Record a finding by hand — e.g. what a loop analysis showed.

    Findings appear in the report's findings section.
    """
    from latris.operations._resolve import resolve_target
    from latris.operations.findings import record_new_finding
    from latris.repo.project import require_project
    from latris.repo.yaml_io import load_model
    from latris.schema import Substrate
    from latris.schema.findings import FINDING_CATEGORIES

    if category not in FINDING_CATEGORIES:
        raise ValueError(f"category must be one of: {', '.join(FINDING_CATEGORIES)}")
    target_ids = None
    if target:
        substrate = load_model(Substrate, require_project().conceptual_yaml)
        target_ids = [resolve_target(t, substrate) for t in target]
    finding, sha = record_new_finding(
        statement, category, model_type, detail=detail, target_ids=target_ids  # type: ignore[arg-type]
    )
    emit(
        finding,
        commit_sha=sha,
        human=lambda: console.print(
            f"[green]recorded[/green] {finding.category} finding [cyan]{finding.id}[/cyan] "
            f"· commit [cyan]{sha[:10]}[/cyan]"
        ),
    )


@app.command("list")
@handle_cli_errors
def list_cmd(
    category: str | None = typer.Option(None, "--category", "-c", help="Filter by category."),
    model_type: str | None = typer.Option(None, "--model-type", "-m", help="Filter by model type."),
    maturity: str | None = typer.Option(
        None,
        "--maturity",
        help="Filter by maturity (proposed/reviewed/approved).",
    ),
    target_id: str | None = typer.Option(None, "--target", "-t", help="Filter by target entity/edge ID."),
    limit: int | None = typer.Option(None, "--limit", "-n", help="Maximum number of findings to show."),
) -> None:
    """List findings with optional filters (newest first)."""
    from latris.operations.findings import list_findings

    results = list_findings(
        category=category,
        model_type=model_type,
        maturity=maturity,
        target_id=target_id,
        limit=limit,
    )

    if json_mode():
        emit(results, human=lambda: None)
        return
    if not results:
        console.print("[dim](no findings match the filters)[/dim]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("ID", style="dim", max_width=20)
    table.add_column("Category")
    table.add_column("Model")
    table.add_column("Maturity")
    table.add_column("Statement", max_width=60)

    for f in results:
        style = _MATURITY_STYLE.get(f.maturity, "")
        table.add_row(
            f.id[:20] + "…",
            f.category,
            f.model_type,
            f"[{style}]{f.maturity}[/{style}]",
            f.statement[:60] + ("…" if len(f.statement) > 60 else ""),
        )

    console.print(table)
    console.print(f"\n{len(results)} finding(s).")


@app.command("show")
@handle_cli_errors
def show_cmd(
    query: str = typer.Argument(..., help="Finding ID or prefix."),
) -> None:
    """Show a single finding in detail."""
    from latris.operations.findings import get_finding

    f = get_finding(query)
    style = _MATURITY_STYLE.get(f.maturity, "")

    console.print(f"[bold]ID:[/bold]        {f.id}")
    console.print(f"[bold]Category:[/bold]  {f.category}")
    console.print(f"[bold]Model:[/bold]     {f.model_type}")
    console.print(f"[bold]Maturity:[/bold]  [{style}]{f.maturity}[/{style}]")
    console.print(f"[bold]Origin:[/bold]    {f.origin}")
    console.print(f"[bold]Created:[/bold]   {id_timestamp(f.id).isoformat()}")
    if f.reviewed_by:
        console.print(f"[bold]Reviewed:[/bold]  {f.reviewed_by.name} ({f.reviewed_at})")
    if f.supersedes:
        console.print(f"[bold]Supersedes:[/bold] {', '.join(f.supersedes)}")
    console.print()
    console.print(f"[bold]Statement:[/bold] {f.statement}")
    if f.detail:
        console.print(f"\n[bold]Detail:[/bold]\n{f.detail}")
    if f.target_ids:
        console.print(f"\n[bold]Targets:[/bold]  {', '.join(f.target_ids[:10])}")
    if f.payload:
        console.print(f"\n[bold]Payload keys:[/bold] {', '.join(f.payload.keys())}")


@app.command("check-stale")
@handle_cli_errors
def check_stale_cmd() -> None:
    """Check all active (proposed or reviewed) findings for staleness."""
    from latris.operations.findings import check_staleness, list_findings

    active = list_findings(maturity="proposed") + list_findings(maturity="reviewed")
    if not active:
        console.print("[dim](no active findings)[/dim]")
        return

    stale = []
    for f in active:
        if check_staleness(f):
            stale.append(f)

    if not stale:
        console.print(f"[green]All {len(active)} active finding(s) are current.[/green]")
        return

    console.print(f"[yellow]{len(stale)} finding(s) may be stale:[/yellow]\n")
    for f in stale:
        console.print(f"  • [{f.maturity}] {f.statement[:60]}…  ({f.id[:20]}…)")
    console.print("\nUse [bold]mature <id>[/bold] to advance findings, or `git rm` the finding to retract it.")
