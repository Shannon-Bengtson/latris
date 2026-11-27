"""Argument map CLI — conclusion and claims, links (supports / attacks), assessments, show, check, analyse."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from latris.cli._errors import handle_cli_errors
from latris.cli._options import ORIGIN_HELP, verification
from latris.cli._output import emit

app = typer.Typer(help="Argument maps: does the conclusion stand, and what does it rest on?", no_args_is_help=True)

# Where each command sits in the workflow (schema/workflow.py; rules in docs/engineering/WORKFLOW_STRUCTURE.md).
PLACE = {
    "element": "formalise.definitions",
    "link": "formalise.definitions",
    "claim": "formalise.values",
    "show": "formalise",
    "check": "validation",
    "analyse": "analyse.base_case",
}
console = Console()
_STYLE = {"in": "green", "out": "red", "undecided": "yellow"}


def _sha(sha: str) -> str:
    return f"commit [cyan]{sha[:10]}[/cyan]"


@app.command("element")
@handle_cli_errors
def element(
    target: str = typer.Argument(..., help="Node ID, ID prefix, or label."),
    kind: str = typer.Argument(..., help="conclusion | claim | question"),
) -> None:
    """Make a factor the conclusion (what is argued for), a claim (a premise, objection or answer) or the
    question the conclusion answers. A claim's grounds are its citations: `latris evidence add <claim>
    description <key>`."""
    from latris.operations import argument_map as am

    target_id, sha = am.set_element(target, kind)
    emit({"target_id": target_id, "element": kind},
         human=lambda: console.print(f"[green]set[/green] {escape(target)} → {kind} · {_sha(sha)}"), commit_sha=sha)


@app.command("link")
@handle_cli_errors
def link(
    link_: str = typer.Argument(..., metavar="LINK",
                                help="'Premise -> Claim' (add the link first: `latris edge add`)."),
    relation: str = typer.Option(None, "--relation", "-r", help="supports (default) | attacks — an objection."),
    reason: str = typer.Option(None, "--reason", help="A name shared by premises that only work together (a "
                                                      "linked reason); leave out for a reason that stands alone."),
    warrant: str = typer.Option(None, "--warrant", help="Why the premise bears on the claim."),
    qualifier: str = typer.Option(None, "--qualifier", help="certainly | probably | possibly."),
    notes: str = typer.Option(None, "--notes"),
    source: str = typer.Option(None, "--source", help="Source ID for the inference."),
    origin: str = typer.Option(None, "--origin", help=ORIGIN_HELP),
    verified: bool = typer.Option(False, "--verified", help="A person has reviewed this link."),
) -> None:
    """Say how a premise bears on a claim: supports it or attacks it, which reason it belongs to, and why.

    Premises in one reason only work together ("it works *and* we can
    afford it"); give them the same --reason. An objection to an
    objection is a rebuttal: it attacks the objection. To object to the
    inference itself rather than a premise, open a challenge on the link
    (`latris challenge open "Premise -> Claim" ...`).
    """
    from latris.operations import argument_map as am

    given = {"relation": relation, "reason": reason, "warrant": warrant, "qualifier": qualifier, "notes": notes,
             "source_id": source, "origin": origin}
    kwargs = {k: v for k, v in given.items() if v is not None}
    if verified:
        kwargs["verification"] = verification(True)
    entry, sha = am.set_link(link_, **kwargs)
    emit(entry, human=lambda: console.print(f"[green]set[/green] {escape(link_)}: {entry.relation}"
                                            + (f" (reason {escape(entry.reason)})" if entry.reason else "")
                                            + f" · {_sha(sha)}"), commit_sha=sha)


@app.command("claim")
@handle_cli_errors
def claim(
    target: str = typer.Argument(..., help="A claim."),
    assessment: str = typer.Argument(..., help="accepted | rejected | none (clear it)."),
    rationale: str = typer.Option(None, "--rationale", help="Why."),
    source: str = typer.Option(None, "--source"),
    verified: bool = typer.Option(False, "--verified", help="A person has reviewed this assessment."),
) -> None:
    """A person's assessment of a claim the map takes as given: accepted, or rejected (it then counts as
    defeated)."""
    from latris.operations import argument_map as am

    entry, sha = am.set_claim(target, assessment=None if assessment == "none" else assessment, rationale=rationale,
                              source_id=source, verification=verification(verified))
    emit(entry, human=lambda: console.print(f"[green]set[/green] {escape(target)}: {entry.assessment or 'not assessed'}"
                                            f" · {_sha(sha)}"), commit_sha=sha)


@app.command("show")
@handle_cli_errors
def show() -> None:
    """Print the map: each claim with what supports and attacks it, and its status."""
    from latris.operations import argument_map as am

    m = am.load()
    lab = am.label(m) if not m.problems else {}
    rows = []
    for c in m.claims:
        rows.append({"claim": m.labels[c], "role": m.kind[c], "status": lab.get(c),
                     "supports": [" + ".join(m.labels[ln.premise] for ln in g) for g in m.reasons(c).values()],
                     "attacks": [m.labels[ln.premise] for ln in m.attacks(c)]})

    def human() -> None:
        t = Table(show_header=True, header_style="bold")
        for col in ("Claim", "Status", "Reasons", "Objections"):
            t.add_column(col)
        for r in rows:
            st = r["status"]
            t.add_row(("[bold]" + escape(r["claim"]) + "[/bold]") if r["role"] == "conclusion" else escape(r["claim"]),
                      f"[{_STYLE[st]}]{st}[/{_STYLE[st]}]" if st else "—",
                      escape("; ".join(r["supports"])) or "—", escape("; ".join(r["attacks"])) or "—")
        console.print(t)
        for p in m.problems:
            console.print(f"[yellow]![/yellow] {escape(m.labels.get(p.target_id or '', '(map)'))}: {escape(p.message)}")

    emit({"claims": rows, "problems": [p.message for p in m.problems]}, human=human)


@app.command("check")
@handle_cli_errors
def check() -> None:
    """Check there is one conclusion and something argues for or against it. Exits 1 until there is."""
    from latris.operations.readiness import assess_readiness

    r = assess_readiness("argument_map")
    gaps = [{"element": g.element_label, "gap_type": g.gap_type, "message": g.message} for g in r.gaps]

    def human() -> None:
        if r.can_switch:
            console.print("[green]The argument map is ready to evaluate.[/green]")
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
    """Does the conclusion stand? Its reasons, unanswered objections, linchpins, and what the premises rest on."""
    from latris.operations import argument_map as am
    from latris.operations.formalisms.argument_map import _BASIS

    payload = am.analyse()
    sha = None
    if not no_record and not payload["problems"]:
        sha, payload["run_id"] = am.record(payload)

    def human() -> None:
        for p in payload["problems"]:
            console.print(f"[yellow]![/yellow] {escape(p['label'])}: {escape(p['message'])}")
        console.print(escape(am.describe(payload)) + ".\n")
        if payload["problems"]:
            return
        t = Table(show_header=True, header_style="bold", title="Claims")
        for col in ("Claim", "Status", "Grounds"):
            t.add_column(col)
        for c in payload["claims"]:
            st = c["status"]
            t.add_row(escape(c["claim"]), f"[{_STYLE[st]}]{st}[/{_STYLE[st]}]",
                      _BASIS.get(c["basis"], c["basis"]) if c["given"] else "argued")
        console.print(t)
        for o in payload["objections"]:
            tag = "answered" if o["answered"] else "[red]unanswered[/red]"
            console.print(f"Objection: {escape(o['objection'])} → {escape(o['against'])} ({tag})")
        for x in payload["linchpins"]:
            console.print(f"[bold]Linchpin:[/bold] {escape(x['claim'])} — {_BASIS.get(x['basis'], x['basis'])}")
        if sha:
            console.print(f"\nrecorded · {_sha(sha)}")

    emit(payload, human=human, commit_sha=sha)
