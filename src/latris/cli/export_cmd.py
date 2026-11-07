from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.console import Console

from latris.cli._errors import handle_cli_errors
from latris.cli._output import json_mode
from latris.exporters import dot as dot_exporter
from latris.exporters import markdown as md_exporter
from latris.operations import sync as sync_ops
from latris.repo.project import require_project

app = typer.Typer(help="Export the project to Markdown or Graphviz DOT.", no_args_is_help=True)
console = Console()


def _emit(text: str) -> None:
    """Write exporter output to stdout without rich markup processing.

    Rich interprets ``[...]`` as style tags, which mangles DOT attrs and any
    Markdown containing brackets. Go straight to stdout instead.
    """
    sys.stdout.write(text)
    if not text.endswith("\n"):
        sys.stdout.write("\n")


@app.command("md")
@handle_cli_errors
def export_md(
    output: str = typer.Option(
        None,
        "--output",
        "-o",
        help="Write to file instead of stdout. Relative paths resolve to the project root.",
    ),
    model_type: str = typer.Option(
        None,
        "--model-type",
        "-m",
        help="Scope the report to one formalism (e.g. cld, dag, fcm). Omit for the whole project.",
    ),
    pack: str = typer.Option(
        None,
        "--pack",
        "-p",
        help=(
            "Report pack: client (board/funder, no IDs), publication (paper, no IDs), review (a reviewer), "
            "workshop (a stakeholder session), audit (everything). Omit for the full report. "
            "`latris capabilities` describes each."
        ),
    ),
    report_url: str = typer.Option(
        None,
        "--report-url",
        help="Link to the hosted copy of this report, shown in the footer. Defaults to the shared link, if any.",
    ),
    no_ai: bool = typer.Option(
        False,
        "--no-ai",
        help="Write the narrative preamble without an AI call (fast, deterministic, no credentials).",
    ),
    no_link: bool = typer.Option(
        False,
        "--no-link",
        help="Leave out the link to the full figure in the Latris app (made fresh on every export, offline).",
    ),
) -> None:
    """Render the project as a Markdown report (stdout by default).

    Under the diagram, the report links to the full Latris figure and the
    interactive report (the same link `latris link` prints), made fresh on
    every export so it's never out of date.
    """
    paths = require_project()
    if report_url is None:
        report_url = sync_ops.report_url(root=paths.root)
    if output is None:
        _emit(md_exporter.render(
            paths, pack=pack, model_type=model_type, report_url=report_url, ai=not no_ai, app_link=not no_link,
        ))
        if not report_url and not no_link and not json_mode():
            Console(stderr=True).print(f"[dim]{_LINK_HINT}[/dim]")
        return
    target = Path(output)
    if not target.is_absolute():
        target = paths.root / target
    md_exporter.write(
        paths, target, pack=pack, model_type=model_type, report_url=report_url, ai=not no_ai, app_link=not no_link,
    )
    console.print(f"[green]wrote[/green] {target.as_posix()}")
    if not report_url and not no_link and not json_mode():
        console.print(f"[dim]{_LINK_HINT}[/dim]")


# Agents relay what tools print: say where the polished version is, at the moment of output.
_LINK_HINT = (
    "For the person: under the diagram, the report links to this model in the Latris app — the full "
    "figure (loops, evidence), a report they can share, and Word once they save it. The link is made "
    "fresh on every export (no network needed); `latris link` prints it on its own."
)


@app.command("dot")
@handle_cli_errors
def export_dot(
    view: str = typer.Option(
        "system_map",
        "--view",
        "-v",
        help="system_map | cld | dag  (cld labels edges with polarity)",
    ),
    output: str = typer.Option(
        None,
        "--output",
        "-o",
        help="Write to file instead of stdout. Relative paths resolve to the project root.",
    ),
) -> None:
    """Render the substrate as Graphviz DOT (pipe to `dot -Tpng` for an image)."""
    if view not in ("system_map", "cld", "dag"):
        raise typer.BadParameter("view must be one of: system_map, cld, dag")

    paths = require_project()
    if output is None:
        _emit(dot_exporter.render(paths, view=view))  # type: ignore[arg-type]
        return
    target = Path(output)
    if not target.is_absolute():
        target = paths.root / target
    dot_exporter.write(paths, target, view=view)  # type: ignore[arg-type]
    console.print(f"[green]wrote[/green] {target.as_posix()}")
