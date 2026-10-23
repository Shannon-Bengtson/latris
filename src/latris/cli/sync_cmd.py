from __future__ import annotations

import typer
from rich.console import Console

from latris.cli._errors import handle_cli_errors
from latris.operations import sync as ops

app = typer.Typer(help="Sync the project with a remote (push, pull, fetch).", no_args_is_help=True)
console = Console()

# The real public control plane and the real public hosted app — both
# overridable for anyone self-hosting either. Backend code never hardcodes
# either domain; these are purely CLI-default conveniences.
DEFAULT_SERVER_URL = "https://sync.latris.app"
DEFAULT_APP_URL = "https://app.latris.app"


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


@app.command("login")
@handle_cli_errors
def login(
    email: str = typer.Option(..., "--email", help="Account email."),
    code: str = typer.Option(None, "--code", help="The one-time code emailed to you. Omit to request one."),
    server: str = typer.Option(DEFAULT_SERVER_URL, "--server", help="Control-plane server URL."),
    device: str = typer.Option("Latris CLI", "--device", help="Label shown for this login in account settings."),
    intent: str = typer.Option("auto", "--intent", help="auto | signin | signup."),
    first_name: str = typer.Option(None, "--first-name", help="Only used when creating a new account."),
    last_name: str = typer.Option(None, "--last-name", help="Only used when creating a new account."),
    organisation: str = typer.Option(None, "--organisation", help="Only used when creating a new account."),
    country: str = typer.Option(None, "--country", help="Only used when creating a new account."),
    role: str = typer.Option(None, "--role", help="Only used when creating a new account."),
    industry: str = typer.Option(None, "--industry", help="Only used when creating a new account."),
) -> None:
    """Sign in (or create an account) on the Latris control plane.

    Two calls: first without --code to get one emailed to you, then again
    with --code to finish. Lets an agent carry a human through sign-in —
    run this, relay "what code did you get?" to them, then run it again.
    """
    if code is None:
        ops.login_request_code(server, email, intent)
        console.print(f"[green]code sent[/green] to [cyan]{email}[/cyan] — check your inbox, then run:")
        console.print(f'  latris sync login --email {email} --code <the code>')
        return
    account = ops.login_verify(
        server, email, code, device,
        intent=intent, first_name=first_name, last_name=last_name,
        organisation=organisation, country=country, role=role, industry=industry,
    )
    console.print(f"[green]signed in[/green] as {account.get('display_name')} <{account['email']}>")
    console.print('[dim]next: `latris sync share "<project name>"` to put a project online[/dim]')


@app.command("share")
@handle_cli_errors
def share(
    name: str = typer.Argument(..., help="Name for the shared project."),
    app_url: str = typer.Option(DEFAULT_APP_URL, "--app-url", help="Hosted app URL to show in the confirmation."),
) -> None:
    """Share this project to the control plane so others can view/collaborate online.

    Requires `latris sync login` first. Creates a remote project, wires it
    as the git remote, and pushes — then prints the link to open it in the
    hosted app.
    """
    account = ops.current_account()
    proj = ops.share(name)
    console.print(f'[green]shared[/green] "{name}" ({proj["id"]})')
    email_hint = f" (sign in with {account['email']})" if account else ""
    console.print(f"[dim]view online:[/dim] {app_url}/{email_hint}")


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
