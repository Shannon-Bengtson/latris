"""ACH CLI — hypotheses, evidence items, ratings, show, check, analyse."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from latris.cli._errors import handle_cli_errors
from latris.cli._options import ORIGIN_HELP, verification
from latris.cli._output import emit

app = typer.Typer(help="Analysis of competing hypotheses.", no_args_is_help=True)

# Where each command sits in the workflow (schema/workflow.py; rules in docs/engineering/WORKFLOW_STRUCTURE.md).
PLACE = {
    "element": "formalise.definitions",
    "item": "formalise.definitions",
    "rate": "formalise.values",
    "show": "formalise",
    "check": "validation",
    "analyse": "analyse.base_case",
}
console = Console()
_STYLE = {"CC": "green", "C": "green", "N": "dim", "I": "red", "II": "bold red"}


def _sha(sha: str) -> str:
    return f"commit [cyan]{sha[:10]}[/cyan]"


@app.command("element")
@handle_cli_errors
def element(
    target: str = typer.Argument(..., help="Node ID, ID prefix, or label."),
    kind: str = typer.Argument(..., help="hypothesis | evidence_item"),
) -> None:
    """Make a factor a hypothesis (a possible explanation) or an evidence item (a fact, report, argument or
    absence). An evidence item can carry its own sources: `latris evidence add <item> description <key>`."""
    from latris.operations import ach

    target_id, sha = ach.set_element(target, kind)
    emit({"target_id": target_id, "element": kind},
         human=lambda: console.print(f"[green]set[/green] {escape(target)} → {kind} · {_sha(sha)}"), commit_sha=sha)


@app.command("item")
@handle_cli_errors
def item(
    target: str = typer.Argument(..., help="An evidence item."),
    credibility: str = typer.Option(None, "--credibility", help="high | medium | low — how far it can be trusted."),
    relevance: str = typer.Option(None, "--relevance", help="high | medium | low — how directly it bears."),
    notes: str = typer.Option(None, "--notes"),
) -> None:
    """Set an evidence item's credibility and relevance (both default to medium)."""
    from latris.operations import ach

    given = {"credibility": credibility, "relevance": relevance, "notes": notes}
    kwargs = {k: v for k, v in given.items() if v is not None}
    entry, sha = ach.set_item(target, **kwargs)
    emit(entry, human=lambda: console.print(f"[green]set[/green] {escape(target)}: {', '.join(kwargs)} · "
                                            f"{_sha(sha)}"), commit_sha=sha)


@app.command("rate")
@handle_cli_errors
def rate(
    item: str = typer.Argument(..., help="An evidence item."),
    hypothesis: str = typer.Argument(..., help="A hypothesis."),
    rating: str = typer.Argument(..., help="CC | C | N | I | II (very consistent … very inconsistent)."),
    rationale: str = typer.Option(None, "--rationale", help="Why — especially for I and II."),
    origin: str = typer.Option("human-direct", "--origin", help=ORIGIN_HELP),
    verified: bool = typer.Option(False, "--verified", help="A person has reviewed this rating."),
) -> None:
    """Rate how an evidence item bears on a hypothesis.

    Ask: if this hypothesis were true, how likely would I be to see this
    evidence? Unlikely → I or II. Evidence consistent with every
    hypothesis rates the same everywhere and won't help choose.
    """
    from latris.operations import ach

    entry, sha = ach.set_rating(item, hypothesis, rating, rationale=rationale, origin=origin,  # type: ignore[arg-type]
                                verification=verification(verified))
    emit(entry, human=lambda: console.print(f"[green]rated[/green] {escape(item)} vs {escape(hypothesis)}: "
                                            f"{entry.rating} · {_sha(sha)}"), commit_sha=sha)


@app.command("show")
@handle_cli_errors
def show() -> None:
    """Print the matrix: evidence items × hypotheses."""
    from latris.operations import ach

    m = ach.load()
    lab = m.labels
    data = {"hypotheses": [lab[h] for h in m.hypotheses], "items": [
        {"item": lab[i], "ratings": {lab[h]: m.ratings[(i, h)].rating for h in m.hypotheses if (i, h) in m.ratings}}
        for i in m.items]}

    def human() -> None:
        t = Table(show_header=True, header_style="bold")
        t.add_column("Evidence")
        for h in m.hypotheses:
            t.add_column(lab[h], justify="center")
        for i in m.items:
            cells = []
            for h in m.hypotheses:
                r = m.ratings.get((i, h))
                cells.append(f"[{_STYLE[r.rating]}]{r.rating}[/{_STYLE[r.rating]}]" if r else "[red]?[/red]")
            t.add_row(escape(lab[i]), *cells)
        console.print(t)
        for p in m.problems:
            console.print(f"[yellow]![/yellow] {escape(lab.get(p.target_id or '', '(matrix)'))}: {escape(p.message)}")

    emit(data, human=human)


@app.command("check")
@handle_cli_errors
def check() -> None:
    """Check every item is rated against every hypothesis. Exits 1 until it is."""
    from latris.operations.readiness import assess_readiness

    r = assess_readiness("ach")
    gaps = [{"element": g.element_label, "gap_type": g.gap_type, "message": g.message} for g in r.gaps]

    def human() -> None:
        if r.can_switch:
            console.print("[green]The ACH matrix is complete.[/green]")
        for g in gaps:
            console.print(f"  - {escape(g['element'])}: {escape(g['message'])}")

    emit({"ready": r.can_switch, "gaps": gaps}, human=human)
    if not r.can_switch:
        raise typer.Exit(1)


@app.command("analyse")
@handle_cli_errors
def analyse(
    no_record: bool = typer.Option(False, "--no-record", help="Show the result without recording it for reports."),
) -> None:
    """Rank hypotheses by the evidence against them, find the linchpins, and flag evidence that doesn't
    discriminate."""
    from latris.operations import ach
    from latris.operations.formalisms.ach import _SOURCE_WORDS

    payload = ach.analyse()
    sha = None
    if not no_record and not payload["problems"]:
        sha, payload["run_id"] = ach.record(payload)

    def human() -> None:
        for p in payload["problems"]:
            console.print(f"[yellow]![/yellow] {escape(p['label'])}: {escape(p['message'])}")
        console.print(escape(ach.describe(payload)) + ".\n")
        if payload["problems"]:
            return
        t = Table(show_header=True, header_style="bold", title="Least evidence against, first")
        t.add_column("Hypothesis")
        t.add_column("Weighted inconsistency", justify="right")
        t.add_column("Evidence against it")
        for r in payload["ranking"]:
            t.add_row(escape(r["hypothesis"]), f"{r['inconsistency']:.2f}", escape(", ".join(r["against"])) or "—")
        console.print(t)
        for x in payload["linchpins"]:
            console.print(f"[bold]Linchpin:[/bold] {escape(x['item'])} — {_SOURCE_WORDS[x['sources']]}")
        if payload["non_diagnostic"]:
            console.print("Doesn't discriminate: " + escape(", ".join(payload["non_diagnostic"])))
        if sha:
            console.print(f"\nrecorded · {_sha(sha)}")

    emit(payload, human=human, commit_sha=sha)
