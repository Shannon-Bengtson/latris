"""MCDA CLI — options, criteria (weight, direction, scale), scores, show, check, analyse."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from latris.cli._errors import handle_cli_errors
from latris.cli._output import emit

app = typer.Typer(help="Multi-criteria decision analysis: options against weighted criteria.", no_args_is_help=True)
console = Console()
_ORIGINS = "human-direct | human-elicited | ai-proposed | data-derived | imported | mixed"


def _sha(sha: str) -> str:
    return f"commit [cyan]{sha[:10]}[/cyan]"


@app.command("element")
@handle_cli_errors
def element(
    target: str = typer.Argument(..., help="Node ID, ID prefix, or label."),
    kind: str = typer.Argument(..., help="option | criterion"),
) -> None:
    """Make a factor an option (something you could choose) or a criterion (something options are judged on)."""
    from latris.operations import mcda

    target_id, sha = mcda.set_element(target, kind)
    emit({"target_id": target_id, "element": kind},
         human=lambda: console.print(f"[green]set[/green] {escape(target)} → {kind} · {_sha(sha)}"), commit_sha=sha)


@app.command("criterion")
@handle_cli_errors
def criterion(
    target: str = typer.Argument(..., help="A criterion."),
    weight: float = typer.Option(None, "--weight", help="Swing weight (any positive number; normalised)."),
    direction: str = typer.Option(None, "--direction", help="higher | lower — which is better."),
    worst: float = typer.Option(None, "--worst", help="The scale's worst value (give with --best)."),
    best: float = typer.Option(None, "--best", help="The scale's best value (give with --worst)."),
    units: str = typer.Option(None, "--units"),
    source: str = typer.Option(None, "--source", help="Whose judgement or which document the weight comes from."),
    origin: str = typer.Option(None, "--origin", help=_ORIGINS),
    verified: bool = typer.Option(None, "--verified/--unverified", help="A person has checked it."),
    notes: str = typer.Option(None, "--notes"),
) -> None:
    """Set a criterion's swing weight, direction and scale (only what you give changes).

    A swing weight says how much moving from the worst to the best of this
    criterion's scale matters, compared with the other criteria's swings —
    so set the scale first. Without --worst/--best the options' own range
    is used, which shifts when an option is added.
    """
    from latris.operations import mcda

    given = {"weight": weight, "direction": direction, "worst": worst, "best": best, "units": units,
             "source_id": source, "origin": origin, "notes": notes}
    kwargs = {k: v for k, v in given.items() if v is not None}
    if verified is not None:
        kwargs["verification"] = "human-verified" if verified else "unverified"
    entry, sha = mcda.set_criterion(target, **kwargs)
    emit(entry, human=lambda: console.print(f"[green]set[/green] criterion {escape(target)}: {', '.join(kwargs)} · "
                                            f"{_sha(sha)}"), commit_sha=sha)


@app.command("score")
@handle_cli_errors
def score(
    option: str = typer.Argument(..., help="An option."),
    criterion: str = typer.Argument(..., help="A criterion."),
    value: float = typer.Argument(..., help="The option's performance, in the criterion's units."),
    source: str = typer.Option(None, "--source"),
    origin: str = typer.Option("human-direct", "--origin", help=_ORIGINS),
    verified: bool = typer.Option(False, "--verified", help="A person has checked it against its source."),
    notes: str = typer.Option(None, "--notes"),
) -> None:
    """Set an option's score on a criterion, with where it came from."""
    from latris.operations import mcda

    entry, sha = mcda.set_score(option, criterion, value, origin=origin, source_id=source,  # type: ignore[arg-type]
                                verification="human-verified" if verified else "unverified", notes=notes)
    emit(entry, human=lambda: console.print(f"[green]set[/green] {escape(option)} on {escape(criterion)} = {value:g} · "
                                            f"{_sha(sha)}"), commit_sha=sha)


