from __future__ import annotations

import sys

# Windows consoles default to cp1252; our YAML/labels/commit messages carry
# Unicode (em-dashes, arrows, non-ASCII names). Reconfigure stdio to UTF-8
# before anything writes so rich never hits an UnsupportedCharError.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

import typer  # noqa: E402
from rich.console import Console  # noqa: E402

from latris import __version__  # noqa: E402
from latris.cli import (  # noqa: E402
    ai_cmd,
    analyse_cmd,
    attr_cmd,
    bn_cmd,
    capabilities_cmd,
    challenge_cmd,
    check_cmd,
    completeness_cmd,
    edge_cmd,
    elicit_cmd,
    evidence_cmd,
    export_cmd,
    fcm_cmd,
    findings_cmd,
    history_cmd,
    interpret_cmd,
    lineage_cmd,
    mapping_cmd,
    maturity_cmd,
    node_cmd,
    project_cmd,
    provenance_cmd,
    ref_cmd,
    review_cmd,
    story_cmd,
    sync_cmd,
    view_cmd,
)
from latris.cli.init_cmd import init as init_command  # noqa: E402

app = typer.Typer(
    name="latris",
    help="AI-assisted, evidence-native modelling workbench (CLI prototype).",
    no_args_is_help=True,
    add_completion=False,
)

app.command("init")(init_command)
app.add_typer(project_cmd.app, name="project")
app.add_typer(node_cmd.app, name="node")
app.add_typer(edge_cmd.app, name="edge")
app.add_typer(attr_cmd.app, name="attr")
app.add_typer(maturity_cmd.app, name="mature")
app.add_typer(ref_cmd.app, name="ref")
app.add_typer(evidence_cmd.app, name="evidence")
app.add_typer(challenge_cmd.app, name="challenge")
app.add_typer(provenance_cmd.assumption_app, name="assumption")
app.add_typer(provenance_cmd.decision_app, name="decision")
app.add_typer(provenance_cmd.signoff_app, name="signoff")
app.add_typer(provenance_cmd.session_app, name="session")
app.add_typer(provenance_cmd.question_app, name="question")
app.add_typer(provenance_cmd.exclusion_app, name="exclusion")
app.add_typer(provenance_cmd.prediction_app, name="prediction")
app.command("log")(history_cmd.log_cmd)
app.command("status")(history_cmd.status_cmd)
app.command("diff")(history_cmd.diff_cmd)
app.add_typer(elicit_cmd.app, name="elicit")
app.add_typer(mapping_cmd.app, name="mapping")
app.add_typer(view_cmd.app, name="view")
app.add_typer(export_cmd.app, name="export")
app.add_typer(review_cmd.app, name="review")
app.add_typer(story_cmd.app, name="story")
app.add_typer(sync_cmd.app, name="sync")
app.add_typer(ai_cmd.app, name="ai")
app.add_typer(analyse_cmd.app, name="analyse")
app.add_typer(check_cmd.app, name="check")
app.add_typer(findings_cmd.app, name="finding")
app.add_typer(interpret_cmd.app, name="interpret")
app.add_typer(completeness_cmd.app, name="completeness")
app.add_typer(fcm_cmd.app, name="fcm")
app.add_typer(bn_cmd.app, name="bn")
app.add_typer(lineage_cmd.app, name="version")

console = Console()


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"latris {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show version and exit.",
        is_eager=True,
        callback=_version_callback,
    ),
) -> None:
    """Root command."""


app.command("capabilities")(capabilities_cmd.capabilities)


@app.command()
def doctor() -> None:
    """Check environment prerequisites (git binary, identity config)."""
    import shutil
    import subprocess

    git = shutil.which("git")
    if not git:
        console.print("[red]git not found on PATH[/red] — install from https://git-scm.com/")
        raise typer.Exit(code=1)
    console.print(f"[green]git[/green]: {git}")

    try:
        name = subprocess.run(
            ["git", "config", "--global", "user.name"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        email = subprocess.run(
            ["git", "config", "--global", "user.email"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
    except OSError as exc:
        console.print(f"[red]could not run git: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    if not name or not email:
        console.print(
            "[yellow]git identity not fully configured[/yellow] — run:\n"
            '    git config --global user.name "Your Name"\n'
            '    git config --global user.email "you@example.com"'
        )
        raise typer.Exit(code=1)

    console.print(f"[green]user.name[/green]: {name}")
    console.print(f"[green]user.email[/green]: {email}")
    console.print("[green]ok[/green] — ready to initialise projects.")
