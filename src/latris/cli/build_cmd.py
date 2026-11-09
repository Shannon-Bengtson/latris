from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape

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
    is changed. `latris docs` has a worked example. Keys:

    - ``context``: background, audience, boundary, intuition (what the
      person expects the answer to be) — the top of the report
    - ``factors``: label, kind, description, sources, contradicts
    - ``links``: from, to, polarity (+ or -), reason, confidence
      (low | medium | high | quantitative-pending | by-definition),
      sources, contradicts
    - ``sources``: key, title, authors, year, container, doi, url, notes,
      extract (the text you read), extract_url, extract_kind, cited_via (the source it was read in)
    - ``assumptions``: text, or text + target + rationale
    - ``questions``: text
    - ``findings``: statement, category (structure | dynamics |
      sensitivity | inference | diagnostics | recommendations), detail,
      targets — recorded as proposed; a person approves them
    - ``challenges``: argument, target
    - ``decisions``: statement, rationale, target
    - ``interpretation``: section, prose, by (ai | human)
    - ``outcome``: the factor the model explains
    - ``sd``: roles, stocks, constants, equations, tables, uncertainty
      (node, distribution, params, reason), scenarios (name, set:
      ["Variable=value units"], description, reason)
    - ``bn``: states, tables (node, parents, probabilities), noisy_or
    - ``analyses``: kind (simulate | monte_carlo | sensitivity | loops |
      bn_query | bn_sensitivity) + its options — run and recorded after
      building, so the report shows them

    Targets are factor labels or links written "From -> To". Quote YAML
    values that contain a colon.
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
            f"{result.questions} questions"
            + (f", {result.parameters} parameters" if result.parameters else "")
            + (f", {len(result.analyses)} analyses run" if result.analyses else "")
            + f" · commit [cyan]{result.commit_sha[:10]}[/cyan]"
            + "".join(f"\n[yellow]note:[/yellow] {escape(n)}" for n in result.notes)
        ),
    )
    if result.missing_extras:
        # The model is built, but analyses it asked for didn't run: that must not look like success.
        raise typer.Exit(code=1)
