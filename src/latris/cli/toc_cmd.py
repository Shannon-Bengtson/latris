"""Theory of Change CLI — give factors their levels, then check the pathways."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from latris.cli._errors import handle_cli_errors
from latris.cli._output import emit, json_mode

app = typer.Typer(help="Theory of Change (results chain) operations.", no_args_is_help=True)
console = Console()

_STATUS_STYLE = {"checked": "green", "cited": "yellow", "untested": "red", "contested": "magenta"}


def _labels() -> dict[str, str]:
    from latris.operations import nodes as node_ops

    return {e.id: e.label for e in node_ops.list_nodes()}


@app.command("level")
@handle_cli_errors
def level(
    target: str = typer.Argument(..., help="Node ID, ID prefix, or label."),
    value: str = typer.Argument(
        ..., help="input | activity | output | short_term_outcome | long_term_outcome | impact"
    ),
) -> None:
    """Give a factor its level in the results chain.

    Activities are what the intervention does; outputs what it directly
    produces; short- and long-term outcomes the changes that follow; the
    impact is the long-term change it is for (the outcome of interest).
    Inputs are the resources it uses.
    """
    from latris.operations import toc

    target_id, sha = toc.set_level(target, value)
    if json_mode():
        emit({"target_id": target_id, "level": value}, human=lambda: None, commit_sha=sha)
        return
    name = escape(_labels().get(target_id, target_id[:15]))
    console.print(f"[green]set[/green] {name} → {value} · commit [cyan]{sha[:10]}[/cyan]")


@app.command("levels")
@handle_cli_errors
def levels() -> None:
    """List factors by level, from inputs to impact."""
    from latris.operations import toc

    labels = _labels()
    lv = toc.get_levels()
    rows = sorted(
        ({"node": labels.get(eid, eid), "level": lvl} for eid, lvl in lv.items() if eid in labels),
        key=lambda r: (toc.LEVELS.index(r["level"]), r["node"]),
    )
    unset = sorted(name for eid, name in labels.items() if eid not in lv)

    def human() -> None:
        if not rows and not unset:
            console.print("[dim](no factors)[/dim]")
            return
        table = Table(show_header=True, header_style="bold")
        table.add_column("Level")
        table.add_column("Factor")
        for r in rows:
            table.add_row(toc.LEVEL_NAMES[r["level"]], escape(r["node"]))
        for name in unset:
            table.add_row("[red]no level[/red]", escape(name))
        console.print(table)

    emit({"levels": rows, "no_level": unset}, human=human)


@app.command("check")
@handle_cli_errors
def check(
    no_record: bool = typer.Option(False, "--no-record", help="Show the result without recording it for reports."),
) -> None:
    """Lay out every pathway from an activity to an impact and what holds each link up.

    A link is *checked* when a source was read and found to support it,
    *cited* when it has a source nobody has checked yet, *untested* with no
    source, and *contested* when a source argues against it. A pathway is as
    strong as its weakest link. Recorded for reports unless --no-record.
    """
    from latris.operations import toc

    payload, sha = toc.check(record=not no_record)

    def human() -> None:
        problems = payload["problems"]
        if problems:
            console.print(f"[yellow]{len(problems)} structure problem(s):[/yellow]")
            for p in problems:
                console.print(f"  - {escape(p['label'])}: {escape(p['message'])}")
            console.print()
        counts = ", ".join(f"{n} {toc.LEVEL_NAMES[lvl].lower()}" for lvl, n in payload["counts"].items() if n)
        if counts:
            console.print(f"Levels: {counts}")
        console.print(escape(toc.describe(payload)) + ".\n")
        if payload["pathways"]:
            table = Table(show_header=True, header_style="bold", title="Pathways (weakest first)")
            table.add_column("Pathway")
            table.add_column("Weakest link")
            table.add_column("Links below checked")
            order = {"contested": 0, "untested": 1, "cited": 2, "checked": 3}
            for p in sorted(payload["pathways"], key=lambda p: order[p["status"]]):
                style = _STATUS_STYLE[p["status"]]
                table.add_row(
                    escape(" → ".join(p["path"])), f"[{style}]{p['status']}[/{style}]",
                    escape(", ".join(p["weak_links"])) or "—",
                )
            console.print(table)
        on = [lk for lk in payload["links"] if lk["on_pathway"]]
        if on:
            table = Table(show_header=True, header_style="bold", title="Links on a pathway")
            table.add_column("Link")
            table.add_column("Evidence")
            table.add_column("For / checked / against", justify="right")
            table.add_column("Assumptions", justify="right")
            table.add_column("Note")
            for lk in on:
                style = _STATUS_STYLE[lk["status"]]
                note = "leap: skips levels — state the steps between" if lk["leap"] else ""
                table.add_row(
                    escape(lk["label"]), f"[{style}]{lk['status']}[/{style}]",
                    f"{lk['sources_for']} / {lk['sources_for_checked']} / {lk['sources_against']}",
                    str(lk["assumptions"]) if lk["assumptions"] else "[red]0[/red]", note,
                )
            console.print(table)
        if sha:
            console.print(f"\nrecorded · commit [cyan]{sha[:10]}[/cyan]")

    emit(payload, human=human, commit_sha=sha)
