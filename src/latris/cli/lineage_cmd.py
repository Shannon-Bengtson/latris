"""CLI wiring for lineage operations — milestones, alternatives, version tree."""

from __future__ import annotations

import typer
from rich.console import Console

from latris.cli._errors import handle_cli_errors
from latris.operations import lineage as ops
from latris.operations import sync as sync_ops

console = Console()

app = typer.Typer(help="Version tree: milestones, alternatives, switch.", no_args_is_help=True)


@app.command("milestone")
@handle_cli_errors
def milestone(
    name: str = typer.Argument(..., help="Name for this milestone."),
    maturity: str = typer.Option("proposed", "--maturity", "-m", help="proposed | reviewed | approved."),
    notes: str = typer.Option(None, "--notes", "-n", help="Optional notes."),
) -> None:
    """Mark the current state as a named milestone."""
    entry, sha = ops.create_milestone(name, maturity=maturity, notes=notes)  # type: ignore[arg-type]
    console.print(
        f"[green]milestone[/green] [cyan]{entry.id}[/cyan] '{entry.name}' "
        f"({entry.maturity}) · commit [cyan]{sha[:10]}[/cyan]"
    )


@app.command("alternative")
@handle_cli_errors
def alternative(
    name: str = typer.Argument(..., help="Name for the new version."),
    from_milestone: str = typer.Option(None, "--from", "-f", help="Start from a milestone (ID or name)."),
    notes: str = typer.Option(None, "--notes", "-n", help="Optional notes."),
) -> None:
    """Create a new version as an alternative from the current state."""
    node, branch = ops.create_alternative(name, from_milestone=from_milestone, notes=notes)
    console.print(f"[green]created alternative[/green] [cyan]{node.id}[/cyan] '{node.name}' on branch {branch}")


@app.command("restore")
@handle_cli_errors
def restore(
    milestone_query: str = typer.Argument(..., help="Milestone to restore from (ID or name)."),
    name: str = typer.Argument(..., help="Name for the new version."),
    notes: str = typer.Option(None, "--notes", "-n", help="Optional notes."),
) -> None:
    """Create a new version by restoring a milestone's state."""
    node, branch = ops.restore_milestone(milestone_query, name, notes=notes)
    console.print(f"[green]restored[/green] [cyan]{node.id}[/cyan] '{node.name}' on branch {branch}")


@app.command("switch")
@handle_cli_errors
def switch(
    version_query: str = typer.Argument(..., help="Version ID, name, or 'main'."),
) -> None:
    """Switch to a different version."""
    result = ops.switch_version(version_query)
    name = result["name"] if isinstance(result, dict) else result.name
    console.print(f"[green]switched to[/green] '{name}'")


@app.command("tree")
@handle_cli_errors
def tree() -> None:
    """Show the lineage version tree."""
    data = ops.get_lineage_tree()
    nodes = data["nodes"]
    edges = data.get("edges", [])
    current_id = data["current_version_id"]
    milestones = data["milestones"]

    if not nodes:
        console.print("[dim](no lineage data)[/dim]")
        return

    # Build a simple text tree. Parent map is derived from server-side edges
    # (which come from git topology); root nodes are those with no incoming edge.
    parent_of: dict[str, str | None] = {}
    for n in nodes:
        nid = n["id"] if isinstance(n, dict) else n.id
        parent_of[nid] = None
    for e in edges:
        parent_of[e["target"]] = e["source"]

    by_parent: dict[str | None, list] = {}
    for n in nodes:
        nid = n["id"] if isinstance(n, dict) else n.id
        by_parent.setdefault(parent_of.get(nid), []).append(n)

    def _get(n, key):
        return n[key] if isinstance(n, dict) else getattr(n, key)

    def _print_subtree(parent_id: str | None, indent: int = 0) -> None:
        for n in by_parent.get(parent_id, []):
            nid = _get(n, "id")
            name = _get(n, "name")
            maturity = _get(n, "maturity")
            rel = _get(n, "relationship")
            marker = " [bold cyan]← current[/bold cyan]" if nid == current_id else ""
            prefix = "  " * indent + ("├─ " if indent > 0 else "")
            console.print(f"{prefix}[bold]{name}[/bold] ({rel}, {maturity}){marker}")

            # Show milestones for this node.
            node_milestones = milestones.get(nid, [])
            for m in node_milestones:
                m_name = m["name"] if isinstance(m, dict) else m.name
                m_maturity = m["maturity"] if isinstance(m, dict) else m.maturity
                m_prefix = "  " * (indent + 1) + "  ◆ "
                console.print(f"{m_prefix}[dim]{m_name} ({m_maturity})[/dim]")

            _print_subtree(nid, indent + 1)

    _print_subtree(None)


