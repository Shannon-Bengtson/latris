"""Decision tree CLI — node types, branches, payoffs, uncertainties, settings, show, check, analyse."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from latris.cli._errors import handle_cli_errors
from latris.cli._options import ORIGIN_HELP, verification
from latris.cli._output import emit

app = typer.Typer(help="Decision trees: the best choice under uncertainty, and what information is worth.",
                  no_args_is_help=True)
console = Console()


def _sha(sha: str) -> str:
    return f"commit [cyan]{sha[:10]}[/cyan]"


@app.command("element")
@handle_cli_errors
def element(
    target: str = typer.Argument(..., help="Node ID, ID prefix, or label."),
    kind: str = typer.Argument(..., help="decision | chance | terminal"),
) -> None:
    """Give a factor its node type: decision (someone chooses), chance (the world does) or terminal (a payoff).

    Branches are ordinary links from parent to child (`latris edge add <parent> <child> --kind conditional`);
    each node has one parent. Repeat a node under each branch rather than sharing it.
    """
    from latris.operations import decision_tree as dt

    target_id, sha = dt.set_element(target, kind)
    emit({"target_id": target_id, "element": kind},
         human=lambda: console.print(f"[green]set[/green] {escape(target)} → {kind} · {_sha(sha)}"), commit_sha=sha)


@app.command("branch")
@handle_cli_errors
def branch(
    link: str = typer.Argument(..., help="The branch, written 'Parent -> Child'."),
    label: str = typer.Option(None, "--label", help="The option or state it stands for (default: the child)."),
    probability: float = typer.Option(None, "--probability", "-p", help="For a branch from a chance node."),
    value: float = typer.Option(None, "--value", help="Incurred along the branch (e.g. a cost, as a negative)."),
    source: str = typer.Option(None, "--source"),
    origin: str = typer.Option(None, "--origin", help=ORIGIN_HELP),
    verified: bool = typer.Option(None, "--verified/--unverified", help="A person has checked the value."),
    notes: str = typer.Option(None, "--notes"),
) -> None:
    """Set a branch's label, probability or value (only what you give changes)."""
    from latris.operations import decision_tree as dt

    given = {"label": label, "probability": probability, "value": value, "source_id": source, "origin": origin,
             "notes": notes}
    kwargs = {k: v for k, v in given.items() if v is not None}
    if verified is not None:
        kwargs["verification"] = verification(verified)
    entry, sha = dt.set_branch(link, **kwargs)
    emit(entry, human=lambda: console.print(f"[green]set[/green] branch {escape(link)}: {', '.join(kwargs)} · "
                                            f"{_sha(sha)}"), commit_sha=sha)


@app.command("payoff")
@handle_cli_errors
def payoff(
    target: str = typer.Argument(..., help="A terminal node."),
    value: float = typer.Argument(..., help="Its value, in the tree's units."),
    source: str = typer.Option(None, "--source"),
    origin: str = typer.Option("human-direct", "--origin", help=ORIGIN_HELP),
    verified: bool = typer.Option(False, "--verified"),
    notes: str = typer.Option(None, "--notes"),
) -> None:
    """Set the payoff at a terminal node."""
    from latris.operations import decision_tree as dt

    entry, sha = dt.set_payoff(target, value, origin=origin, source_id=source, notes=notes,  # type: ignore[arg-type]
                               verification=verification(verified))
    emit(entry, human=lambda: console.print(f"[green]set[/green] payoff {escape(target)} = {value:g} · {_sha(sha)}"),
         commit_sha=sha)


@app.command("uncertainty")
@handle_cli_errors
def uncertainty(
    target: str = typer.Argument(..., help="A chance node."),
    name: str = typer.Argument(..., help="The uncertainty it resolves, e.g. 'Demand'."),
) -> None:
    """Name the uncertainty a chance node resolves. Chance nodes with the same name — the same uncertainty under
    different choices — are priced together for the value of information."""
    from latris.operations import decision_tree as dt

    entry, sha = dt.set_uncertainty(target, name)
    emit(entry, human=lambda: console.print(f"[green]set[/green] {escape(target)} resolves {escape(name)} · "
                                            f"{_sha(sha)}"), commit_sha=sha)


