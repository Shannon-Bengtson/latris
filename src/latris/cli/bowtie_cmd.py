"""Bow-tie CLI — elements, barriers, threat frequencies, show, check, analyse."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from latris.cli._errors import handle_cli_errors
from latris.cli._options import ORIGIN_HELP, verification
from latris.cli._output import emit, json_mode

app = typer.Typer(help="Bow-tie (threats, barriers, consequences) operations.", no_args_is_help=True)
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
    kind: str = typer.Argument(..., help="hazard | top_event | threat | consequence | barrier | escalation_factor"),
) -> None:
    """Give a factor its place in the bow-tie.

    The top event is the moment control of the hazard is lost. Threats cause
    it; consequences follow it. Draw each line with ordinary links: threat →
    barrier → … → top event, and top event → barrier → … → consequence. An
    escalation factor degrades a barrier: link it (through any barriers that
    control it) to the barrier it degrades.
    """
    from latris.operations import bow_tie as bt

    target_id, sha = bt.set_element(target, kind)
    if json_mode():
        emit({"target_id": target_id, "element": kind}, human=lambda: None, commit_sha=sha)
        return
    console.print(f"[green]set[/green] {escape(_labels().get(target_id, target_id[:15]))} → {kind} · {_sha(sha)}")


@app.command("barrier")
@handle_cli_errors
def barrier(
    target: str = typer.Argument(..., help="A barrier."),
    barrier_type: str = typer.Option(
        None, "--type", help="passive_hardware | active_hardware | active_hardware_human | human"
    ),
    status: str = typer.Option(None, "--status", help="in_place | degraded | not_in_place"),
    owner: str = typer.Option(None, "--owner", help="Who is accountable for it."),
    pfd: float = typer.Option(None, "--pfd", help="Probability it fails when called on, in [0, 1]."),
    source: str = typer.Option(None, "--source", help="Where the failure probability came from."),
    origin: str = typer.Option(
        None, "--origin", help=ORIGIN_HELP
    ),
    verified: bool = typer.Option(None, "--verified/--unverified", help="A person has checked the value."),
    notes: str = typer.Option(None, "--notes"),
) -> None:
    """Set a barrier's type, status, owner, failure probability or provenance (only what you give changes)."""
    from latris.operations import bow_tie as bt

    given = {"barrier_type": barrier_type, "status": status, "owner": owner, "pfd": pfd, "source_id": source,
             "origin": origin, "notes": notes}
    kwargs = {k: v for k, v in given.items() if v is not None}
    if verified is not None:
        kwargs["verification"] = verification(verified)
    entry, sha = bt.set_barrier(target, **kwargs)
    if json_mode():
        emit(entry, human=lambda: None, commit_sha=sha)
        return
    console.print(f"[green]set[/green] barrier {escape(_labels().get(entry.target_id, ''))}: "
                  f"{', '.join(kwargs)} · {_sha(sha)}")


@app.command("frequency")
@handle_cli_errors
def frequency(
    target: str = typer.Argument(..., help="A threat."),
    per_year: float = typer.Argument(..., help="How often it occurs, per year."),
    source: str = typer.Option(None, "--source", help="Where it came from (a reference key, a fault-tree run, …)."),
    origin: str = typer.Option(
        "human-direct", "--origin", help=ORIGIN_HELP
    ),
    verified: bool = typer.Option(False, "--verified", help="A person has checked the value."),
    notes: str = typer.Option(None, "--notes"),
) -> None:
    """Set how often a threat occurs, with its provenance."""
    from latris.operations import bow_tie as bt

    entry, sha = bt.set_frequency(target, per_year, origin=origin, source_id=source,  # type: ignore[arg-type]
                                  verification=verification(verified), notes=notes)
    if json_mode():
        emit(entry, human=lambda: None, commit_sha=sha)
        return
    console.print(f"[green]set[/green] {escape(_labels().get(entry.target_id, ''))}: {per_year:g}/year · "
                  f"{_sha(sha)}")


def _barrier_text(name: str, by: dict) -> str:
    b = by.get(name, {})
    bits = []
    if b.get("status") and b["status"] != "in_place":
        bits.append(b["status"].replace("_", " "))
    if b.get("pfd") is not None:
        bits.append(f"pfd {b['pfd']:g}")
    return f"[{name}{' — ' + ', '.join(bits) if bits else ''}]"


