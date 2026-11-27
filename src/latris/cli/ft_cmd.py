"""Fault tree CLI — event types, gates, probabilities, check, analyse."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from latris.cli._errors import handle_cli_errors
from latris.cli._options import ORIGIN_HELP, verification
from latris.cli._output import emit, json_mode

app = typer.Typer(help="Fault tree operations.", no_args_is_help=True)

# Where each command sits in the workflow (schema/workflow.py; rules in docs/engineering/WORKFLOW_STRUCTURE.md).
PLACE = {
    "event": "formalise.definitions",
    "gate": "formalise.definitions",
    "probability": "formalise.values",
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


@app.command("event")
@handle_cli_errors
def event(
    target: str = typer.Argument(..., help="Node ID, ID prefix, or label."),
    event_type: str = typer.Argument(..., help="top_event | intermediate_event | basic_event | undeveloped_event"),
) -> None:
    """Give a factor its type in the fault tree.

    The top event is the undesired event the tree explains. Intermediate
    events combine their inputs through a gate. Basic events are the leaves
    you give probabilities to; undeveloped events are leaves not broken down
    further. Link each input to the event it feeds (`latris edge add <input>
    <event> --kind logical`, or a causal link).
    """
    from latris.operations import fault_tree as ft

    target_id, sha = ft.set_event(target, event_type)
    if json_mode():
        emit({"target_id": target_id, "event_type": event_type}, human=lambda: None, commit_sha=sha)
        return
    console.print(f"[green]set[/green] {escape(_labels().get(target_id, target_id[:15]))} → {event_type} · {_sha(sha)}")


@app.command("gate")
@handle_cli_errors
def gate(
    target: str = typer.Argument(..., help="A top or intermediate event."),
    kind: str = typer.Argument(..., help="and | or | vote"),
    k: int = typer.Option(None, "--k", "-k", help="For vote: at least k of the inputs must occur."),
) -> None:
    """Say how a top or intermediate event's inputs combine.

    and: all of them must occur. or: any one is enough. vote: at least k of
    them (a k-out-of-n gate, e.g. 2-out-of-3 redundant supplies).
    """
    from latris.operations import fault_tree as ft

    entry, sha = ft.set_gate(target, kind, k=k)
    if json_mode():
        emit(entry, human=lambda: None, commit_sha=sha)
        return
    shown = f"vote {k}-of-n" if kind == "vote" else kind.upper()
    console.print(f"[green]set[/green] {escape(_labels().get(entry.target_id, ''))} gate → {shown} · {_sha(sha)}")


@app.command("probability")
@handle_cli_errors
def probability(
    target: str = typer.Argument(..., help="A basic or undeveloped event."),
    value: float = typer.Argument(..., help="Probability in [0, 1] over the period the tree is about."),
    source: str = typer.Option(None, "--source", help="Where it came from (a reference key, dataset, …)."),
    origin: str = typer.Option(
        "human-direct", "--origin", help=ORIGIN_HELP
    ),
    verified: bool = typer.Option(False, "--verified", help="A person has checked this value against its source."),
    notes: str = typer.Option(None, "--notes", help="e.g. the failure rate and exposure time it came from."),
) -> None:
    """Set a basic or undeveloped event's probability, with its provenance."""
    from latris.operations import fault_tree as ft

    entry, sha = ft.set_probability(target, value, origin=origin, source_id=source,  # type: ignore[arg-type]
                                    verification=verification(verified), notes=notes)
    if json_mode():
        emit(entry, human=lambda: None, commit_sha=sha)
        return
    console.print(f"[green]set[/green] P({escape(_labels().get(entry.target_id, ''))}) = {value:g} · {_sha(sha)}")


@app.command("show")
@handle_cli_errors
def show() -> None:
    """Print the tree from the top event down, with gates and probabilities."""
    from latris.operations import fault_tree as ft

    tree = ft.load_tree()
    lab = tree.labels
    parents: dict[str, int] = {}
    for ins in tree.inputs.values():
        for i in ins:
            parents[i] = parents.get(i, 0) + 1

    def node_dict(eid: str, seen: frozenset[str]) -> dict:
        g = tree.gates.get(eid)
        p = tree.probabilities.get(eid)
        d = {"event": lab[eid], "type": tree.events[eid],
             "gate": (f"vote {g.k}" if g.gate == "vote" else g.gate) if g else None,
             "probability": p.probability if p else None, "shared": parents.get(eid, 0) > 1, "inputs": []}
        if eid not in seen:
            d["inputs"] = [node_dict(i, seen | {eid}) for i in tree.inputs.get(eid, [])]
        return d

    data = {"tree": node_dict(tree.top, frozenset()) if tree.top else None,
            "problems": [f"{lab.get(p.target_id or '', '(tree)')}: {p.message}" for p in tree.problems]}

    def human() -> None:
        if not data["tree"]:
            console.print("[dim](no top event yet — `latris ft event <factor> top_event`)[/dim]")
        else:
            def walk(d: dict, depth: int) -> None:
                bits = []
                if d["gate"]:
                    bits.append(f"[bold]{d['gate'].upper()}[/bold]")
                if d["probability"] is not None:
                    bits.append(f"p={d['probability']:g}")
                if d["type"] == "undeveloped_event":
                    bits.append("[dim]undeveloped[/dim]")
                if d["shared"]:
                    bits.append("[dim]shared: feeds more than one gate[/dim]")
                tag = f"  ({', '.join(bits)})" if bits else ""
                console.print("  " * depth + ("└ " if depth else "") + escape(d["event"]) + tag)
                for c in d["inputs"]:
                    walk(c, depth + 1)

            walk(data["tree"], 0)
        for p in data["problems"]:
            console.print(f"[yellow]![/yellow] {escape(p)}")

    emit(data, human=human)


