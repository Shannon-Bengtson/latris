"""Markov CLI — states, strategies, transitions, costs and utilities, start, settings, show, check, analyse."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from latris.cli._errors import handle_cli_errors
from latris.cli._options import ORIGIN_HELP, verification
from latris.cli._output import emit

app = typer.Typer(help="Markov cohort models: costs and outcomes over time, and cost-effectiveness.",
                  no_args_is_help=True)
console = Console()


def _sha(sha: str) -> str:
    return f"commit [cyan]{sha[:10]}[/cyan]"


@app.command("element")
@handle_cli_errors
def element(
    target: str = typer.Argument(..., help="Node ID, ID prefix, or label."),
    kind: str = typer.Argument(..., help="state | strategy"),
) -> None:
    """Make a factor a state the cohort can be in (Healthy, Sick, Dead) or a strategy being compared
    (Standard care, New drug). Transitions are ordinary links between states."""
    from latris.operations import markov

    target_id, sha = markov.set_element(target, kind)
    emit({"target_id": target_id, "element": kind},
         human=lambda: console.print(f"[green]set[/green] {escape(target)} → {kind} · {_sha(sha)}"), commit_sha=sha)


@app.command("transition")
@handle_cli_errors
def transition(
    link: str = typer.Argument(..., help="'From state -> To state' (an existing link)."),
    probability: float = typer.Argument(..., help="Probability of moving along it in one cycle."),
    strategy: str = typer.Option(None, "--strategy", help="Only under this strategy (default: every strategy)."),
    source: str = typer.Option(None, "--source"),
    origin: str = typer.Option("human-direct", "--origin", help=ORIGIN_HELP),
    verified: bool = typer.Option(False, "--verified"),
    notes: str = typer.Option(None, "--notes"),
) -> None:
    """Set a per-cycle transition probability. Whatever doesn't leave a state stays in it."""
    from latris.operations import markov

    entry, sha = markov.set_transition(link, probability, strategy=strategy, origin=origin,  # type: ignore[arg-type]
                                       source_id=source, notes=notes,
                                       verification=verification(verified))
    emit(entry, human=lambda: console.print(f"[green]set[/green] {escape(link)} = {probability:g}"
                                            + (f" under {escape(strategy)}" if strategy else "") + f" · {_sha(sha)}"),
         commit_sha=sha)


@app.command("reward")
@handle_cli_errors
def reward(
    state: str = typer.Argument(..., help="A state."),
    cost: float = typer.Option(None, "--cost", help="Cost per cycle in this state."),
    utility: float = typer.Option(None, "--utility", help="Utility weight per year (1 = full health, 0 = dead)."),
    strategy: str = typer.Option(None, "--strategy", help="Only under this strategy (default: every strategy)."),
    source: str = typer.Option(None, "--source"),
    origin: str = typer.Option(None, "--origin", help=ORIGIN_HELP),
    verified: bool = typer.Option(None, "--verified/--unverified"),
    notes: str = typer.Option(None, "--notes"),
) -> None:
    """Set a state's cost per cycle and/or utility (only what you give changes)."""
    from latris.operations import markov

    given = {"cost": cost, "utility": utility, "source_id": source, "origin": origin, "notes": notes}
    kwargs = {k: v for k, v in given.items() if v is not None}
    if verified is not None:
        kwargs["verification"] = verification(verified)
    entry, sha = markov.set_reward(state, strategy=strategy, **kwargs)
    emit(entry, human=lambda: console.print(f"[green]set[/green] {escape(state)}: {', '.join(kwargs)}"
                                            + (f" under {escape(strategy)}" if strategy else "") + f" · {_sha(sha)}"),
         commit_sha=sha)


@app.command("start")
@handle_cli_errors
def start(
    state: str = typer.Argument(..., help="A state."),
    proportion: float = typer.Argument(..., help="Share of the cohort starting here (all shares sum to 1)."),
) -> None:
    """Set where the cohort starts."""
    from latris.operations import markov

    entry, sha = markov.set_start(state, proportion)
    emit(entry, human=lambda: console.print(f"[green]set[/green] {proportion:g} of the cohort starts in "
                                            f"{escape(state)} · {_sha(sha)}"), commit_sha=sha)


@app.command("settings")
@handle_cli_errors
def settings(
    cycles: int = typer.Option(None, "--cycles", help="Number of cycles (the time horizon)."),
    cycle_length: float = typer.Option(None, "--cycle-length", help="Length of a cycle, in time units."),
    time_units: str = typer.Option(None, "--time-units", help="days | weeks | months | years"),
    discount: float = typer.Option(None, "--discount", help="Annual discount rate for costs, e.g. 0.035."),
    outcome_discount: float = typer.Option(None, "--outcome-discount", help="For outcomes (default: as costs)."),
    half_cycle: bool = typer.Option(None, "--half-cycle/--no-half-cycle", help="Half-cycle correction."),
    wtp: float = typer.Option(None, "--wtp", help="Willingness to pay per unit of outcome, e.g. 20000 per QALY."),
    cost_units: str = typer.Option(None, "--cost-units", help="e.g. '£'"),
    outcome_units: str = typer.Option(None, "--outcome-units", help="e.g. 'QALY'"),
) -> None:
    """Set the horizon, discounting, half-cycle correction, willingness to pay and units."""
    from latris.operations import markov

    given = {"num_cycles": cycles, "cycle_length": cycle_length, "time_units": time_units, "discount_rate": discount,
             "outcome_discount_rate": outcome_discount, "half_cycle_correction": half_cycle, "wtp": wtp,
             "cost_units": cost_units, "outcome_units": outcome_units}
    fields = {k: v for k, v in given.items() if v is not None}
    s, sha = markov.set_settings(**fields)
    emit(s, human=lambda: console.print(f"[green]set[/green] {', '.join(fields) or 'nothing'} · {_sha(sha)}"),
         commit_sha=sha)