@app.command("show")
@handle_cli_errors
def show() -> None:
    """Print the performance matrix (options × criteria) and the weights."""
    from latris.operations import mcda

    m = mcda.load()
    lab = m.labels
    data = {"options": [lab[o] for o in m.options], "criteria": [
        {"criterion": lab[c], **(m.settings[c].model_dump(include={"weight", "direction", "worst", "best", "units"})
                                 if c in m.settings else {})} for c in m.criteria],
        "scores": {lab[o]: {lab[c]: m.scores[(o, c)].value for c in m.criteria if (o, c) in m.scores}
                   for o in m.options}}

    def human() -> None:
        t = Table(show_header=True, header_style="bold")
        t.add_column("Option")
        for c in m.criteria:
            s = m.settings.get(c)
            sub = []
            if s and s.weight is not None:
                sub.append(f"w {s.weight:g}")
            if s and s.direction:
                sub.append("↑" if s.direction == "higher" else "↓")
            t.add_column(f"{lab[c]}\n{' '.join(sub)}", justify="right")
        for o in m.options:
            t.add_row(escape(lab[o]), *(f"{m.scores[(o, c)].value:g}" if (o, c) in m.scores else "[red]—[/red]"
                                         for c in m.criteria))
        console.print(t)
        for p in m.problems:
            console.print(f"[yellow]![/yellow] {escape(lab.get(p.target_id or '', '(model)'))}: {escape(p.message)}")

    emit(data, human=human)


@app.command("check")
@handle_cli_errors
def check() -> None:
    """Check every criterion has a weight and direction and every option a score on each. Exits 1 until so."""
    from latris.operations.readiness import assess_readiness

    r = assess_readiness("mcda")
    gaps = [{"element": g.element_label, "gap_type": g.gap_type, "message": g.message} for g in r.gaps]

    def human() -> None:
        if r.can_switch:
            console.print("[green]The MCDA is complete.[/green]")
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
    """Rank the options, show each criterion's contribution, dominated options, and how far each weight would
    have to move before the top choice changes."""
    from latris.operations import mcda
    from latris.operations.formalisms.mcda import _reversal_lines

    payload = mcda.analyse()
    sha = None
    if not no_record and not payload["problems"]:
        sha, payload["run_id"] = mcda.record(payload)

    def human() -> None:
        for p in payload["problems"]:
            console.print(f"[yellow]![/yellow] {escape(p['label'])}: {escape(p['message'])}")
        console.print(escape(mcda.describe(payload)) + ".\n")
        if payload["problems"]:
            return
        t = Table(show_header=True, header_style="bold", title="Ranking (points of 100, by criterion)")
        t.add_column("Option")
        t.add_column("Total", justify="right")
        for c in payload["criteria"]:
            t.add_column(c, justify="right")
        for r in payload["ranking"]:
            t.add_row(escape(r["option"]), f"{r['total']:.1f}", *(f"{r['contributions'][c]:.1f}"
                                                                    for c in payload["criteria"]))
        console.print(t)
        console.print("[bold]Weights, and how far each would have to move to change the top choice:[/bold]")
        for line in _reversal_lines(payload):
            console.print(f"  {escape(line)}")
        if payload["dominated"]:
            console.print("Dominated: " + escape("; ".join(f"{d['option']} (by {d['by']})"
                                                           for d in payload["dominated"])))
        m = payload["margin"]
        if m and m["unverified_scores"]:
            console.print(f"[yellow]The margin rests on unverified scores:[/yellow] "
                          f"{escape(', '.join(m['unverified_scores']))}")
        if payload["flat"]:
            console.print("[yellow]Every option scores the same on:[/yellow] "
                          f"{escape(', '.join(payload['flat']))} — it can't separate them.")
        if payload["outside"]:
            console.print("[yellow]Scores outside the stated scale (clamped to its end):[/yellow] "
                          f"{escape(', '.join(payload['outside']))}")
        if any(w["local_scale"] for w in payload["weights"]):
            console.print("[dim]Some criteria use the options' own range as their scale; adding an option shifts it "
                          "and the weights would need revisiting (set --worst/--best).[/dim]")
        if sha:
            console.print(f"\nrecorded · {_sha(sha)}")

    emit(payload, human=human, commit_sha=sha)