@app.command("check")
@handle_cli_errors
def check() -> None:
    """Check the tree's structure. Exits 1 until it is complete."""
    from latris.operations.readiness import assess_readiness

    r = assess_readiness("fault_tree")
    gaps = [{"element": g.element_label, "gap_type": g.gap_type, "message": g.message} for g in r.gaps]

    def human() -> None:
        if r.can_switch:
            console.print("[green]The fault tree is complete.[/green]")
        for g in gaps:
            console.print(f"  - {escape(g['element'])}: {escape(g['message'])}")

    emit({"ready": r.can_switch, "gaps": gaps}, human=human)
    if not r.can_switch:
        raise typer.Exit(1)


@app.command("analyse")
@handle_cli_errors
def analyse(
    max_order: int = typer.Option(None, "--max-order", help="List cut sets only up to this many events."),
    no_record: bool = typer.Option(False, "--no-record", help="Show the result without recording it for reports."),
) -> None:
    """Minimal cut sets, single points of failure and — once every leaf has a probability — the
    exact top-event probability and each event's importance.

    Importance: Fussell–Vesely is the share of the top-event probability
    that needs the event; Birnbaum how much the top event's probability
    moves with it; RAW how many times likelier the top event becomes if it
    occurs. Values a person hasn't verified are flagged weak.
    """
    from latris.operations import fault_tree as ft

    payload = ft.analyse(max_order=max_order)
    sha = run_id = None
    if not no_record and not payload["problems"] and not payload["error"]:
        sha, run_id = ft.record(payload)
        payload["run_id"] = run_id

    def human() -> None:
        for p in payload["problems"]:
            console.print(f"[yellow]![/yellow] {escape(p['label'])}: {escape(p['message'])}")
        for o in payload["outside_inputs"]:
            console.print(f"[dim]left out (not in the tree): {escape(o)}[/dim]")
        console.print(escape(ft.describe(payload)) + ".\n")
        if payload["quantified"]:
            pr = payload["probability"]
            console.print(f"Top-event probability: [bold]{pr['exact']:.4g}[/bold] (exact) · rare-event "
                          f"approximation {pr['rare_event']:.4g} · min-cut upper bound "
                          f"{pr['min_cut_upper_bound']:.4g}\n")
        if payload["cut_sets"]:
            t = Table(show_header=True, header_style="bold", title="Minimal cut sets")
            t.add_column("Events")
            t.add_column("Order", justify="right")
            t.add_column("Probability", justify="right")
            for c in payload["cut_sets"][:20]:
                t.add_row(escape(" AND ".join(c["events"])), str(c["order"]),
                          f"{c['probability']:.3g}" if c["probability"] is not None else "—")
            console.print(t)
            if payload["cut_sets_total"] > 20:
                console.print(f"[dim]…and {payload['cut_sets_total'] - 20} more (--json lists up to 200)[/dim]")
        if payload["importance"]:
            t = Table(show_header=True, header_style="bold", title="Importance (by Fussell–Vesely)")
            for col in ("Event", "p", "Fussell–Vesely", "Birnbaum", "RAW", "Provenance"):
                t.add_column(col, justify="left" if col in ("Event", "Provenance") else "right")
            for i in payload["importance"]:
                prov = f"{i['origin']}" + (f", {i['source']}" if i["source"] else "")
                prov += " · [yellow]weak[/yellow]" if i["weak"] else " · verified"
                t.add_row(escape(i["event"]), f"{i['probability']:.3g}", f"{i['fussell_vesely']:.3f}",
                          f"{i['birnbaum']:.3g}", f"{i['raw']:.3g}" if i["raw"] is not None else "—", prov)
            console.print(t)
        if payload["missing_probabilities"]:
            console.print("No probability yet: " + escape(", ".join(payload["missing_probabilities"])))
        if sha:
            console.print(f"\nrecorded · {_sha(sha)}")

    emit(payload, human=human, commit_sha=sha)


from latris.cli import _risk_mc as _risk_mc_cmds  # noqa: E402

_risk_mc_cmds.register(app, "fault_tree")