@app.command("show")
@handle_cli_errors
def show() -> None:
    """Print the states, transitions (by strategy), costs and utilities, and the start."""
    from latris.operations import markov

    m = markov.load()
    lab = m.labels
    strategies = m.strategy_names()

    def name(s: str | None) -> str:
        return lab[s] if s else "all"

    data = {"states": [lab[s] for s in m.states], "strategies": [lab[s] for s in m.strategies],
            "start": {lab[k]: v for k, v in m.start.items()},
            "transitions": [{"from": lab[a], "to": lab[b], "strategy": name(st), "probability": t.probability}
                            for (e, st), t in m.transitions.items() for a, b in [m.edges[e]]]}

    def human() -> None:
        t = Table(show_header=True, header_style="bold", title="Transitions per cycle")
        t.add_column("From → to")
        for st in strategies:
            t.add_column(lab[st] if st else markov.BASE_CASE, justify="right")
        for e, (a, b) in m.edges.items():
            t.add_row(escape(f"{lab[a]} → {lab[b]}"),
                      *(f"{m.prob(e, st).probability:g}" if m.prob(e, st) else "—" for st in strategies))
        console.print(t)
        t = Table(show_header=True, header_style="bold", title="States")
        for col in ("State", "Starts", *(f"Cost / utility ({lab[st] if st else markov.BASE_CASE})"
                                          for st in strategies)):
            t.add_column(col)
        for s in m.states:
            cells = []
            for st in strategies:
                c, u = m.reward(s, st, "cost")[0], m.reward(s, st, "utility")[0]
                cells.append(f"{'—' if c is None else f'{c:g}'} / {'—' if u is None else f'{u:g}'}")
            t.add_row(escape(lab[s]), f"{m.start.get(s, 0):g}", *cells)
        console.print(t)
        for p in m.problems:
            console.print(f"[yellow]![/yellow] {escape(lab.get(p.target_id or '', '(model)'))}: {escape(p.message)}")

    emit(data, human=human)


@app.command("check")
@handle_cli_errors
def check() -> None:
    """Check the model: two states or more, a start summing to 1, transitions between states that don't
    exceed 1 out of any state. Exits 1 until so."""
    from latris.operations.readiness import assess_readiness

    r = assess_readiness("markov")
    gaps = [{"element": g.element_label, "gap_type": g.gap_type, "message": g.message} for g in r.gaps]

    def human() -> None:
        if r.can_switch:
            console.print("[green]The Markov model is complete.[/green]")
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
    """Run the cohort: each strategy's discounted costs and outcomes, the incremental analysis (ICERs,
    dominance, extended dominance) and — with a willingness to pay — the strategy to choose."""
    from latris.operations import markov
    from latris.operations.markov import _money

    payload = markov.analyse()
    sha = None
    if not no_record and not payload["problems"]:
        sha, payload["run_id"] = markov.record(payload)

    def human() -> None:
        for p in payload["problems"]:
            console.print(f"[yellow]![/yellow] {escape(p['label'])}: {escape(p['message'])}")
        console.print(escape(markov.describe(payload)) + ".\n")
        if payload["problems"]:
            return
        s = payload["settings"]
        cu, ou = s["cost_units"], s["outcome_units"] or "outcome"
        t = Table(show_header=True, header_style="bold", title="Discounted per person")
        for col in ("Strategy", "Cost", ou, "Status", "ICER"):
            t.add_column(col, justify="left" if col in ("Strategy", "Status") else "right")
        inc = {r["strategy"]: r for r in payload.get("incremental", [])}
        for r in payload["results"]:
            i = inc.get(r["strategy"], {})
            icer = _money(i["icer"], cu) + f" vs {i['versus']}" if i.get("icer") is not None else "—"
            t.add_row(escape(r["strategy"]), _money(r["cost"], cu), f"{r['outcome']:.3f}",
                      i.get("status", "—"), escape(icer))
        console.print(t)
        if payload["missing_cost"] or payload["missing_utility"]:
            console.print("[dim]No value recorded (counted as 0): "
                          + escape(", ".join(sorted(set(payload["missing_cost"]) | set(payload["missing_utility"]))))
                          + "[/dim]")
        if sha:
            console.print(f"\nrecorded · {_sha(sha)}")

    emit(payload, human=human, commit_sha=sha)
