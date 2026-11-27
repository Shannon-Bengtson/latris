"""FCM CLI commands — set weights, run inference, compare scenarios."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from latris.cli._errors import handle_cli_errors
from latris.cli._output import emit, json_mode

app = typer.Typer(help="Fuzzy Cognitive Map operations.", no_args_is_help=True)

# Where each command sits in the workflow (schema/workflow.py; rules in docs/engineering/WORKFLOW_STRUCTURE.md).
PLACE = {
    "set_weight": "formalise.values",
    "weights": "formalise.values",
    "infer": "analyse.base_case",
}
console = Console()


@app.command("set-weight")
@handle_cli_errors
def set_weight(
    edge: str = typer.Argument(..., help="Edge ID, ID prefix, or 'from→to' label."),
    value: str = typer.Argument(..., help="Weight value in [-1, +1]."),
) -> None:
    """Set the FCM weight on an edge."""
    from latris.operations import view_attributes as va

    target_id, sha = va.set_view_attribute(edge, "fcm", "weight", value)
    if json_mode():
        emit({"target_id": target_id, "weight": value}, human=lambda: None, commit_sha=sha)
        return
    console.print(f"[green]set[/green] FCM weight on {target_id[:15]}… = {value} · commit [cyan]{sha[:10]}[/cyan]")


@app.command("weights")
@handle_cli_errors
def weights() -> None:
    """List all FCM edge weights."""
    from latris.operations import edges as edge_ops
    from latris.operations import nodes as node_ops
    from latris.operations import view_attributes as va

    store = va.get_view_attributes("fcm", "weight")
    edges = edge_ops.list_edges()
    entities = node_ops.list_nodes()

    labels = {e.id: e.label for e in entities}
    weight_map = {e.target_id: e.value for e in store.entries}
    if json_mode():
        emit([
            {"link": f"{labels.get(e.from_id, e.from_id)} -> {labels.get(e.to_id, e.to_id)}", "id": e.id,
             "weight": weight_map.get(e.id)}
            for e in edges
        ], human=lambda: None)
        return

    if not edges:
        console.print("[dim](no edges)[/dim]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Edge")
    table.add_column("Weight")
    table.add_column("Edge maturity")
    for e in edges:
        from_label = labels.get(e.from_id, e.from_id[:10])
        to_label = labels.get(e.to_id, e.to_id[:10])
        w = weight_map.get(e.id)
        weight_str = f"{w:+.2f}" if w is not None else "[dim]—[/dim]"
        table.add_row(f"{from_label} → {to_label}", weight_str, e.maturity)
    console.print(table)


@app.command("infer")
@handle_cli_errors
def infer(
    clamp: list[str] | None = typer.Option(None, "--clamp", "-c", help="Clamp entity=value (e.g. 'Price=1.0')."),
    record: bool = typer.Option(True, "--record/--no-record", help="Save the result for reports + log a run."),
) -> None:
    """Run FCM inference to steady state (recorded for reports, one result per clamp scenario)."""
    from latris.operations.analysis import fcm_steady_state, record_fcm

    clamped: dict[str, float] = {}
    for c in clamp or []:
        if "=" not in c:
            raise typer.BadParameter(f"Clamp must be 'entity=value', got {c!r}")
        name, val_str = c.rsplit("=", 1)
        clamped[name.strip()] = float(val_str.strip())

    payload = fcm_steady_state(clamp=clamped)
    recorded = record_fcm(payload) if record else None
    if json_mode():
        emit({"converged": payload["converged"], "iterations": payload["iterations"], "activations": [
            {"variable": a["label"], "activation": a["activation"], "clamped": a["clamped"]}
            for a in payload["activations"]
        ], "run_id": recorded[1] if recorded else None}, human=lambda: None,
            commit_sha=recorded[0] if recorded else None)
        return

    status = "[green]converged[/green]" if payload["converged"] else "[yellow]did not converge[/yellow]"
    console.print(f"FCM inference: {status} in {payload['iterations']} iteration(s)\n")
    table = Table(show_header=True, header_style="bold")
    table.add_column("Variable")
    table.add_column("Activation", justify="right")
    table.add_column("Status")
    for a in payload["activations"]:
        val = a["activation"]
        val_str = f"[green]{val:.3f}[/green]" if val > 0.7 else f"[red]{val:.3f}[/red]" if val < 0.3 else f"{val:.3f}"
        table.add_row(a["label"], val_str, "[bold]clamped[/bold]" if a["clamped"] else "")
    console.print(table)
    if recorded:
        console.print(f"\nrecorded · {recorded[0][:8]}")
