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
    build_cmd,
    capabilities_cmd,
    challenge_cmd,
    check_cmd,
    checkpoint_cmd,
    completeness_cmd,
    data_cmd,
    docs_cmd,
    edge_cmd,
    elicit_cmd,
    evidence_cmd,
    export_cmd,
    findings_cmd,
    foundations_cmd,
    history_cmd,
    interpret_cmd,
    lineage_cmd,
    link_cmd,
    mapping_cmd,
    maturity_cmd,
    node_cmd,
    project_cmd,
    provenance_cmd,
    ref_cmd,
    results_cmd,
    sync_cmd,
    view_cmd,
)
from latris.cli._output import set_json_mode  # noqa: E402
from latris.cli.init_cmd import init as init_command  # noqa: E402

app = typer.Typer(
    name="latris",
    help=(
        "Evidence-native causal modelling. New here (or an AI agent)? `latris docs` prints the guide — "
        "no network needed — and `latris capabilities` lists what Latris can do."
    ),
    no_args_is_help=True,
    add_completion=False,
)

app.command("init")(init_command)
app.command("build")(build_cmd.build)
app.command("link")(link_cmd.link)
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
app.add_typer(sync_cmd.app, name="sync")
app.add_typer(ai_cmd.app, name="ai")
app.add_typer(analyse_cmd.app, name="analyse")
app.add_typer(check_cmd.app, name="check")
app.add_typer(checkpoint_cmd.app, name="checkpoint")
app.add_typer(findings_cmd.app, name="finding")
app.add_typer(interpret_cmd.app, name="interpret")
app.add_typer(completeness_cmd.app, name="completeness")
def _add_formalism_commands(app: typer.Typer) -> None:
    """Each registered formalism's command group (``operations/formalisms``), in registration order."""
    import importlib

    from latris.operations import formalisms

    for f in formalisms.all_formalisms():
        if f.cli:
            module, name = f.cli
            app.add_typer(importlib.import_module(module).app, name=name)


_add_formalism_commands(app)  # every formalism's own group (sd, bn, fcm, mcda, ft, …), from its plugin
app.add_typer(results_cmd.app, name="results")
app.add_typer(data_cmd.app, name="data")
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
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Print one JSON object instead of rich text (commands that support it).",
    ),
) -> None:
    """Root command."""
    from latris.cli._agent import apply_agent_defaults

    set_json_mode(json_output)
    apply_agent_defaults()


app.command("capabilities")(capabilities_cmd.capabilities)
app.command("foundations")(foundations_cmd.foundations)
app.command("docs")(docs_cmd.docs)


@app.command()
def doctor() -> None:
    """Check environment prerequisites (git binary, identity config)."""
    import shutil

    from latris.repo import git as git_ops

    git = shutil.which("git")
    if not git:
        console.print("[red]git not found on PATH[/red] — install from https://git-scm.com/")
        raise typer.Exit(code=1)
    console.print(f"[green]git[/green]: {git}")

    try:
        name = git_ops.global_config("user.name")
        email = git_ops.global_config("user.email")
    except (OSError, git_ops.GitError) as exc:
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