@app.command("show")
@handle_cli_errors
def show() -> None:
    """Print the bow-tie line by line."""
    from latris.operations import bow_tie as bt

    payload = bt.analyse()

    def human() -> None:
        for p in payload["problems"]:
            console.print(f"[yellow]![/yellow] {escape(p['label'])}: {escape(p['message'])}")
        if payload["problems"]:
            return
        by = {b["barrier"]: b for b in payload["barriers"]}
        if payload["hazard"]:
            console.print(f"Hazard: {escape(payload['hazard'])}")
        console.print(f"Top event: [bold]{escape(payload['top'])}[/bold]\n")
        for side, title in (("prevention", "Prevention (threat → top event)"),
                            ("mitigation", "Mitigation (top event → consequence)")):
            console.print(f"[bold]{title}[/bold]")
            for ln in payload["lines"]:
                if ln["side"] == side:
                    mid = " → ".join(_barrier_text(b, by) for b in ln["barriers"]) or "[red](no barrier)[/red]"
                    console.print(f"  {escape(ln['from'])} → {escape(mid) if ln['barriers'] else mid} → "
                                  f"{escape(ln['to'])}")
            console.print()
        if payload["escalation"]:
            console.print("[bold]Escalation factors[/bold]")
            for e in payload["escalation"]:
                ctrl = escape(" → ".join(f"[{c}]" for c in e["controls"])) or "[red](no control)[/red]"
                console.print(f"  {escape(e['factor'])} → {ctrl} → degrades {escape(e['degrades'])}")

    emit(payload, human=human)


@app.command("check")
@handle_cli_errors
def check() -> None:
    """Check the bow-tie's structure. Exits 1 until it is complete."""
    from latris.operations.readiness import assess_readiness

    r = assess_readiness("bow_tie")
    gaps = [{"element": g.element_label, "gap_type": g.gap_type, "message": g.message} for g in r.gaps]

    def human() -> None:
        if r.can_switch:
            console.print("[green]The bow-tie is complete.[/green]")
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
    """Lines and their effective barriers, what weakens them, and — once every threat has a frequency and
    every barrier a failure probability — the top-event and consequence frequencies (layer of protection).

    RAW per barrier: how many times more often the top event (prevention) or
    its consequences (mitigation) would happen if the barrier always failed.
    """
    from latris.operations import bow_tie as bt

    payload = bt.analyse()
    sha = None
    if not no_record and not payload["problems"]:
        sha, payload["run_id"] = bt.record(payload)

    def human() -> None:
        for p in payload["problems"]:
            console.print(f"[yellow]![/yellow] {escape(p['label'])}: {escape(p['message'])}")
        for o in payload["outside_inputs"]:
            console.print(f"[dim]left out (not in the bow-tie): {escape(o)}[/dim]")
        console.print(escape(bt.describe(payload)) + ".\n")
        if payload["problems"]:
            return
        f = bt.flags(payload)
        for key, title in (("unprotected", "No effective barrier"), ("single_barrier", "Resting on one barrier"),
                           ("shared", "Barriers on more than one line (one failure takes them all)"),
                           ("uncontrolled_escalation", "Escalation factors with no control"),
                           ("not_in_place", "Barriers degraded or not in place"),
                           ("no_owner", "Barriers with no owner")):
            if f[key]:
                console.print(f"[bold]{title}:[/bold] {escape(', '.join(f[key]))}")
        if payload["quantified"]:
            fr = payload["frequency"]
            console.print(f"\nTop-event frequency: [bold]{fr['top']:.3g}[/bold] per year")
            for c, v in fr["consequences"].items():
                console.print(f"  {escape(c)}: {v:.3g} per year")
        t = Table(show_header=True, header_style="bold", title="Barriers (most buy first)")
        for col in ("Barrier", "Side", "PFD", "Lines", "RAW", "Owner", "Value"):
            t.add_column(col, justify="right" if col in ("PFD", "Lines", "RAW") else "left")
        for b in payload["barriers"]:
            value = "[yellow]weak[/yellow]" if b["weak"] else "verified"
            value += f" ({escape(b['source'])})" if b["source"] else ""
            t.add_row(escape(b["barrier"]), {"prevention": "prev", "mitigation": "mitig"}.get(b["side"], "control"),
                      f"{b['pfd']:g}" if b["pfd"] is not None else "—", str(b["lines"]),
                      f"{b['raw']:.3g}" if b["raw"] is not None else "—", escape(b["owner"] or "—"), value)
        console.print()
        console.print(t)
        if payload["missing"]:
            console.print("Not quantified — missing: " + escape(", ".join(payload["missing"])))
        if sha:
            console.print(f"\nrecorded · {_sha(sha)}")

    emit(payload, human=human, commit_sha=sha)


from latris.cli import _risk_mc as _risk_mc_cmds  # noqa: E402

_risk_mc_cmds.register(app, "bow_tie")
