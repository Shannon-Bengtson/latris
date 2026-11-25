"""Contract and predict CLI — declare a model's inputs and outputs, then run it on values you give."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from latris.cli._errors import handle_cli_errors
from latris.cli._output import emit

app = typer.Typer(help="A model's contract: the inputs a caller may give it and the outputs it returns.",
                  no_args_is_help=True)
console = Console()

_MODEL_TYPES = ("A model type that computes outputs: equation_model, sd, bn, fcm, fault_tree, bow_tie, event_tree, "
                "decision_tree, markov or mcda")
_TYPE = typer.Option(None, "--model-type", "-m", help="Which model, when the project has contracts for several.")


def _sha(sha: str) -> str:
    return f"commit [cyan]{sha[:10]}[/cyan]"


def _g(x) -> str:  # noqa: ANN001
    return "—" if x is None else f"{x:,.6g}" if isinstance(x, int | float) else str(x)


def _print_contract(d: dict) -> None:
    from latris.operations._units import display

    console.print(f"[bold]{escape(d['model_type'])}[/bold] contract · hash [cyan]{d['hash']}[/cyan]")
    t = Table(show_header=True, header_style="bold", title="Inputs", title_justify="left")
    for c in ("Name", "Factor", "Takes", "Default", "Valid range"):
        t.add_column(c)
    for i in d["inputs"]:
        takes = (display(i["units"]) or "a number") if i["kind"] == "value" else \
            f"{' | '.join(i['states'])} ({'set' if i['mode'] == 'set' else 'observed'})"
        bounded = i["valid_min"] is not None or i["valid_max"] is not None
        span = f"{_g(i['valid_min'])} – {_g(i['valid_max'])}" if bounded else ""
        t.add_row(i["name"], escape(i["label"] or "?"), escape(takes),
                  "required" if i["required"] else _g(i["default"]), span)
    console.print(t)
    t = Table(show_header=True, header_style="bold", title="Outputs", title_justify="left")
    for c in ("Name", "Factor", "Returns"):
        t.add_column(c)
    for o in d["outputs"]:
        returns = {"value": (display(o["units"] or "") or "a number") + (f" ({o['metric']})" if o["metric"] else ""),
                   "series": f"a series in {display(o['units'] or '') or 'numbers'}",
                   "distribution": f"the probability of {' | '.join(o['states'])}",
                   "choice": f"one of {' | '.join(o['states'])}"}[o["kind"]]
        t.add_row(o["name"], escape(o["label"] or "?"), escape(returns))
    console.print(t)
    for p in d["problems"]:
        console.print(f"[yellow]![/yellow] {escape(p)}")


@app.command("init")
@handle_cli_errors
def init(
    model_type: str = typer.Argument(..., help=_MODEL_TYPES),
    replace: bool = typer.Option(False, "--replace", help="Draft it again over the contract that is there."),
) -> None:
    """Draft a contract from the model: what it treats as given goes in, what it is for comes out.

    Then prune it. Every input is a promise to whoever calls the model, so expose only what a caller
    should set.
    """
    from latris.operations import contract

    _, sha = contract.init(model_type, replace=replace)
    d = contract.describe(model_type)

    def human() -> None:
        _print_contract(d)
        console.print(f"drafted · {_sha(sha)}")

    emit(d, human=human, commit_sha=sha)


@app.command("show")
@handle_cli_errors
def show(
    model_type: str = _TYPE,
    ref: str = typer.Option(None, "--ref", help="A commit, a milestone's name or a version's name (default: now)."),
) -> None:
    """Print the contract as a caller reads it: inputs, outputs, its hash, and whether it fits the model."""
    from latris.operations import predict

    d = predict.load(model_type=model_type, ref=ref).describe()

    def human() -> None:
        _print_contract(d)
        p = d["provenance"]
        console.print(f"[dim]at commit {(p['commit'] or '(none)')[:10]}"
                      + (" with unsaved changes" if p["uncommitted_changes"] else "") + "[/dim]")

    emit(d, human=human)


@app.command("available")
@handle_cli_errors
def available(model_type: str = typer.Argument(..., help=_MODEL_TYPES)) -> None:
    """List everything this model could expose as an input or an output, and what the contract already has."""
    from latris.operations import contract

    d = contract.candidates(model_type)

    def human() -> None:
        for what in ("inputs", "outputs"):
            t = Table(show_header=True, header_style="bold", title=f"Possible {what}", title_justify="left")
            cells = any(r["cell"] for r in d[what])
            for c in ("Factor", *(("Cell",) if cells else ()), "What it is", "Kind", "Units / states",
                      "In the contract as"):
                t.add_column(c)
            for r in d[what]:
                t.add_row(escape(r["label"]), *((escape(r["cell"] or ""),) if cells else ()), r["role"],
                          " | ".join(r["kinds"]),
                          escape(r["units"] or " | ".join(r["states"])), ", ".join(r["in_contract"]) or "—")
            console.print(t)
        for p in d["problems"]:
            console.print(f"[yellow]![/yellow] {escape(p)}")

    emit(d, human=human)


@app.command("input")
@handle_cli_errors
def input_(
    model_type: str = typer.Argument(..., help=_MODEL_TYPES),
    target: str = typer.Argument(..., help="The factor a caller sets: node ID, ID prefix, or label; `model` for a "
                                           "model-wide setting."),
    name: str = typer.Option(None, "--name", help="What callers call it (default: the label, as flow_depth)."),
    units: str = typer.Option(None, "--units", help="The units a bare number is read in (default: the model's)."),
    default: str = typer.Option(None, "--default", help="Used when the caller gives nothing (default: the "
                                                        "model's own value). 'none' clears it."),
    valid_min: float = typer.Option(None, "--min", help="Below this the result is flagged as an extrapolation."),
    valid_max: float = typer.Option(None, "--max", help="Above this the result is flagged as an extrapolation."),
    set_: bool = typer.Option(None, "--set/--observe", help="A state the caller makes so (an intervention) "
                                                            "or sees (evidence, the default)."),
    required: bool = typer.Option(None, "--required/--optional", help="Must the caller always give it?"),
    description: str = typer.Option(None, "--description", "-d"),
    cell: str = typer.Option(None, "--cell", help="Which of the factor's parameters, when it has several (see "
                                                  "`contract available`), e.g. markov:transition:<strategy>."),
) -> None:
    """Add a factor to the contract as an input, or change the input it already is (only what you give)."""
    from latris.operations import contract

    kwargs: dict = {}
    if default is not None:
        try:
            kwargs["default"] = None if default.lower() == "none" else float(default)
        except ValueError:
            kwargs["default"] = default
    if valid_min is not None:
        kwargs["valid_min"] = valid_min
    if valid_max is not None:
        kwargs["valid_max"] = valid_max
    entry, sha = contract.set_input(model_type, target, name=name, units=units, required=required,
                                    mode=None if set_ is None else "set" if set_ else "observe",
                                    description=description, cell=cell, **kwargs)
    emit(entry, human=lambda: console.print(f"[green]input[/green] {entry.name} ← {escape(target)} · {_sha(sha)}"),
         commit_sha=sha)


@app.command("output")
@handle_cli_errors
def output(
    model_type: str = typer.Argument(..., help=_MODEL_TYPES),
    target: str = typer.Argument(..., help="The factor returned: node ID, ID prefix, or label."),
    name: str = typer.Option(None, "--name", help="What callers call it (default: the label, as peak_demand)."),
    kind: str = typer.Option(None, "--kind", help="value | series | distribution | choice (default: what the "
                                                  "factor gives)."),
    metric: str = typer.Option(None, "--metric", help="System dynamics: which value of the run: final | peak | "
                                                      "peak-time | min | mean | total | at:T."),
    description: str = typer.Option(None, "--description", "-d"),
    cell: str = typer.Option(None, "--cell", help="Which of the factor's results, when it has several (see "
                                                  "`contract available`)."),
) -> None:
    """Add an output to the contract, or change the one with that name.

    A factor can be several outputs under different names: a stock's whole run (--kind series) and its
    peak (--metric peak --name peak_stock).
    """
    from latris.operations import contract

    entry, sha = contract.set_output(model_type, target, name=name, kind=kind, metric=metric, description=description,
                                     cell=cell)
    emit(entry, human=lambda: console.print(f"[green]output[/green] {entry.name} ← {escape(target)} "
                                            f"({entry.kind}) · {_sha(sha)}"), commit_sha=sha)


@app.command("remove")
@handle_cli_errors
def remove(
    model_type: str = typer.Argument(..., help=_MODEL_TYPES),
    name: str = typer.Argument(..., help="The input's or output's name in the contract."),
) -> None:
    """Take an input or an output out of the contract. Callers that use it will break: see `contract diff`."""
    from latris.operations import contract

    sha = contract.remove(model_type, name)
    emit({"removed": name}, human=lambda: console.print(f"[green]removed[/green] {name} · {_sha(sha)}"),
         commit_sha=sha)


@app.command("check")
@handle_cli_errors
def check(model_type: str = _TYPE) -> None:
    """Check the contract still fits the model (every input settable, every output computed). Exits 1 if not."""
    from latris.operations import contract

    problems = contract.check(model_type)

    def human() -> None:
        if not problems:
            console.print("[green]The contract fits the model and can be run.[/green]")
        for p in problems:
            console.print(f"  - {escape(p)}")

    emit({"ready": not problems, "problems": problems}, human=human)
    if problems:
        raise typer.Exit(1)


@app.command("diff")
@handle_cli_errors
def diff(
    base: str = typer.Argument(..., help="The version a caller was written against: a commit, milestone or version."),
    head: str = typer.Argument(None, help="The version to move to (default: the latest save)."),
    model_type: str = _TYPE,
) -> None:
    """What changed for a caller between two versions: breaking, compatible, or internal only.

    Exits 1 when the change is breaking, so a pipeline can refuse to upgrade.
    """
    from latris.operations import contract

    d = contract.compare(base, head, model_type=model_type)

    def human() -> None:
        says = {"breaking": "[red]Breaking[/red]: a caller written against the first version may fail on the second.",
                "compatible": "[green]Compatible[/green]: a caller written against the first version still works.",
                "internal": "[yellow]Internal only[/yellow]: the contract is the same, but the model behind it "
                            "changed, so the same inputs may give different outputs.",
                "same": "No change: the same contract and the same model."}[d["verdict"]]
        console.print(says)
        for line in d["breaking"]:
            console.print(f"  [red]✗[/red] {escape(line)}")
        for line in d["compatible"]:
            console.print(f"  [green]+[/green] {escape(line)}")
        if d["verdict"] in ("breaking", "compatible") and d["model_changed"]:
            console.print("  [dim]The model behind the contract changed too.[/dim]")

    emit(d, human=human)
    if d["verdict"] == "breaking":
        raise typer.Exit(1)


@handle_cli_errors
def predict(
    set_: list[str] = typer.Option([], "--set", "-s", help="An input: 'name=value', 'name=250 cm' or "
                                                           "'name=state' (repeatable)."),
    inputs: str = typer.Option(None, "--inputs", "-i", help="A JSON file of inputs {name: value}, or - for stdin."),
    model_type: str = _TYPE,
    ref: str = typer.Option(None, "--ref", help="Run a pinned version: a commit, a milestone's name or a "
                                                "version's name (default: the project as it is now)."),
    require: str = typer.Option(None, "--require", help="Refuse a version that isn't at least: reviewed | approved."),
) -> None:
    """Run the model on inputs you give and print its outputs. Nothing is recorded.

    Inputs are the names in the model's contract (`latris contract show`); one
    you leave out takes its default. The result says which commit produced it,
    and warns when an input is outside its valid range. With --json the whole
    result is one JSON object, for a pipeline.
    """
    from latris.operations import predict as ops
    from latris.operations._units import with_units

    given: dict = {}
    if inputs:
        text = sys.stdin.read() if inputs == "-" else Path(inputs).read_text(encoding="utf-8")
        loaded = json.loads(text)
        if not isinstance(loaded, dict):
            raise ValueError("the inputs file must hold one JSON object: {name: value}")
        given.update(loaded)
    given.update(dict(ops.parse_assignment(s) for s in set_))
    result = ops.predict(given, model_type=model_type, ref=ref, require=require)

    def human() -> None:
        t = Table(show_header=True, header_style="bold")
        t.add_column("Output")
        t.add_column("Result")
        for name, o in result["outputs"].items():
            if "value" in o:
                shown = "—" if o["value"] is None else with_units(_g(o["value"]), o["units"] or "dimensionless")
            elif "series" in o:
                s = o["series"]
                shown = (f"{len(s['values'])} points, {_g(s['values'][0])} → "
                         f"{with_units(_g(s['values'][-1]), o['units'] or 'dimensionless')} over {_g(s['times'][-1])} "
                         f"{s['time_units']}")
            elif "choice" in o:
                shown = str(o["choice"])
            else:
                shown = ", ".join(f"{k} {v:.1%}" for k, v in o["distribution"].items())
            t.add_row(f"{name}\n[dim]{escape(o['label'] or '')}[/dim]", escape(shown))
        console.print(t)
        using = ", ".join(f"{n} = {with_units(_g(v['value']), v['units'] or 'dimensionless')}" + (
            "" if v["source"] == "given" else f" ({v['source']})") for n, v in result["inputs"].items()
                          if v["value"] is not None)
        if using:
            console.print(f"[dim]with {escape(using)}[/dim]")
        for w in result["warnings"]:
            console.print(f"[yellow]![/yellow] {escape(w)}")
        p = result["provenance"]
        review = p["review"]
        stood = (review["milestone"] or {}).get("maturity") or review["maturity"]
        console.print(f"[dim]{escape(p['project'] or '')} at commit {(p['commit'] or '(none)')[:10]}"
                      + (f" ({escape(p['ref'])})" if p["ref"] else "") + f", contract {p['contract_hash']}"
                      + (f", {stood}" if stood else "") + ". Nothing was recorded.[/dim]")

    emit(result, human=human)
