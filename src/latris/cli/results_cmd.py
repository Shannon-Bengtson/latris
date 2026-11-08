"""Recorded results — what reports show from simulations, queries and sensitivity runs."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from latris.cli._errors import handle_cli_errors
from latris.cli._output import emit, json_mode

app = typer.Typer(
    help="Recorded analysis results (simulations, scenarios, Monte Carlo, BN queries) and which ones reports show.",
    no_args_is_help=True,
)
console = Console()


def _row(run, hidden: bool, stale: bool, shown: set[str]) -> dict:
    return {
        "run_id": run.id, "kind": run.result_kind, "summary": run.output_summary,
        "date": run.id and _date(run.id), "in_reports": run.id in shown, "hidden": hidden, "out_of_date": stale,
    }


def _date(run_id: str) -> str:
    from latris.schema import id_timestamp

    try:
        return id_timestamp(run_id).isoformat(timespec="seconds")
    except Exception:
        return ""


@app.command("list")
@handle_cli_errors
def list_results(
    all_results: bool = typer.Option(False, "--all", help="Include results reports don't show (older or hidden)."),
) -> None:
    """Results reports show: the latest run of each analysis (--all for every recorded result)."""
    from latris.operations import analysis_results as ar

    shown = {r.run.id for r in ar.report_results()}
    rows = [_row(run, hidden, stale, shown) for run, hidden, stale in ar.list_results()]
    if not all_results:
        rows = [r for r in rows if r["in_reports"]]
    if json_mode():
        emit(rows, human=lambda: None)
        return
    if not rows:
        console.print("No recorded results yet. `sd simulate`, `bn query` and the sensitivity commands record them.")
        return
    table = Table(show_header=True, header_style="bold")
    for col in ("Run", "Kind", "Date", "Status", "Summary"):
        table.add_column(col)
    for r in rows:
        status = "hidden" if r["hidden"] else "in reports" if r["in_reports"] else "superseded"
        if r["out_of_date"]:
            status += ", [yellow]out of date[/yellow]"
        table.add_row(r["run_id"].split("_", 1)[-1][:10], r["kind"], r["date"], status, escape(r["summary"][:140]))
    console.print(table)


@app.command("show")
@handle_cli_errors
def show(run: str = typer.Argument(..., help="Run ID or a prefix of it.")) -> None:
    """Show one recorded result in full."""
    import json

    from latris.operations import analysis_results as ar

    record, payload = ar.get_result(run)
    if json_mode():
        emit({"run": record.model_dump(mode="json"), "result": payload}, human=lambda: None)
        return
    console.print(f"[bold]{record.result_kind}[/bold] · {record.id}\n{escape(record.output_summary)}\n")
    console.print(escape(json.dumps(payload, indent=1)[:20000]))


def _set_hidden(run: str, hidden: bool) -> None:
    from latris.operations import analysis_results as ar

    record, sha = ar.set_hidden(run, hidden)
    if json_mode():
        emit({"run_id": record.id, "hidden": hidden}, human=lambda: None, commit_sha=sha)
        return
    verb = "hidden from reports" if hidden else "shown in reports"
    tail = f" · commit [cyan]{sha[:10]}[/cyan]" if sha else " (no change)"
    console.print(f"[green]{verb}[/green] {record.result_kind} {record.id.split('_', 1)[-1][:10]}{tail}")


@app.command("hide")
@handle_cli_errors
def hide(run: str = typer.Argument(..., help="Run ID or a prefix of it.")) -> None:
    """Leave a result out of reports (it stays in the run log)."""
    _set_hidden(run, True)


@app.command("unhide")
@handle_cli_errors
def unhide(run: str = typer.Argument(..., help="Run ID or a prefix of it.")) -> None:
    """Show a hidden result in reports again."""
    _set_hidden(run, False)
