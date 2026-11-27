"""Theory of Change CLI — give factors their levels, then check the pathways."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from latris.cli._errors import handle_cli_errors
from latris.cli._options import ORIGIN_HELP, verification
from latris.cli._output import emit, json_mode

app = typer.Typer(help="Theory of Change (results chain) operations.", no_args_is_help=True)

# Where each command sits in the workflow (schema/workflow.py; rules in docs/engineering/WORKFLOW_STRUCTURE.md).
PLACE = {
    "level": "formalise.definitions",
    "levels": "formalise.definitions",
    "check": "analyse.structural",
    "prior": "formalise.values",
    "test_link": "formalise.values",
    "trace": "analyse.base_case",
    "impact": "analyse.estimation",
}
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


def _origin_opts(origin: str | None, source: str | None, verified: bool) -> dict:
    out: dict = {"verification": verification(verified)}
    if origin:
        out["origin"] = origin
    if source:
        out["source_id"] = source
    return out


@app.command("prior")
@handle_cli_errors
def prior(
    link: str = typer.Argument(..., help="The link, written 'From -> To' (or an edge ID)."),
    value: float = typer.Argument(..., help="Probability the link holds before any test, strictly between 0 and 1."),
    source: str | None = typer.Option(None, "--source", help="Source ID the prior rests on."),
    origin: str | None = typer.Option(None, "--origin", help=ORIGIN_HELP),
    verified: bool = typer.Option(False, "--verified", help="Mark the prior as checked by a person."),
    notes: str | None = typer.Option(None, "--notes"),
) -> None:
    """Process tracing: how confident you are in a link before the tests (default 0.5)."""
    from latris.operations import process_tracing as pt

    entry, sha = pt.set_prior(link, value, notes=notes, **_origin_opts(origin, source, verified))
    emit(entry.model_dump(mode="json"),
         human=lambda: console.print(f"[green]prior[/green] {escape(link)} = {value:g} · "
                                     f"commit [cyan]{sha[:10]}[/cyan]"),
         commit_sha=sha)


@app.command("test")
@handle_cli_errors
def test_link(
    link: str = typer.Argument(..., help="The link, written 'From -> To' (or an edge ID)."),
    name: str = typer.Argument(..., help="A short name for the test; unique on its link."),
    if_true: float | None = typer.Option(None, "--if-true", help="P(evidence found | the link holds): certainty."),
    if_false: float | None = typer.Option(
        None, "--if-false", help="P(evidence found | it doesn't): low means the evidence is unique to the link."
    ),
    found: bool | None = typer.Option(
        None, "--found/--not-found", help="The result, once you've looked. Omit while the test is still to run."
    ),
    description: str | None = typer.Option(None, "--description", help="What evidence you'd expect to find."),
    source: str | None = typer.Option(None, "--source", help="Source ID where the evidence was (or wasn't) found."),
    origin: str | None = typer.Option(None, "--origin"),
    verified: bool = typer.Option(False, "--verified", help="Mark the judgements as checked by a person."),
    notes: str | None = typer.Option(None, "--notes"),
    remove: bool = typer.Option(False, "--remove", help="Remove this test."),
) -> None:
    """Process tracing: add or update an evidence test on a link.

    A test is the evidence you'd expect to see if the link holds. --if-true
    is how likely you'd find it if the link holds; --if-false, if it
    doesn't. Van Evera's types follow: a *hoop* test (high --if-true) sinks
    the link if failed; a *smoking gun* (low --if-false) clinches it if
    passed; *doubly decisive* does both; *straw in the wind* nudges. Add the
    result with --found or --not-found. Updating a test changes only what you
    give.
    """
    from latris.operations import process_tracing as pt

    if remove:
        sha = pt.remove_test(link, name)
        emit({"removed": name}, human=lambda: console.print(f"[green]removed[/green] {escape(name)} · commit "
                                                             f"[cyan]{sha[:10]}[/cyan]"), commit_sha=sha)
        return
    kw: dict = {}
    for k, v in (("p_if_true", if_true), ("p_if_false", if_false), ("description", description), ("notes", notes),
                 ("origin", origin), ("source_id", source)):
        if v is not None:
            kw[k] = v
    if found is not None:
        kw["found"] = found
    if verified:
        kw["verification"] = "human-verified"
    entry, sha = pt.set_test(link, name, **kw)
    kind = pt.classify(entry.p_if_true, entry.p_if_false)
    state = {True: "found", False: "not found", None: "not yet looked for"}[entry.found]
    emit(entry.model_dump(mode="json") | {"type": kind},
         human=lambda: console.print(f"[green]test[/green] {escape(name)} on {escape(link)}: {kind}, {state} · "
                                     f"commit [cyan]{sha[:10]}[/cyan]"),
         commit_sha=sha)


@app.command("trace")
@handle_cli_errors
def trace(
    no_record: bool = typer.Option(False, "--no-record", help="Show the result without recording it for reports."),
) -> None:
    """Process tracing: how far the tests support each link, and each pathway.

    Each link starts at its prior; each test passed or failed multiplies the
    odds by P(E|holds)/P(E|doesn't) or its complement. A pathway's confidence
    is the product of its links' posteriors. Tests not yet run are ranked by
    how far they could move their link. Recorded for reports unless --no-record.
    """
    from latris.operations import process_tracing as pt

    payload, sha = pt.trace(record=not no_record)

    def pct(x: float) -> str:
        return f"{x:.0%}"

    def human() -> None:
        console.print(escape(pt.describe(payload)) + ".\n")
        if payload["links"]:
            table = Table(show_header=True, header_style="bold", title="Links")
            for col in ("Link", "Prior", "Tests carried out", "Posterior", "Verdict"):
                table.add_column(col)
            for lk in payload["links"]:
                done = [t for t in lk["tests"] if t["found"] is not None]
                tests = "; ".join(f"{t['test']} ({t['type']}, {'passed' if t['found'] else 'failed'})"
                                  for t in done) or "[dim]none[/dim]"
                table.add_row(escape(lk["link"]), pct(lk["prior"]), tests, pct(lk["posterior"]), lk["verdict"])
            console.print(table)
        if payload["pathways"]:
            table = Table(show_header=True, header_style="bold", title="Pathways")
            for col in ("Pathway", "Confidence", "Weakest link"):
                table.add_column(col)
            for pw in payload["pathways"]:
                table.add_row(escape(" → ".join(pw["path"])), pct(pw["confidence"]),
                              f"{escape(pw['weakest'])} ({pct(pw['weakest_posterior'])})")
            console.print(table)
        pending = [(lk["link"], t) for lk in payload["links"] for t in lk["pending"]]
        if pending:
            table = Table(show_header=True, header_style="bold", title="Tests to run (most informative first)")
            for col in ("Link", "Test", "Type", "If found", "If not found"):
                table.add_column(col)
            for name, t in sorted(pending, key=lambda c: -abs(c[1]["if_found"] - c[1]["if_not_found"])):
                table.add_row(escape(name), escape(t["test"]), t["type"], pct(t["if_found"]), pct(t["if_not_found"]))
            console.print(table)
        if payload["rests_on_unverified"]:
            console.print("[yellow]Judgements nobody has verified:[/yellow] "
                          + escape(", ".join(payload["rests_on_unverified"])))
        if sha:
            console.print(f"\nrecorded · commit [cyan]{sha[:10]}[/cyan]")

    emit(payload, human=human, commit_sha=sha)


@app.command("impact")
@handle_cli_errors
def impact(
    outcome: str = typer.Argument(..., help="The outcome or impact factor whose change to estimate."),
    dataset: str = typer.Option(..., "--dataset", help="Registered dataset (`latris data add`)."),
    time: str = typer.Option(..., "--time", help="The dataset's time column (numbers or dates)."),
    at: str = typer.Option(..., "--at", help="The first period the intervention could affect (a number or date)."),
    group: str | None = typer.Option(
        None, "--group", help="Difference-in-differences: the column saying which group each row is in."
    ),
    treated: list[str] = typer.Option(
        [], "--treated", help="Group value(s) that received the intervention (repeat for several)."
    ),
    column: str | None = typer.Option(None, "--column", help="The outcome's column, if not the factor's label."),
    no_record: bool = typer.Option(False, "--no-record", help="Show the result without recording it for reports."),
) -> None:
    """Estimate the intervention's impact on an outcome from data.

    Without --group: an interrupted time series — the step and change of
    slope at --at, and the effect by the last period against the
    pre-period trend projected forward. With --group and --treated:
    difference-in-differences against the comparison group, after checking
    whether the groups were on parallel trends before. Every check that
    fails or can't be made is listed as a caution. Recorded unless --no-record.
    """
    from latris.operations import impact as ops

    payload = ops.estimate(outcome, dataset, time=time, at=at, group=group, treated=treated or None,
                           column=column)
    sha = None
    if not no_record:
        sha, payload["run_id"] = ops.record(payload)

    def g(x: float) -> str:
        return f"{x:.4g}"

    def human() -> None:
        console.print(escape(ops.describe(payload)) + ".\n")
        table = Table(show_header=True, header_style="bold")
        for col in ("", "Estimate", "95% CI", "p"):
            table.add_column(col)
        if payload["method"] == "its":
            parts = (("Trend before (per period)", payload["pre_trend"]),
                     ("Step at the start", payload["level_change"]),
                     ("Change of slope (per period)", payload["slope_change"]),
                     ("Effect by the last period", payload["effect"]))
        else:
            parts = (("Difference-in-differences", payload["effect"]),)
            pt = payload["pre_trend_difference"]
            if pt.get("testable"):
                parts += (("Pre-period trend difference", pt),)
        for name, c in parts:
            table.add_row(name, g(c["estimate"]), f"{g(c['ci_low'])} to {g(c['ci_high'])}", g(c["p"]))
        console.print(table)
        if payload["method"] == "did":
            m = payload["means"]
            console.print(f"Means — treated {g(m['treated_before'])} → {g(m['treated_after'])}, comparison "
                          f"{g(m['comparison_before'])} → {g(m['comparison_after'])}.")
        console.print(f"Standard errors: {payload['se_type']}.")
        for w in payload["warnings"]:
            console.print(f"[yellow]caution:[/yellow] {escape(w)}")
        console.print("[dim]Assumes: " + escape(" ".join(payload["assumptions"])) + "[/dim]")
        if sha:
            console.print(f"\nrecorded · commit [cyan]{sha[:10]}[/cyan]")

    emit(payload, human=human, commit_sha=sha)
