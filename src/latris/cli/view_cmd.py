from __future__ import annotations

import typer
from rich.console import Console

from latris.cli._errors import handle_cli_errors
from latris.cli._output import emit
from latris.operations import view_attributes as view_attr_ops
from latris.operations import view_roles as view_role_ops
from latris.operations import views as view_ops

app = typer.Typer(help="View projection and model-specific attributes.", no_args_is_help=True)
console = Console()


@app.command("project")
@handle_cli_errors
def view_project(
    kind: str = typer.Argument(..., help="View kind: cld | dag."),
) -> None:
    """Project the current mappings into a formal view."""
    view = view_ops.project_view(kind)
    console.print(f"Projected {kind} view: {len(view.entity_ids)} entities, {len(view.edge_ids)} edges")


@app.command("auto-project")
@handle_cli_errors
def view_auto_project(
    kind: str = typer.Argument(..., help="View kind: cld | dag."),
) -> None:
    """Map all substrate elements to a view and project it."""
    created = view_ops.auto_project(kind)
    console.print(f"Auto-projected {kind} view: {len(created)} new mappings created")


@app.command("set")
@handle_cli_errors
def view_set(
    model_type: str = typer.Argument(..., help="Model type the attribute belongs to (e.g. cld, fcm)."),
    target: str = typer.Argument(..., help="Node ID/label or edge ID."),
    attribute: str = typer.Argument(..., help="Model-specific attribute (e.g. polarity for cld)."),
    value: str = typer.Argument(..., help="Attribute value (e.g. + or - for CLD polarity)."),
    rationale: str = typer.Option(None, "--rationale", help="Why this value, e.g. the causal story of a polarity."),
) -> None:
    """Set a model-specific attribute, such as a CLD edge's polarity.

    Put ``--`` before a negative number so it isn't read as an option:
    ``latris view set fcm <edge> weight -- -0.7``.
    """
    target_id, sha = view_attr_ops.set_view_attribute(target, model_type, attribute, value, rationale=rationale)
    emit(
        {"target_id": target_id, "model_type": model_type, "attribute": attribute, "value": value},
        commit_sha=sha,
        human=lambda: console.print(
            f"[green]set[/green] {model_type} {attribute} = {value} on [cyan]{target_id}[/cyan] "
            f"· commit [cyan]{sha[:10]}[/cyan]"
        ),
    )


@app.command("role")
@handle_cli_errors
def view_role(
    model_type: str = typer.Argument(..., help="Model type the role belongs to (e.g. cld)."),
    target: str = typer.Argument(..., help="Node ID or label."),
    role: str = typer.Argument(..., help="Role in that view, e.g. outcome (cld, dag, fcm)."),
) -> None:
    """Give a factor a role in a view, e.g. mark the outcome the model explains.

    ``latris view role cld "Volunteer departures" outcome`` keeps the outcome
    out of the intervention points the report suggests.
    """
    target_id, sha = view_role_ops.set_role(target, model_type, role)
    emit(
        {"target_id": target_id, "model_type": model_type, "role": role},
        commit_sha=sha,
        human=lambda: console.print(
            f"[green]set[/green] {model_type} role = {role} on [cyan]{target_id}[/cyan] "
            f"· commit [cyan]{sha[:10]}[/cyan]"
        ),
    )
