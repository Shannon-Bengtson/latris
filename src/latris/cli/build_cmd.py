from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path

import typer
from rich.console import Console

from latris.cli._errors import handle_cli_errors
from latris.cli._output import emit
from latris.operations import build as build_ops

console = Console()


@handle_cli_errors
def build(
    spec: str = typer.Option(..., "--spec", help="YAML or JSON file describing the model; '-' reads stdin."),
    verified_by: str = typer.Option(
        "human", "--verified-by", help="human | ai — who verified the citations in the spec apply."
    ),
) -> None:
    """Add a whole model from one spec, as one commit.

    The spec is checked in full first; if anything doesn't resolve, nothing
    is changed. Keys (see the README for an example): ``factors`` (label,
    description, sources, contradicts), ``links`` (from, to, polarity,
    reason, confidence, sources, contradicts), ``sources`` (key, title,
    authors, year, doi, url, notes), ``assumptions`` (text, or text + target
    + rationale), ``questions``, ``findings`` (statement, category, detail,
    targets; recorded as proposed), ``challenges`` (argument, target),
    ``interpretation`` (section, prose, by) and ``outcome``. Targets are
    factor labels or links written "From -> To".
    """
    if verified_by not in {"human", "ai"}:
        raise ValueError("--verified-by must be 'human' or 'ai'.")
    text = sys.stdin.read() if spec == "-" else Path(spec).read_text(encoding="utf-8")
    result = build_ops.build_from_spec(build_ops.load_spec(text), verified_by=verified_by)
    emit(
        asdict(result),
        commit_sha=result.commit_sha,
        human=lambda: console.print(
            f"[green]built[/green] {result.factors} factors, {len(result.links)} links, "
            f"{result.sources} sources, {result.citations} citations, {result.assumptions} assumptions, "
            f"{result.questions} questions · commit [cyan]{result.commit_sha[:10]}[/cyan]"
        ),
    )