@app.command("settings")
@handle_cli_errors
def settings(
    objective: str = typer.Option(None, "--objective", help="maximise (e.g. profit) | minimise (e.g. cost)."),
    units: str = typer.Option(None, "--units", help="The payoffs' units, e.g. '$k'."),
) -> None:
    """Set whether the best choice maximises or minimises expected value, and the units."""
    from latris.operations import decision_tree as dt

    s, sha = dt.set_settings(objective=objective, units=units)
    emit(s, human=lambda: console.print(f"[green]set[/green] {s.objective}" + (f", {escape(s.units)}" if s.units
                                                                                else "") + f" · {_sha(sha)}"),
         commit_sha=sha)


def _print_tree(d: dict, depth: int, units: str | None, via: str = "") -> None:
    from latris.operations.decision_tree import fmt

    tag = {"decision": "□", "chance": "○", "terminal": "◁"}[d["type"]]
    val = fmt(d["payoff"], units) if d["type"] == "terminal" else f"EV {fmt(d['ev'], units)}"
    console.print("  " * depth + escape(via) + f"{tag} {escape(d['node'])}  [dim]{val}[/dim]")
    for b in d.get("branches", []):
        bits = [b["label"]]
        if b["probability"] is not None:
            bits.append(f"p {b['probability']:.3g}")
        if b["value"]:
            bits.append(f"{b['value']:+g}")
        mark = "→ " if b["chosen"] else "  "
        _print_tree(b["to"], depth + 1, units, via=f"{mark}[{', '.join(bits)}] ")


@app.command("show")
@handle_cli_errors
def show() -> None:
    """Print the tree from the root, with expected values; → marks the best choice at each decision."""
    from latris.operations import decision_tree as dt

    payload = dt.analyse()

    def human() -> None:
        for p in payload["problems"]:
            console.print(f"[yellow]![/yellow] {escape(p['label'])}: {escape(p['message'])}")
        if not payload["problems"]:
            _print_tree(payload["tree"], 0, payload["units"])

    emit(payload.get("tree") or payload, human=human)


@app.command("check")
@handle_cli_errors
def check() -> None:
    """Check the tree is complete: one root, a tree, payoffs and probabilities summing to 1. Exits 1 until so."""
    from latris.operations.readiness import assess_readiness

    r = assess_readiness("decision_tree")
    gaps = [{"element": g.element_label, "gap_type": g.gap_type, "message": g.message} for g in r.gaps]

    def human() -> None:
        if r.can_switch:
            console.print("[green]The decision tree is complete.[/green]")
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
    """The best strategy by expected value, what perfect information on each uncertainty is worth (EVPI), and the
    probabilities at which the best choice changes."""
    from latris.operations import decision_tree as dt
    from latris.operations.formalisms.decision_tree import _threshold_lines

    payload = dt.analyse()
    sha = None
    if not no_record and not payload["problems"]:
        sha, payload["run_id"] = dt.record(payload)

    def human() -> None:
        for p in payload["problems"]:
            console.print(f"[yellow]![/yellow] {escape(p['label'])}: {escape(p['message'])}")
        console.print(escape(dt.describe(payload)) + ".\n")
        if payload["problems"]:
            return
        u = payload["units"]
        if payload.get("options"):
            t = Table(show_header=True, header_style="bold", title=f"{payload['root']} ({payload['objective']})")
            t.add_column("Option")
            t.add_column("Expected value", justify="right")
            for o in payload["options"]:
                t.add_row(("[bold]" if o["best"] else "") + escape(o["option"]), dt.fmt(o["ev"], u))
            console.print(t)
        ev = payload["evpi"]
        if ev["per_uncertainty"]:
            t = Table(show_header=True, header_style="bold", title="Value of perfect information")
            t.add_column("Uncertainty")
            t.add_column("EVPI", justify="right")
            t.add_column("Best choice if known")
            for x in sorted(ev["per_uncertainty"], key=lambda x: -x["evpi"]):
                t.add_row(escape(x["uncertainty"]), dt.fmt(x["evpi"], u),
                          escape("; ".join(f"{s}: {d['choice']}" for s, d in x["by_state"].items())))
            console.print(t)
            if ev["all"]:
                console.print(f"Knowing everything first: worth up to {dt.fmt(ev['all']['evpi'], u)}")
        for s in ev["skipped"]:
            console.print(f"[dim]not priced: {escape(s)}[/dim]")
        for line in _threshold_lines(payload):
            console.print(escape(line))
        if payload["unverified_on_path"]:
            console.print("[yellow]Unverified on the best path:[/yellow] "
                          + escape(", ".join(payload["unverified_on_path"])))
        if sha:
            console.print(f"\nrecorded · {_sha(sha)}")

    emit(payload, human=human, commit_sha=sha)
