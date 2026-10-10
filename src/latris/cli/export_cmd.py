from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.console import Console

from latris.cli._errors import handle_cli_errors
from latris.exporters import dot as dot_exporter
from latris.exporters import markdown as md_exporter
from latris.exporters import review_html as review_exporter
from latris.exporters import word as word_exporter
from latris.repo.project import require_project

app = typer.Typer(help="Export the project to Markdown, Word, Graphviz DOT, or Review Pack.", no_args_is_help=True)
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
        help="Report pack (review, audit, client, workshop, publication). Omit for the full report.",
    ),
) -> None:
    """Render the project as a Markdown report (stdout by default)."""
    paths = require_project()
    if output is None:
        _emit(md_exporter.render(paths, pack=pack, model_type=model_type))
        return
    target = Path(output)
    if not target.is_absolute():
        target = paths.root / target
    md_exporter.write(paths, target, pack=pack, model_type=model_type)
    console.print(f"[green]wrote[/green] {target.as_posix()}")


@app.command("word")
@handle_cli_errors
def export_word(
    output: str = typer.Option(
        "report.docx",
        "--output",
        "-o",
        help="Output .docx file. Relative paths resolve to the project root.",
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
        help="Report pack (review, audit, client, workshop, publication). Omit for the full report.",
    ),
) -> None:
    """Render the project as a Word (.docx) document."""
    paths = require_project()
    target = Path(output)
    if not target.is_absolute():
        target = paths.root / target
    word_exporter.write(paths, target, pack=pack, model_type=model_type)
    console.print(f"[green]wrote[/green] {target.as_posix()}")


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


@app.command("review")
@handle_cli_errors
def export_review(
    output: str = typer.Option(
        "review.html",
        "--output",
        "-o",
        help="Output .html file. Relative paths resolve to the project root.",
    ),
    pack: str = typer.Option(
        "review",
        "--pack",
        "-p",
        help="Report pack (review, audit, client, workshop, publication).",
    ),
    model_type: str = typer.Option(
        None,
        "--model-type",
        "-m",
        help="Scope the review pack to one formalism (e.g. cld, dag, fcm). Omit for the whole project.",
    ),
) -> None:
    """Render a self-contained HTML review pack for external feedback."""
    paths = require_project()
    target = Path(output)
    if not target.is_absolute():
        target = paths.root / target
    html = review_exporter.render(paths, pack=pack, model_type=model_type)
    target.write_text(html, encoding="utf-8")
    console.print(f"[green]wrote[/green] {target.as_posix()}")
