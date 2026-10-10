"""Bayesian Network CLI — state spaces, CPTs, readiness check, inference."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from latris.cli._errors import handle_cli_errors

app = typer.Typer(help="Bayesian Network operations.", no_args_is_help=True)
console = Console()


def _labels() -> dict[str, str]:
    from latris.operations import nodes as node_ops

    return {e.id: e.label for e in node_ops.list_nodes()}


def _split(csv: str) -> list[str]:
    return [s.strip() for s in csv.split(",") if s.strip()]


@app.command("set-state-space")
@handle_cli_errors
def set_state_space(
    node: str = typer.Argument(..., help="Node ID, ID prefix, or label."),
    states: str = typer.Argument(..., help="Comma-separated states, e.g. 'low,med,high'."),
    ordered: bool = typer.Option(False, "--ordered", help="Mark as an ordinal (ordered) state space."),
) -> None:
    """Set the discrete state space of a chance node."""
    from latris.operations import bn as bn_ops

    entry, sha = bn_ops.set_state_space(node, _split(states), ordered=ordered)
    console.print(
        f"[green]set[/green] state space on {entry.target_id[:15]}… = "
        f"{', '.join(entry.states)} · commit [cyan]{sha[:10]}[/cyan]"
    )


@app.command("set-cpt")
@handle_cli_errors
def set_cpt(
    node: str = typer.Argument(..., help="Node ID, ID prefix, or label."),
    parents: str | None = typer.Option(None, "--parents", "-p", help="Comma-separated parent nodes."),
    probs: str = typer.Option(..., "--probs", help="Comma-separated probabilities, row-major (first parent slowest)."),
    origin: str = typer.Option("human-direct", "--origin", help="Provenance origin stamped on every row."),
    source: str | None = typer.Option(None, "--source", help="Source ID stamped on every row."),
) -> None:
    """Set a node's conditional probability table from a flat probability list.

    Probabilities are read in blocks of (number of node states), one block per
    parent-state combination, with the first parent varying slowest. Each block
    should sum to 1.
    """
    from latris.operations import bn as bn_ops

    parent_list = _split(parents) if parents else []
    try:
        prob_list = [float(x) for x in _split(probs)]
    except ValueError as exc:
        raise typer.BadParameter(f"--probs must be comma-separated numbers: {exc}") from exc

    cpt, sha = bn_ops.set_cpt(node, parent_list, prob_list, origin=origin, source_id=source)
    parent_desc = ", ".join(p[:12] for p in cpt.parents) or "—"
    console.print(
        f"[green]set[/green] CPT on {cpt.target_id[:15]}… "
        f"({len(cpt.rows)} row(s), parents: {parent_desc}) · commit [cyan]{sha[:10]}[/cyan]"
    )


@app.command("set-noisy-or")
@handle_cli_errors
def set_noisy_or(
    node: str = typer.Argument(..., help="Binary node ID, ID prefix, or label."),
    cause: list[str] = typer.Option(
        ..., "--cause", "-c",
        help="A cause as '<parent>=<active_state>:<prob>' (repeatable).",
    ),
    leak: float = typer.Option(0.0, "--leak", help="P(node active | all causes inactive)."),
    origin: str = typer.Option("human-elicited", "--origin", help="Provenance origin for the spec."),
    source: str | None = typer.Option(None, "--source", help="Source ID for the spec."),
) -> None:
    """Set a node's Noisy-OR parameterisation (binary node + binary causes).

    A compact alternative to a full CPT for high-fan-in nodes: each cause
    contributes independently. Stored as a spec and expanded to a full CPT at
    compute time. Example:
    `bn set-noisy-or "Outage" -c "Storm=yes:0.6" -c "Maintenance=yes:0.3" --leak 0.02`
    """
    from latris.operations import bn as bn_ops

    causes: list[tuple[str, str, float]] = []
    for raw in cause:
        if ":" not in raw or "=" not in raw.rsplit(":", 1)[0]:
            raise typer.BadParameter(f"--cause must be '<parent>=<active_state>:<prob>', got {raw!r}")
        head, prob_str = raw.rsplit(":", 1)
        parent, active_state = head.split("=", 1)
        try:
            prob = float(prob_str)
        except ValueError as exc:
            raise typer.BadParameter(f"probability in {raw!r} is not a number: {exc}") from exc
        causes.append((parent.strip(), active_state.strip(), prob))

    entry, sha = bn_ops.set_noisy_or(node, leak, causes, origin=origin, source_id=source)
    console.print(
        f"[green]set[/green] Noisy-OR on {entry.target_id[:15]}… "
        f"({len(entry.links)} cause(s), leak {entry.leak}) · commit [cyan]{sha[:10]}[/cyan]"
    )


@app.command("learn")
@handle_cli_errors
def learn(
    dataset: str = typer.Argument(..., help="Dataset ID or name."),
    node: list[str] = typer.Option(None, "--node", "-n", help="Restrict to these nodes (repeatable)."),
    estimator: str = typer.Option("bayesian", "--estimator", help="Estimator: 'bayesian' or 'mle'."),
    prior: str = typer.Option("BDeu", "--prior", help="Bayesian prior: BDeu | K2 | dirichlet."),
    ess: int = typer.Option(5, "--ess", help="Equivalent sample size (Bayesian prior strength)."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Apply without confirmation."),
) -> None:
    """Fit CPTs from a dataset, protecting expert-entered rows.

    Shows a preview, then (on confirm or --yes) writes the merged CPTs and
    records an AnalysisRun. Learned rows are stamped data-derived; rows a human
    elicited or verified are kept.
    """
    from latris.operations import bn_learn

    proposal = bn_learn.learn_cpts(
        dataset, nodes=node or None, estimator=estimator, prior=prior, equivalent_sample_size=ess,
    )
    labels = _labels()
    console.print(
        f"[bold]Parameter learning preview[/bold] — dataset {proposal.dataset_id[:18]}…, "
        f"{proposal.rows_used} row(s) used, {proposal.rows_dropped_na} dropped (NA)\n"
    )
    table = Table(show_header=True, header_style="bold")
    table.add_column("Node")
    table.add_column("Action")
    table.add_column("Learned")
    table.add_column("Kept")
    table.add_column("Zero-support")
    for d in proposal.diffs:
        name = labels.get(d.node_id, d.node_id[:12])
        if d.skipped_reason:
            table.add_row(name, f"[dim]skip: {d.skipped_reason}[/dim]", "—", "—", "—")
            continue
        origin = "mixed" if (d.rows_kept and d.rows_learned) else "data-derived"
        table.add_row(
            name, origin, str(d.rows_learned), str(d.rows_kept),
            str(d.zero_support_combos) if d.zero_support_combos else "",
        )
    console.print(table)

    if not proposal.affected_ids:
        console.print("\n[yellow]Nothing to apply[/yellow] — every targeted node was skipped.")
        return
    if not yes and not typer.confirm("\nApply learned CPTs?", default=False):
        console.print("[dim]aborted[/dim]")
        return

    sha, run_id = bn_learn.apply_learned(proposal)
    console.print(
        f"[green]applied[/green] · run [cyan]{run_id[:18]}…[/cyan] · commit [cyan]{sha[:10]}[/cyan]"
    )


@app.command("state-spaces")
@handle_cli_errors
def state_spaces() -> None:
    """List all node state spaces."""
    from latris.operations import bn as bn_ops

    store = bn_ops.get_state_spaces()
    if not store.entries:
        console.print("[dim](no state spaces defined)[/dim]")
        return
    labels = _labels()
    table = Table(show_header=True, header_style="bold")
    table.add_column("Node")
    table.add_column("States")
    table.add_column("Ordered")
    for e in store.entries:
        table.add_row(labels.get(e.target_id, e.target_id[:12]), ", ".join(e.states), "✓" if e.ordered else "")
    console.print(table)


@app.command("cpts")
@handle_cli_errors
def cpts() -> None:
    """List all CPTs (one row per conditional distribution).

    Canonical (Noisy-OR) nodes are shown expanded, marked in the Kind column.
    """
    from latris.operations import bn as bn_ops

    cpt_map = bn_ops.effective_cpts()
    if not cpt_map:
        console.print("[dim](no CPTs defined)[/dim]")
        return
    canonical = {e.target_id for e in bn_ops.get_noisy_or().entries}
    labels = _labels()
    table = Table(show_header=True, header_style="bold")
    table.add_column("Node")
    table.add_column("Kind")
    table.add_column("Parent states")
    table.add_column("P(node)")
    table.add_column("Origin")
    for nid, cpt in cpt_map.items():
        node_label = labels.get(nid, nid[:12])
        kind = "Noisy-OR" if nid in canonical else "table"
        for row in cpt.rows:
            cond = ", ".join(f"{labels.get(k, k[:8])}={v}" for k, v in row.parent_states.items()) or "—"
            dist = ", ".join(f"{s}:{p:.3f}" for s, p in zip(cpt.states, row.p, strict=True))
            table.add_row(node_label, kind, cond, dist, row.origin)
    console.print(table)


@app.command("check")
@handle_cli_errors
def check() -> None:
    """Check BN readiness: state spaces defined, CPTs complete + normalised."""
    from latris.operations import bn as bn_ops

    gaps = bn_ops.check()
    if not gaps:
        console.print("[green]✓[/green] BN is fully quantified and ready to compute.")
        return
    labels = _labels()
    table = Table(show_header=True, header_style="bold")
    table.add_column("Node")
    table.add_column("Gap")
    table.add_column("Detail")
    for g in gaps:
        node = labels.get(g.element_id, g.element_label or g.element_id[:12])
        table.add_row(node, g.gap_type, g.message)
    console.print(table)
    raise typer.Exit(code=1)


@app.command("marginals")
@handle_cli_errors
def marginals() -> None:
    """Show prior marginal distributions for every node."""
    from latris.operations import bn as bn_ops

    result = bn_ops.infer()
    _print_marginals(result, header="Prior marginals")


@app.command("query")
@handle_cli_errors
def query(
    evidence: list[str] | None = typer.Option(None, "--evidence", "-e", help="Observed node=state (repeatable)."),
    query_nodes: list[str] | None = typer.Option(None, "--query", "-q", help="Node to compute (repeatable)."),
) -> None:
    """Compute posterior marginals given evidence."""
    from latris.operations import bn as bn_ops

    ev: dict[str, str] = {}
    for item in evidence or []:
        if "=" not in item:
            raise typer.BadParameter(f"Evidence must be 'node=state', got {item!r}")
        name, state = item.rsplit("=", 1)
        ev[name.strip()] = state.strip()

    result = bn_ops.infer(query=query_nodes or None, evidence=ev or None)
    # result.evidence is keyed by resolved node ID, so labels resolve cleanly
    # in the header (the raw ``ev`` keys are user input — IDs, prefixes, or
    # labels — and wouldn't match the node-ID-keyed label map).
    _print_marginals(result, header="Posterior marginals", evidence=result.evidence)


@app.command("sensitivity")
@handle_cli_errors
def sensitivity(
    target: str = typer.Argument(..., help="Target node ID, prefix, or label."),
    state: str = typer.Option(..., "--state", "-s", help="Target state to analyse."),
    evidence: list[str] | None = typer.Option(None, "--evidence", "-e", help="Observed node=state (repeatable)."),
    top: int = typer.Option(15, "--top", help="Show the N most influential parameters."),
    record: bool = typer.Option(True, "--record/--no-record", help="Log an AnalysisRun + artifact."),
) -> None:
    """Rank CPT parameters by their influence on P(target=state), with provenance.

    Each conditional is swept over its range; the tornado shows which parameters
    move the conclusion — and flags those that aren't human-verified, so you see
    when the answer hinges on weakly-grounded cells.
    """
    from latris.operations import bn_sensitivity

    ev: dict[str, str] = {}
    for item in evidence or []:
        if "=" not in item:
            raise typer.BadParameter(f"Evidence must be 'node=state', got {item!r}")
        name, st = item.rsplit("=", 1)
        ev[name.strip()] = st.strip()

    result = bn_sensitivity.sensitivity(target, state, evidence=ev or None, top=top)
    labels = _labels()
    cond = ""
    if result.evidence:
        given = ", ".join(f"{labels.get(k, k[:8])}={v}" for k, v in result.evidence.items())
        cond = f"  (given {given})"
    console.print(
        f"[bold]Sensitivity[/bold] of P({labels.get(result.target_id, result.target_id[:12])}"
        f"={result.target_state}) = [cyan]{result.baseline:.3f}[/cyan]{cond}\n"
    )
    table = Table(show_header=True, header_style="bold")
    table.add_column("Parameter")
    table.add_column("Cell")
    table.add_column("Influence", justify="right")
    table.add_column("Origin")
    table.add_column("Verified")
    for f in result.findings:
        node = labels.get(f.node_id, f.node_id[:12])
        cond_str = ", ".join(f"{labels.get(k, k[:8])}={v}" for k, v in f.parent_states.items()) or "(prior)"
        param = f"{node} | {cond_str}"
        verified = "✓" if f.verification == "human-verified" else ("[yellow]⚠ weak[/yellow]" if f.weak else "")
        infl = f"{f.influence:.3f}"
        if f.weak and f.influence > 0:
            infl = f"[yellow]{infl}[/yellow]"
        table.add_row(param, f.state, infl, f.origin, verified)
    console.print(table)

    if record:
        sha, run_id = bn_sensitivity.record_sensitivity(result)
        console.print(
            f"\n[green]recorded[/green] · run [cyan]{run_id[:18]}…[/cyan] · commit [cyan]{sha[:10]}[/cyan]"
        )


def _print_marginals(result, *, header: str, evidence: dict[str, str] | None = None) -> None:
    labels = _labels()
    if evidence:
        cond = ", ".join(f"{labels.get(k, k[:8])}={v}" for k, v in evidence.items())
        console.print(f"[bold]{header}[/bold]  (given {cond})\n")
    else:
        console.print(f"[bold]{header}[/bold]\n")

    if not result.marginals:
        console.print("[dim](nothing to compute)[/dim]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Node")
    table.add_column("Distribution")
    for node_id, dist in result.marginals.items():
        cells = "   ".join(f"{state} {prob:.3f}" for state, prob in dist.items())
        table.add_row(labels.get(node_id, node_id[:12]), cells)
    console.print(table)
