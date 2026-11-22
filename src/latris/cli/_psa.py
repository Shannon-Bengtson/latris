"""`range` and `psa` commands shared by `dt` and `markov` (operations/psa.py)."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from latris.cli._errors import handle_cli_errors
from latris.cli._options import ORIGIN_HELP, verification
from latris.cli._output import emit

console = Console()

_WHAT = {
    "decision_tree": "A terminal node (its payoff), a branch 'Parent -> Child' (its probability, or --quantity value), "
                     "or a chance node (a Dirichlet over its branch probabilities).",
    "markov": "A transition 'From -> To' (its probability), or a state with --quantity cost | utility | leaving "
              "(a Dirichlet over its transitions out).",
}
_QUANTITY = {
    "decision_tree": "payoff | value | probability | probabilities — only where the target leaves it open.",
    "markov": "transition | cost | utility | leaving — required for a state.",
}


def _g(x) -> str:
    return "—" if x is None else f"{x:,.4g}"


def register(app: typer.Typer, model_type: str) -> None:

    @app.command("range")
    @handle_cli_errors
    def range_(
        target: str = typer.Argument(..., help=_WHAT[model_type]),
        distribution: str = typer.Argument(
            ..., help="beta (probabilities, utilities) | gamma (costs) | normal | lognormal | uniform | triangular "
                      "| dirichlet (a set of probabilities)"),
        quantity: str | None = typer.Option(None, "--quantity", "-q", help=_QUANTITY[model_type]),
        strategy: str | None = typer.Option(None, "--strategy", help="Markov: this strategy's own value only.")
        if model_type == "markov" else typer.Option(None, hidden=True),
        mean: float | None = typer.Option(None, "--mean", help="Mean (with --sd): beta and gamma convert by the "
                                                              "method of moments."),
        sd: float | None = typer.Option(None, "--sd", help="Standard deviation (e.g. a study's standard error)."),
        min_: float | None = typer.Option(None, "--min"),
        mode: float | None = typer.Option(None, "--mode"),
        max_: float | None = typer.Option(None, "--max"),
        alpha: float | None = typer.Option(None, "--alpha"),
        beta: float | None = typer.Option(None, "--beta"),
        shape: float | None = typer.Option(None, "--shape"),
        scale: float | None = typer.Option(None, "--scale"),
        n: float | None = typer.Option(None, "--n", help="Dirichlet: how many observations the probabilities "
                                                        "are worth (larger: surer)."),
        reason: str = typer.Option("", "--reason", help="Why this range (e.g. 'trial, 95% CI 0.04–0.08')."),
        source: str | None = typer.Option(None, "--source", help="Source ID backing the range."),
        origin: str = typer.Option("human-direct", "--origin", help=ORIGIN_HELP),
        verified: bool = typer.Option(False, "--verified", help="Mark the range as checked by a person."),
        clear: bool = typer.Option(False, "--clear", help="Remove the range instead."),
    ) -> None:
        """Say how uncertain an input is, for `psa`.

        The usual choices: a beta for a probability or utility and a gamma
        for a cost, each by the mean and standard error a study reports
        (--mean 0.1 --sd 0.02). A set of probabilities that must sum to 1
        takes a Dirichlet worth n observations. The range must include the
        current value.
        """
        from latris.operations import psa

        if clear:
            sha = psa.clear_range(model_type, target, quantity=quantity, strategy=strategy)
            emit({"cleared": target}, human=lambda: console.print(f"[green]cleared[/green] {escape(target)} · "
                                                                   f"commit [cyan]{sha[:10]}[/cyan]"), commit_sha=sha)
            return
        raw = {"mean": mean, "sd": sd, "min": min_, "mode": mode, "max": max_, "alpha": alpha, "beta": beta,
               "shape": shape, "scale": scale, "n": n}
        entry, sha = psa.set_range(model_type, target, distribution, {k: v for k, v in raw.items() if v is not None},
                                   quantity=quantity, strategy=strategy, reason=reason, source_id=source,
                                   origin=origin,  # type: ignore[arg-type]
                                   verification=verification(verified))
        pretty = ", ".join(f"{k}={v:.4g}" for k, v in entry.params.items())
        emit(entry.model_dump(mode="json"),
             human=lambda: console.print(f"[green]range[/green] {escape(target)} ~ {entry.distribution}({pretty}) · "
                                         f"commit [cyan]{sha[:10]}[/cyan]"),
             commit_sha=sha)

    @app.command("psa")
    @handle_cli_errors
    def psa_(
        runs: int = typer.Option(2000 if model_type == "decision_tree" else 1000, "--runs", "-n",
                                 help="Number of sampled runs."),
        seed: int = typer.Option(1234, "--seed", help="The same seed gives the same runs."),
        sampling: str = typer.Option("lhs", "--sampling", help="lhs (Latin hypercube) | random."),
        no_record: bool = typer.Option(False, "--no-record", help="Show the result without recording it."),
    ) -> None:
        """Probabilistic sensitivity analysis: sample every input with a range and rerun the model.

        Shows how often each choice comes out best, the spread of the
        results, the expected value of perfect information (the most it is
        worth to remove the uncertainty before choosing), and which inputs
        drive the decision. Inputs without a range are held at their value
        and listed.
        """
        from latris.operations import psa

        payload = psa.run(model_type, runs=runs, seed=seed, sampling=sampling)
        sha = None
        if not no_record:
            sha, payload["run_id"] = psa.record(payload)

        def human() -> None:
            console.print(escape(psa.describe(payload)) + ".\n")
            if model_type == "decision_tree":
                t = Table(show_header=True, header_style="bold", title="Options")
                for col in ("Option", "Point", "Mean", "5th", "95th", "Best in"):
                    t.add_column(col, justify="left" if col == "Option" else "right")
                for o in payload["outputs"]:
                    t.add_row(escape(o["output"]), _g(o["point"]), _g(o["mean"]), _g(o["p5"]), _g(o["p95"]),
                              f"{o['p_best']:.0%}")
                console.print(t)
            else:
                cu = payload["cost_units"]
                t = Table(show_header=True, header_style="bold", title="Strategies")
                for col in ("Strategy", "Mean cost", "Cost 5th–95th", "Mean outcome", "Outcome 5th–95th"):
                    t.add_column(col, justify="left" if col == "Strategy" else "right")
                for s in payload["strategies"]:
                    t.add_row(escape(s["strategy"]), psa.money(s["cost"]["mean"], cu),
                              f"{psa.money(s['cost']['p5'], cu)} – {psa.money(s['cost']['p95'], cu)}",
                              f"{s['outcome']['mean']:.3f}", f"{s['outcome']['p5']:.3f} – {s['outcome']['p95']:.3f}")
                console.print(t)
                c = payload["ceac"]
                if len(c["strategies"]) > 1:
                    t = Table(show_header=True, header_style="bold", title="Probability cost-effective")
                    t.add_column("Willingness to pay", justify="right")
                    for name in c["strategies"]:
                        t.add_column(escape(name), justify="right")
                    t.add_column("EVPI", justify="right")
                    for i in range(0, len(c["wtp"]), 10):
                        t.add_row(psa.money(c["wtp"][i], cu), *(f"{c['p'][j][i]:.0%}" for j in range(len(c["p"]))),
                                  psa.money(c["evpi"][i], cu))
                    console.print(t)
            t = Table(show_header=True, header_style="bold", title=f"What drives the {payload['driver_target']}")
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

    del range_, psa_  # registered on the app
