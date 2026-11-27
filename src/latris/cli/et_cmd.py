"""Event tree CLI — elements, heading order, sequences, probabilities, frequency, show, check, analyse."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from latris.cli._errors import handle_cli_errors
from latris.cli._options import ORIGIN_HELP, verification
from latris.cli._output import emit, json_mode

app = typer.Typer(help="Event tree operations.", no_args_is_help=True)

# Where each command sits in the workflow (schema/workflow.py; rules in docs/engineering/WORKFLOW_STRUCTURE.md).
PLACE = {
    "element": "formalise.definitions",
    "order": "formalise.definitions",
    "sequence": "formalise.definitions",
    "remove_sequence": "formalise.definitions",
    "probability": "formalise.values",
    "frequency": "formalise.values",
    "show": "formalise",
    "check": "validation",
    "analyse": "analyse.base_case",
}
console = Console()



def _sha(sha: str) -> str:
    return f"commit [cyan]{sha[:10]}[/cyan]"


def _labels() -> dict[str, str]:
    from latris.operations import nodes as node_ops

    return {e.id: e.label for e in node_ops.list_nodes()}


@app.command("element")
@handle_cli_errors
def element(
    target: str = typer.Argument(..., help="Node ID, ID prefix, or label."),
    kind: str = typer.Argument(..., help="initiating_event | functional_event | end_state"),
) -> None:
    """Give a factor its place in the event tree.

    The initiating event starts every sequence. A functional event is a
    heading: a question answered yes or no along the way (phrase it so
    "yes" reads naturally, e.g. "Gas detected", "Ignition"). End states are
    where sequences finish.
    """
    from latris.operations import event_tree as et

    target_id, sha = et.set_element(target, kind)
    if json_mode():
        emit({"target_id": target_id, "element": kind}, human=lambda: None, commit_sha=sha)
        return
    console.print(f"[green]set[/green] {escape(_labels().get(target_id, target_id[:15]))} → {kind} · {_sha(sha)}")


@app.command("order")
@handle_cli_errors
def order(headings: list[str] = typer.Argument(..., help="Every heading, left to right.")) -> None:
    """Set the order the headings are asked in, on every branch."""
    from latris.operations import event_tree as et

    store, sha = et.set_order(headings)
    if json_mode():
        emit(store, human=lambda: None, commit_sha=sha)
        return
    lab = _labels()
    console.print(f"[green]set[/green] heading order: {escape(' → '.join(lab[h] for h in store.headings))} · "
                  f"{_sha(sha)}")


@app.command("sequence")
@handle_cli_errors
def sequence(
    end_state: str = typer.Argument(..., help="The end state this sequence reaches."),
    answers: list[str] = typer.Argument(None, help="The answers on the way, each 'Heading=yes' or 'Heading=no'."),
) -> None:
    """Add a sequence: its answers in order, and the end state it reaches.

    Headings a branch never asks are left out. The same answers again
    replace the sequence's end state.
    """
    from latris.operations import event_tree as et

    seq, sha = et.set_sequence(end_state, et.parse_answers(answers or []))
    if json_mode():
        emit(seq, human=lambda: None, commit_sha=sha)
        return
    console.print(f"[green]set[/green] {escape(', '.join(answers or []) or '(start)')} → "
                  f"{escape(_labels().get(seq.end_state, ''))} · {_sha(sha)}")


@app.command("remove-sequence")
@handle_cli_errors
def remove_sequence(
    answers: list[str] = typer.Argument(..., help="The sequence's answers, each 'Heading=yes' or 'Heading=no'."),
) -> None:
    """Remove the sequence with exactly these answers."""
    from latris.operations import event_tree as et

    sha = et.remove_sequence(et.parse_answers(answers))
    emit({"removed": answers}, human=lambda: console.print(f"[green]removed[/green] sequence · {_sha(sha)}"),
         commit_sha=sha)


@app.command("probability")
@handle_cli_errors
def probability(
    heading: str = typer.Argument(..., help="A heading."),
    p_yes: float = typer.Argument(..., help="Probability the answer is yes, in [0, 1]."),
    given: list[str] = typer.Option(None, "--given", help="Only on branches with this earlier answer "
                                                          "('Heading=yes|no'); repeatable."),
    source: str = typer.Option(None, "--source", help="Where it came from (a reference, a fault-tree run, …)."),
    origin: str = typer.Option("human-direct", "--origin", help=ORIGIN_HELP),
    verified: bool = typer.Option(False, "--verified", help="A person has checked the value."),
    notes: str = typer.Option(None, "--notes"),
) -> None:
    """Set P(yes) for a heading — in general, or given earlier answers (the most specific match applies)."""
    from latris.operations import event_tree as et

    entry, sha = et.set_probability(heading, p_yes, given=et.parse_answers(given or []), origin=origin,  # type: ignore[arg-type]
                                    source_id=source, verification=verification(verified),
                                    notes=notes)
    if json_mode():
        emit(entry, human=lambda: None, commit_sha=sha)
        return
    cond = f" given {', '.join(given)}" if given else ""
    console.print(f"[green]set[/green] P({escape(_labels().get(entry.target_id, ''))}=yes{escape(cond)}) = "
                  f"{p_yes:g} · {_sha(sha)}")


@app.command("frequency")
@handle_cli_errors
def frequency(
    target: str = typer.Argument(..., help="The initiating event."),
    per_year: float = typer.Argument(..., help="How often it occurs, per year."),
    source: str = typer.Option(None, "--source", help="Where it came from (a reference, a bow-tie or fault-tree run)."),
    origin: str = typer.Option("human-direct", "--origin", help=ORIGIN_HELP),
    verified: bool = typer.Option(False, "--verified", help="A person has checked the value."),
    notes: str = typer.Option(None, "--notes"),
) -> None:
    """Set how often the initiating event occurs."""
    from latris.operations import event_tree as et

    entry, sha = et.set_frequency(target, per_year, origin=origin, source_id=source,  # type: ignore[arg-type]
                                  verification=verification(verified), notes=notes)
    if json_mode():
        emit(entry, human=lambda: None, commit_sha=sha)
        return
    console.print(f"[green]set[/green] {escape(_labels().get(entry.target_id, ''))}: {per_year:g}/year · "
                  f"{_sha(sha)}")


def _sequence_table(payload: dict, title: str) -> Table:
    t = Table(show_header=True, header_style="bold", title=title)
    t.add_column("#", justify="right")
    for h in payload["headings"]:
        t.add_column(h, justify="center")
    t.add_column("End state")
    t.add_column("Probability", justify="right")
    if payload.get("frequency"):
        t.add_column("Per year", justify="right")
    for r in payload["sequences"]:
        ans = {a["heading"]: a["answer"] for a in r["answers"]}
        cells = [str(r["n"])] + [ans.get(h, "·") for h in payload["headings"]]
        cells += [escape(r["end_state"]), f"{r['probability']:.3g}" if r["probability"] is not None else "—"]
        if payload.get("frequency"):
            cells.append(f"{r['frequency']:.3g}" if r["frequency"] is not None else "—")
        t.add_row(*cells)
    return t


@app.command("show")
@handle_cli_errors
def show() -> None:
    """Print the tree as its sequences (· = not asked on that branch)."""
    from latris.operations import event_tree as et

    payload = et.analyse()

    def human() -> None:
        for p in payload["problems"]:
            console.print(f"[yellow]![/yellow] {escape(p['label'])}: {escape(p['message'])}")
        if payload["sequences"]:
            console.print(_sequence_table(payload, f"From {payload['initiator']}"))

    emit(payload, human=human)


@app.command("check")
@handle_cli_errors
def check() -> None:
    """Check the tree is complete — every branch covered once. Exits 1 until it is."""
    from latris.operations.readiness import assess_readiness

    r = assess_readiness("event_tree")
    gaps = [{"element": g.element_label, "gap_type": g.gap_type, "message": g.message} for g in r.gaps]

    def human() -> None:
        if r.can_switch:
            console.print("[green]The event tree is complete.[/green]")
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
    """Each sequence's probability (and frequency), the totals per end state, and the dominant sequences."""
    from latris.operations import event_tree as et

    payload = et.analyse()
    sha = None
    if not no_record and not payload["problems"]:
        sha, payload["run_id"] = et.record(payload)

    def human() -> None:
        for p in payload["problems"]:
            console.print(f"[yellow]![/yellow] {escape(p['label'])}: {escape(p['message'])}")
        console.print(escape(et.describe(payload)) + ".\n")
        if payload["problems"]:
            return
        console.print(_sequence_table(payload, "Sequences"))
        if payload["quantified"]:
            t = Table(show_header=True, header_style="bold", title="End states")
            t.add_column("End state")
            t.add_column("Probability", justify="right")
            if payload["frequency"]:
                t.add_column("Per year", justify="right")
            t.add_column("Dominant sequence")
            for d in payload["end_states"]:
                share = d["dominant"]["share"]
                dom = f"#{d['dominant']['n']} ({share:.0%})" if share is not None else "—"
                row = [escape(d["end_state"]), f"{d['probability']:.3g}"]
                if payload["frequency"]:
                    row.append(f"{d['frequency']:.3g}")
                t.add_row(*row, dom)
            console.print(t)
            weak = sorted({v["heading"] for v in payload["values"] if v["weak"]})
            if weak:
                console.print(f"Values nobody has verified: {escape(', '.join(weak))}")
        if payload["missing"]:
            console.print("Not quantified — missing: " + escape("; ".join(payload["missing"])))
        if sha:
            console.print(f"\nrecorded · {_sha(sha)}")

    emit(payload, human=human, commit_sha=sha)


from latris.cli import _risk_mc as _risk_mc_cmds  # noqa: E402

_risk_mc_cmds.register(app, "event_tree")