@app.command("preferred")
@handle_cli_errors
def preferred(
    version_query: str = typer.Argument(..., help="Version ID, name, or 'main'."),
) -> None:
    """Tag a version as the preferred (canonical) model."""
    version_id, sha = ops.set_preferred(version_query)
    console.print(f"[green]preferred[/green] → [cyan]{version_id}[/cyan] · commit [cyan]{sha[:10]}[/cyan]")


@app.command("update")
@handle_cli_errors
def update(
    name: str = typer.Option(None, "--name", help="New version name."),
    maturity: str = typer.Option(None, "--maturity", "-m", help="proposed | reviewed | approved."),
    notes: str = typer.Option(None, "--notes", "-n", help="New notes."),
) -> None:
    """Update the current version's metadata."""
    node, sha = ops.update_version(name=name, maturity=maturity, notes=notes)  # type: ignore[arg-type]
    if sha:
        console.print(
            f"[green]updated version[/green] '{node.name}' ({node.maturity}) · commit [cyan]{sha[:10]}[/cyan]"
        )
    else:
        console.print("[dim]no changes[/dim]")


# -- Per-version sync: publish / get latest / add / status --------------------


@app.command("publish")
@handle_cli_errors
def publish(
    version_query: str = typer.Argument(..., help="Version ID, name, or 'main'."),
) -> None:
    """Publish a version so collaborators can see it."""
    result = sync_ops.publish_version(version_query)
    console.print(
        f"[green]published[/green] '{result['branch']}' · commit [cyan]{result['head'][:10]}[/cyan]"
    )


@app.command("get-latest")
@handle_cli_errors
def get_latest(
    version_query: str = typer.Argument(..., help="Version ID, name, or 'main'."),
) -> None:
    """Bring a published version up to date with the shared copy."""
    result = sync_ops.get_latest(version_query)
    if result.get("status") == "conflict":
        console.print("[yellow]conflict[/yellow] — coordinate with collaborators, then resolve.")
    else:
        console.print(f"[green]up to date[/green] on '{result['branch']}'")


@app.command("add")
@handle_cli_errors
def add(
    branch: str = typer.Argument(..., help="Branch of the remote-only version to add."),
) -> None:
    """Add a collaborator's published version to your workspace."""
    result = sync_ops.add_to_workspace(branch)
    console.print(f"[green]added[/green] '{result['branch']}' to your workspace")


@app.command("sync-status")
@handle_cli_errors
def sync_status() -> None:
    """Show per-version sync state (published / local / ahead / behind)."""
    info = sync_ops.version_sync_states()
    tree = ops.get_lineage_tree()  # hides archived versions
    if not info["shared"]:
        console.print("[dim](project not shared — all versions are local)[/dim]")
    labels = {
        "local_only": "[dim]local only[/dim]",
        "in_sync": "[green]in sync[/green]",
        "unpublished": "[yellow]unpublished changes[/yellow]",
        "updates": "[cyan]updates available[/cyan]",
        "diverged": "[red]diverged — reconcile[/red]",
    }
    for node in tree["nodes"]:
        state = info["sync_state"].get(node["id"])
        if state is None:
            continue
        console.print(f"  [bold]{node['name']}[/bold] — {labels.get(state['state'], state['state'])}")
    for g in info["ghosts"]:
        console.print(
            f"  [dim]{g['name']} — published by a collaborator (not in your workspace)[/dim]"
        )


@app.command("reconcile-preview")
@handle_cli_errors
def reconcile_preview(
    version_query: str = typer.Argument(..., help="Version ID, name, or 'main'."),
) -> None:
    """Show what changed on the shared copy of a diverged version."""
    events = ops.reconcile_preview(version_query)
    if not events:
        console.print("[dim](no differences)[/dim]")
        return
    for e in events:
        console.print(f"  {e.get('summary') or e.get('kind', '')}")


@app.command("reconcile")
@handle_cli_errors
def reconcile(
    version_query: str = typer.Argument(..., help="Version ID, name, or 'main'."),
    keep: str = typer.Option(..., "--keep", help="Which line to keep: mine | theirs."),
) -> None:
    """Resolve a diverged version: keep one line, archive the other."""
    result = ops.reconcile(version_query, keep)
    console.print(
        f"[green]reconciled[/green] '{result['branch']}' (kept {result['keep']}); "
        f"the other line is archived as [cyan]{result['archived_version_id']}[/cyan]"
    )
