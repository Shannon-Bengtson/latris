"""`uncertainty` and `monte-carlo` commands shared by `ft`, `bowtie` and `et` (operations/risk_uncertainty.py)."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from latris.cli._errors import handle_cli_errors
from latris.cli._output import emit

console = Console()

_WHAT = {
    "fault_tree": "A basic or undeveloped event (its probability).",
    "bow_tie": "A barrier (its probability of failure on demand) or a threat (its frequency).",
    "event_tree": "A heading (its P(yes); --given for a conditional one) or the initiating event (its frequency).",
}


def _g(x) -> str:
    return "—" if x is None else f"{x:.3g}"


def register(app: typer.Typer, model_type: str) -> None:

    @app.command("uncertainty")
    @handle_cli_errors
    def uncertainty(
        target: str = typer.Argument(..., help=_WHAT[model_type]),
        distribution: str = typer.Argument(
            "lognormal", help="lognormal (default) | uniform | triangular | normal | beta | gamma"
        ),
        median: float | None = typer.Option(None, "--median", help="Lognormal median (with --error-factor)."),
        error_factor: float | None = typer.Option(
            None, "--error-factor", "--ef", help="Lognormal error factor: 95th percentile ÷ median (e.g. 3, 10)."
        ),
        min_: float | None = typer.Option(None, "--min"),
        mode: float | None = typer.Option(None, "--mode"),
        max_: float | None = typer.Option(None, "--max"),
        mean: float | None = typer.Option(None, "--mean"),
        sd: float | None = typer.Option(None, "--sd"),
        alpha: float | None = typer.Option(None, "--alpha"),
        beta: float | None = typer.Option(None, "--beta"),
        shape: float | None = typer.Option(None, "--shape"),
        scale: float | None = typer.Option(None, "--scale"),
        given: list[str] = typer.Option(
            [], "--given", help="Event trees: the condition of the probability, 'Heading=yes|no' (repeatable)."
        ),
        reason: str = typer.Option("", "--reason", help="Why this range (e.g. 'generic data, OREDA')."),
        source: str | None = typer.Option(None, "--source", help="Source ID backing the range."),
        origin: str = typer.Option("human-direct", "--origin"),
        verified: bool = typer.Option(False, "--verified", help="Mark the range as checked by a person."),
        clear: bool = typer.Option(False, "--clear", help="Remove the range instead."),
    ) -> None:
        """Say how uncertain a probability or frequency is, for `monte-carlo`.

        The usual way in risk assessment is a lognormal by its median and
        error factor: --median 1e-3 --error-factor 3 means the value is 1e-3
        at the median and below 3e-3 with 95% confidence. Probabilities are
        kept within [0, 1]. The range must include the current value.
        """
        from latris.operations import risk_uncertainty as ru

        cond = [tuple(x.strip() for x in g.split("=", 1)) for g in given]
        if any(len(c) != 2 for c in cond):
            raise ValueError("--given takes 'Heading=yes' or 'Heading=no'")
        if clear:
            sha = ru.clear_uncertainty(model_type, target, given=cond or None)  # type: ignore[arg-type]
            emit({"cleared": target}, human=lambda: console.print(f"[green]cleared[/green] {escape(target)} · "
                                                                   f"commit [cyan]{sha[:10]}[/cyan]"), commit_sha=sha)
            return
        raw = {"median": median, "error_factor": error_factor, "min": min_, "mode": mode, "max": max_,
               "mean": mean, "sd": sd, "alpha": alpha, "beta": beta, "shape": shape, "scale": scale}
        entry, sha = ru.set_uncertainty(model_type, target, distribution, {k: v for k, v in raw.items()
                                                                           if v is not None},
                                        given=cond or None, reason=reason, source_id=source,  # type: ignore[arg-type]
                                        origin=origin,  # type: ignore[arg-type]
                                        verification="human-verified" if verified else "unverified")
        pretty = ", ".join(f"{k}={v:.4g}" for k, v in entry.params.items())
        emit(entry.model_dump(mode="json"),
             human=lambda: console.print(f"[green]uncertainty[/green] {escape(target)} ~ {entry.distribution}"
                                         f"({pretty}) · commit [cyan]{sha[:10]}[/cyan]"),
             commit_sha=sha)

    @app.command("monte-carlo")
    @handle_cli_errors
    def monte_carlo(
        runs: int = typer.Option(5000, "--runs", "-n", help="Number of sampled runs."),
        seed: int = typer.Option(1234, "--seed", help="The same seed gives the same runs."),
        sampling: str = typer.Option("lhs", "--sampling", help="lhs (Latin hypercube) | random."),
        output: str | None = typer.Option(None, "--output", help="The result to headline (default: the top event, "
                                                                  "or an event tree's rarest end state)."),
        no_record: bool = typer.Option(False, "--no-record", help="Show the result without recording it."),
    ) -> None:
        """How sure is the result? Sample every input that has a range and recompute.

        Gives each result's 5th–95th percentile, median and mean beside the
        point estimate (with skewed inputs the mean is higher), and ranks the
        uncertain inputs by how strongly they drive the headline result.
        Inputs without a range are held at their value and listed.
        """
        from latris.operations import risk_uncertainty as ru

        payload = ru.monte_carlo(model_type, runs=runs, seed=seed, sampling=sampling, output=output)
        sha = None
        if not no_record:
            sha, payload["run_id"] = ru.record(payload)

        def human() -> None:
            console.print(escape(ru.describe(payload)) + ".\n")
            t = Table(show_header=True, header_style="bold", title="Results")
            for col in ("Result", "Point", "Mean", "5th", "Median", "95th"):
                t.add_column(col, justify="left" if col == "Result" else "right")
            for o in payload["outputs"]:
                t.add_row(escape(o["output"]), _g(o["point"]), _g(o["mean"]), _g(o["p5"]), _g(o["p50"]),
                          _g(o["p95"]))
            console.print(t)
            t = Table(show_header=True, header_style="bold", title=f"What drives {payload['primary']}")
            for col in ("Input", "Distribution", "5th–95th", "Rank corr.", "Checked"):
                t.add_column(col)
            for d in payload["drivers"]:
                t.add_row(escape(d["input"]), d["distribution"], f"{_g(d['p5'])} – {_g(d['p95'])}",
                          "—" if d["spearman"] is None else f"{d['spearman']:+.2f}",
                          "[yellow]no[/yellow]" if d["weak"] else "yes")
            console.print(t)
            if payload["fixed"]:
                console.print("[dim]Held at their value (no range): " + escape(", ".join(payload["fixed"])) + "[/dim]")
            if sha:
                console.print(f"\nrecorded · commit [cyan]{sha[:10]}[/cyan]")

        emit(payload, human=human, commit_sha=sha)

    del uncertainty, monte_carlo  # registered on the app
