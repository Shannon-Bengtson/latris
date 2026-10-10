from __future__ import annotations

import typer
from rich.console import Console

from latris.cli._errors import handle_cli_errors
from latris.operations import sync as ops

app = typer.Typer(help="Sync the project with a remote (push, pull, fetch).", no_args_is_help=True)
console = Console()


@app.command("remote")
@handle_cli_errors
def remote(
    url: str = typer.Argument(None, help="Remote URL. Omit to show the current remote."),
    name: str = typer.Option("origin", "--name", "-n", help="Remote name."),
) -> None:
    """Set or show the sync remote URL."""
    if url is None:
        current = ops.remote_url(name=name)
        if current:
            console.print(f"[cyan]{name}[/cyan] → {current}")
        else:
            console.print(f"[dim](no '{name}' remote — set one with `latris sync remote <url>`)[/dim]")
        return
    ops.set_remote(url, name=name)
    console.print(f"[green]remote[/green] [cyan]{name}[/cyan] → {url}")


@app.command("push")
@handle_cli_errors
def push(
    remote: str = typer.Option("origin", "--remote", "-r", help="Remote name."),
) -> None:
    """Push the current branch to the remote."""
    sha = ops.push(remote=remote)
    console.print(f"[green]pushed[/green] to [cyan]{remote}[/cyan] · HEAD [cyan]{sha[:10]}[/cyan]")


@app.command("pull")
@handle_cli_errors
def pull(
    remote: str = typer.Option("origin", "--remote", "-r", help="Remote name."),
) -> None:
    """Fetch and merge changes from the remote."""
    sha = ops.pull(remote=remote)
    console.print(f"[green]pulled[/green] from [cyan]{remote}[/cyan] · HEAD [cyan]{sha[:10]}[/cyan]")


@app.command("fetch")
@handle_cli_errors
def fetch(
    remote: str = typer.Option("origin", "--remote", "-r", help="Remote name."),
) -> None:
    """Fetch refs from the remote without merging."""
    ops.fetch(remote=remote)
    console.print(f"[green]fetched[/green] from [cyan]{remote}[/cyan]")


@app.command("status")
@handle_cli_errors
def status(
    remote: str = typer.Option("origin", "--remote", "-r", help="Remote name."),
) -> None:
    """Show local sync state (branch, remote, ahead/behind)."""
    s = ops.status(remote=remote)
    if not s["url"]:
        console.print(f"[dim](no '{remote}' remote configured)[/dim]")
        console.print(f"branch: [cyan]{s['branch']}[/cyan]")
        return
    console.print(f"remote [cyan]{remote}[/cyan]: {s['url']}")
    console.print(f"branch: [cyan]{s['branch']}[/cyan]")
    if s["ahead"] is None:
        console.print("[dim]no upstream tracking yet — push to establish it[/dim]")
    else:
        console.print(f"ahead [green]{s['ahead']}[/green] · behind [yellow]{s['behind']}[/yellow] (since last fetch)")
    if s["uncommitted"]:
        console.print("[yellow]uncommitted changes in the working tree[/yellow]")
