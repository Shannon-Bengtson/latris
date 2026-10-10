"""CLI for AI interrogation Phase 2c CompletenessGate."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from latris.cli._errors import handle_cli_errors
from latris.operations import completeness as ops

app = typer.Typer(
    help="Run the AI completeness gate and manage missing-variable records.",
    no_args_is_help=True,
)
console = Console()


_SEVERITY_COLOR = {"required": "red", "recommended": "yellow", "optional": "dim"}
_DISPOSITION_COLOR = {
    "open": "yellow",
    "added_to_model": "green",
    "excluded": "dim",
    "dismissed": "dim",
}


def _print_report(report) -> None:
    if not report.entries:
        console.print(f"[dim](no missing-variable records for {report.model_type})[/dim]")
        return
    table = Table(show_header=True, header_style="bold")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Severity")
    table.add_column("Confidence")
    table.add_column("Disposition")
    for mv in report.entries:
        sev_color = _SEVERITY_COLOR.get(mv.severity, "white")
        disp_color = _DISPOSITION_COLOR.get(mv.disposition, "white")
        table.add_row(
            mv.id[:24] + "…",
            mv.name,
            f"[{sev_color}]{mv.severity}[/{sev_color}]",
            mv.confidence,
            f"[{disp_color}]{mv.disposition}[/{disp_color}]",
        )
    console.print(table)
    console.print(
        f"[dim]coverage_ratio={report.coverage_ratio:.2f} · "
        f"{len(report.entries)} entr{'y' if len(report.entries) == 1 else 'ies'}[/dim]"
    )


@app.command("check")
@handle_cli_errors
def check(
    model_type: str = typer.Argument("cld", help="Model type (cld, dag, fcm, …)."),
    claim: list[str] = typer.Option(
        None,
        "--claim",
        help="Claim string the gate should treat as required-for context. Repeat.",
    ),
) -> None:
    """Run the AI completeness gate for a model type."""
    report, _ = ops.run_completeness_gate(model_type, claims=claim or [])
    _print_report(report)


@app.command("list")
@handle_cli_errors
def list_(
    model_type: str = typer.Argument("cld", help="Model type to list records for."),
    disposition: str = typer.Option(
        None,
        "--disposition",
        help="Filter by disposition: open, added_to_model, excluded, dismissed.",
    ),
) -> None:
    """List missing-variable records for a model type."""
    if disposition is not None:
        entries = ops.list_missing_variables(model_type, disposition_filter=disposition)
    else:
        report = ops.load_report(model_type)
        entries = report.entries
    if not entries:
        console.print("[dim](no records match)[/dim]")
        return
    table = Table(show_header=True, header_style="bold")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Severity")
    table.add_column("Disposition")
    for mv in entries:
        table.add_row(mv.id[:24] + "…", mv.name, mv.severity, mv.disposition)
    console.print(table)


@app.command("override")
@handle_cli_errors
def override(
    model_type: str = typer.Argument(..., help="Model type."),
    missing_var_id: str = typer.Argument(..., help="MissingVariable id."),
    rationale: str = typer.Option(..., "--rationale", help="Why this variable is excluded."),
) -> None:
    """Override a missing-variable record by creating a linked Exclusion."""
    mv, sha = ops.override_missing_variable(model_type, missing_var_id, rationale)
    console.print(
        f"[green]overrode[/green] [bold]{mv.name}[/bold] "
        f"(linked Exclusion {mv.excluded_via_id}) · commit [cyan]{sha[:10]}[/cyan]"
    )


@app.command("dismiss")
@handle_cli_errors
def dismiss(
    model_type: str = typer.Argument(..., help="Model type."),
    missing_var_id: str = typer.Argument(..., help="MissingVariable id."),
) -> None:
    """Dismiss a missing-variable record without creating an Exclusion."""
    mv, sha = ops.dismiss_missing_variable(model_type, missing_var_id)
    console.print(
        f"[green]dismissed[/green] [bold]{mv.name}[/bold] · commit [cyan]{sha[:10]}[/cyan]"
    )


@app.command("mark-added")
@handle_cli_errors
def mark_added(
    model_type: str = typer.Argument(..., help="Model type."),
    missing_var_id: str = typer.Argument(..., help="MissingVariable id."),
    entity_id: str = typer.Option(..., "--entity-id", help="Entity that resolves the gap."),
) -> None:
    """Mark a missing-variable record as added-to-model."""
    mv, sha = ops.mark_added_to_model(model_type, missing_var_id, entity_id)
    console.print(
        f"[green]marked added[/green] [bold]{mv.name}[/bold] (entity {entity_id}) "
        f"· commit [cyan]{sha[:10]}[/cyan]"
    )
