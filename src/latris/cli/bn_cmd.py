"""Bayesian Network CLI — state spaces, CPTs, readiness check, inference."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from latris.cli._errors import handle_cli_errors
from latris.cli._output import emit, json_mode

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
    if json_mode():
        emit(entry, human=lambda: None, commit_sha=sha)
        return
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
    if json_mode():
        emit(cpt, human=lambda: None, commit_sha=sha)
        return
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
    active: str | None = typer.Option(
        None, "--active", help="The node's state the causes push toward (the effect happening), e.g. yes."),
    origin: str = typer.Option("human-elicited", "--origin", help="Provenance origin for the spec."),
    source: str | None = typer.Option(None, "--source", help="Source ID for the spec."),
) -> None:
    """Set a node's Noisy-OR parameterisation (binary node + binary causes).

    A compact alternative to a full CPT for high-fan-in nodes: each cause
    contributes independently. Stored as a spec and expanded to a full CPT at
    compute time. Example:
    `bn set-noisy-or "Outage" -c "Storm=yes:0.6" -c "Maintenance=yes:0.3" --leak 0.02 --active yes`
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

    entry, sha = bn_ops.set_noisy_or(node, leak, causes, active=active, origin=origin, source_id=source)
    if json_mode():
        emit(entry, human=lambda: None, commit_sha=sha)
        return
    console.print(
        f"[green]set[/green] Noisy-OR on {entry.target_id[:15]}… "
        f"({len(entry.links)} cause(s), leak {entry.leak}, effect = {entry.active_state}) · "
        f"commit [cyan]{sha[:10]}[/cyan]"
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
    if json_mode():
        labels = _labels()
        emit([{"node": labels.get(e.target_id, e.target_id), "states": e.states, "ordered": e.ordered}
              for e in store.entries], human=lambda: None)
        return
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
    if json_mode():
        canonical = {e.target_id for e in bn_ops.get_noisy_or().entries}
        labels = _labels()
        emit([
            {"node": labels.get(nid, nid), "kind": "noisy-or" if nid in canonical else "table",
             "states": cpt.states, "parents": [labels.get(p, p) for p in cpt.parents],
             "rows": [{"given": {labels.get(k, k): v for k, v in row.parent_states.items()},
                       "p": dict(zip(cpt.states, row.p, strict=True)), "origin": row.origin}
                      for row in cpt.rows]}
            for nid, cpt in cpt_map.items()
        ], human=lambda: None)
        return
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
    if json_mode():
        labels = _labels()
        emit({"ready": not gaps, "gaps": [
            {"node": labels.get(g.element_id, g.element_label or g.element_id), "gap": g.gap_type, "detail": g.message}
            for g in gaps
        ]}, human=lambda: None)
        return
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
def marginals(
    record: bool = typer.Option(True, "--record/--no-record", help="Save the result for reports + log a run."),
) -> None:
    """Show prior marginal distributions for every node."""
    from latris.operations import bn as bn_ops

    result = bn_ops.infer()
    recorded = bn_ops.record_query(result) if record and result.marginals else None
    _print_marginals(result, header="Prior marginals", recorded=recorded)


@app.command("query")
@handle_cli_errors
def query(
    evidence: list[str] | None = typer.Option(None, "--evidence", "-e", help="Observed node=state (repeatable)."),
    query_nodes: list[str] | None = typer.Option(None, "--query", "-q", help="Node to compute (repeatable)."),
    soft: list[str] | None = typer.Option(
        None, "--soft", "-s", help="Soft evidence 'Node=state:0.8' (80% sure) or 'Node=a:0.6,b:0.4' (repeatable)."),
    likelihood: list[str] | None = typer.Option(
        None, "--likelihood", help="Likelihood evidence 'Node=yes:4,no:1' (the observation favours yes 4:1)."),
    record: bool = typer.Option(True, "--record/--no-record", help="Save the result for reports + log a run."),
) -> None:
    """Compute posterior marginals given evidence (recorded, so reports can show the posteriors).

    Hard evidence (-e Wet=yes) says a node is observed. Soft evidence (-s Wet=yes:0.8)
    says how sure you are: afterwards P(Wet = yes) is 0.8, and the other states share
    the rest. --likelihood gives how much an observation favours each state instead.
    """
    from latris.operations import bn as bn_ops

    ev = _evidence(evidence)
    result = bn_ops.infer(query=query_nodes or None, evidence=ev or None, soft=_dists(soft) or None,
                          likelihood=_dists(likelihood) or None)
    # result.evidence is keyed by resolved node ID, so labels resolve cleanly
    # in the header (the raw ``ev`` keys are user input — IDs, prefixes, or
    # labels — and wouldn't match the node-ID-keyed label map).
    recorded = bn_ops.record_query(result) if record and result.marginals else None
    _print_marginals(result, header="Posterior marginals", evidence=result.evidence, recorded=recorded)


def _evidence(items: list[str] | None) -> dict[str, str]:
    ev: dict[str, str] = {}
    for item in items or []:
        if "=" not in item:
            raise typer.BadParameter(f"Evidence must be 'node=state', got {item!r}")
        name, state = item.rsplit("=", 1)
        ev[name.strip()] = state.strip()
    return ev


def _dists(items: list[str] | None) -> dict[str, dict[str, float]]:
    from latris.operations import bn as bn_ops

    out: dict[str, dict[str, float]] = {}
    for item in items or []:
        try:
            node, dist = bn_ops.parse_distribution(item)
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
        out[node] = dist
    return out


@app.command("explain")
@handle_cli_errors
def explain(
    evidence: list[str] | None = typer.Option(None, "--evidence", "-e", help="Observed node=state (repeatable)."),
    soft: list[str] | None = typer.Option(None, "--soft", "-s", help="Soft evidence 'Node=state:0.8' (repeatable)."),
    likelihood: list[str] | None = typer.Option(None, "--likelihood", help="Likelihood evidence 'Node=yes:4,no:1'."),
    over: list[str] | None = typer.Option(
        None, "--over", help="Explain only these nodes (MAP); default every unobserved node (MPE)."),
    record: bool = typer.Option(True, "--record/--no-record", help="Save the result for reports + log a run."),
) -> None:
    """The single most likely combination of states, given the evidence.

    "Given the flood, what's the likeliest combination of causes?" Shows the
    combination, how probable it is, how many times likelier each state is than
    its runner-up, and where a node's own favourite differs from the combination.
    """
    from latris.operations import bn as bn_ops

    out = bn_ops.explain(over=over or None, evidence=_evidence(evidence) or None, soft=_dists(soft) or None,
                         likelihood=_dists(likelihood) or None)
    recorded = bn_ops.record_explanation(out) if record else None
    labels = out["labels"]
    if json_mode():
        emit({
            "summary": bn_ops.describe_explanation(out), "kind": out["kind"], "probability": out["probability"],
            "explanation": [{
                "node": labels.get(r["node"], r["node"]), "state": r["state"], "own_probability": r["marginal"],
                "runner_up": r["runner_up"], "times_likelier": r["times_likelier"],
                "alternatives_impossible": r["alternatives_impossible"],
                "differs_from_own_favourite": r["differs_from_marginal"], "own_favourite": r["favourite"],
            } for r in out["rows"]],
            "note": out["note"], "run_id": recorded[1] if recorded else None,
        }, human=lambda: None, commit_sha=recorded[0] if recorded else None)
        return
    console.print(f"[bold]{escape(bn_ops.describe_explanation(out))}[/bold]\n")
    table = Table(show_header=True, header_style="bold")
    for col in ("Node", "Most likely", "Its own probability", "vs runner-up"):
        table.add_column(col)
    for r in out["rows"]:
        if r["alternatives_impossible"]:
            vs = "the alternatives are impossible"
        elif r["times_likelier"] is not None:
            vs = f"{r['times_likelier']:.3g}× likelier than {r['runner_up']}"
        else:
            vs = ""
        own = f"{r['marginal']:.1%}" if r["marginal"] is not None else ""
        if r["differs_from_marginal"]:
            own += f" [yellow](on its own, {r['favourite']} is likelier)[/yellow]"
        table.add_row(escape(labels.get(r["node"], r["node"])), escape(r["state"]), own, vs)
    console.print(table)
    if out["note"]:
        console.print(f"[dim]{escape(out['note'])}[/dim]")
    if recorded:
        sha, run_id = recorded
        console.print(f"\n[green]recorded[/green] · run [cyan]{run_id[:18]}…[/cyan] · commit [cyan]{sha[:10]}[/cyan]")


@app.command("set-uncertainty")
@handle_cli_errors
def set_uncertainty(
    node: str = typer.Argument(..., help="The node whose probability table is uncertain."),
    n: float = typer.Option(..., "--n", help="How many observations the table is worth (small = a rough guess)."),
    row: str | None = typer.Option(None, "--row", help="Just one row: 'Parent=state,Other=state'."),
    reason: str = typer.Option("", "--reason", help="Why this much confidence (e.g. 'elicited from two experts')."),
    source: str | None = typer.Option(None, "--source", help="Source ID backing it."),
    origin: str = typer.Option("human-direct", "--origin", help="Provenance origin."),
) -> None:
    """Say how well a probability table is known: "worth about n observations".

    `bn monte-carlo` then samples each row around its current values (a Dirichlet):
    n = 5 is a rough expert guess, n = 500 a table learned from plenty of data.
    """
    from latris.operations import uncertainty

    entry, sha = uncertainty.set_table_uncertainty(node, n, row=row, reason=reason, source_id=source,
                                                   origin=origin)  # type: ignore[arg-type]
    label = _labels().get(entry.target_id, entry.target_id)
    if json_mode():
        emit({"node": label, "n": n, "row": row, "origin": entry.origin}, human=lambda: None, commit_sha=sha)
        return
    where = f" (row {escape(row)})" if row else ""
    console.print(f"[green]uncertainty[/green] {escape(label)}{where}: worth {n:g} observations · "
                  f"commit [cyan]{sha[:10]}[/cyan]")


@app.command("uncertainty")
@handle_cli_errors
def list_uncertainty() -> None:
    """List how well each probability table is known (tables not listed are held fixed)."""
    from latris.operations import uncertainty
    from latris.repo.project import require_project

    specs = uncertainty.bn_specs(require_project(None))
    labels = _labels()
    rows = [{"node": labels.get(node, node), "cell": cell, "n": e.params["n"], "reason": e.reason,
             "origin": e.origin, "verification": e.verification}
            for node, cells in specs.items() for cell, e in cells.items()]
    if json_mode():
        emit(rows, human=lambda: None)
        return
    if not rows:
        console.print("No table uncertainty yet. Add one with `latris bn set-uncertainty <node> --n 20`.")
        return
    table = Table(show_header=True, header_style="bold")
    for col in ("Node", "Applies to", "Worth n", "Origin", "Reason"):
        table.add_column(col)
    for r in rows:
        where = "whole table" if r["cell"] == "bn:cpt" else r["cell"].split(":", 2)[-1]
        table.add_row(escape(r["node"]), escape(where), f"{r['n']:g}", r["origin"], escape(r["reason"]))
    console.print(table)


@app.command("clear-uncertainty")
@handle_cli_errors
def clear_uncertainty(node: str = typer.Argument(..., help="Node ID, prefix or label.")) -> None:
    """Hold a table fixed again in Monte Carlo runs."""
    from latris.operations import uncertainty

    sha = uncertainty.clear_uncertainty(node)
    if json_mode():
        emit({"cleared": node}, human=lambda: None, commit_sha=sha)
        return
    console.print(f"[green]cleared[/green] uncertainty on {escape(node)} · commit [cyan]{sha[:10]}[/cyan]")


@app.command("monte-carlo")
@handle_cli_errors
def monte_carlo(
    target: str = typer.Argument(..., help="The node whose probability you want to stress-test."),
    state: str | None = typer.Option(None, "--state", help="The state to report on (default: the first state)."),
    evidence: list[str] | None = typer.Option(None, "--evidence", "-e", help="Observed node=state (repeatable)."),
    soft: list[str] | None = typer.Option(None, "--soft", "-s", help="Soft evidence 'Node=state:0.8' (repeatable)."),
    likelihood: list[str] | None = typer.Option(None, "--likelihood", help="Likelihood evidence 'Node=yes:4,no:1'."),
    runs: int = typer.Option(500, "--runs", "-n", help="Number of draws (2–2000)."),
    seed: int = typer.Option(1234, "--seed", help="Random seed; the same seed gives the same draws."),
    max_seconds: float = typer.Option(60.0, "--max-seconds", help="Stop early if the draws would take longer."),
    record: bool = typer.Option(True, "--record/--no-record", help="Save the result for reports + log a run."),
) -> None:
    """How sure is this probability? Re-asks the query while sampling the uncertain tables.

    Tables given an uncertainty with `bn set-uncertainty` are sampled around their
    values; the rest stay fixed. Shows the point estimate, the median and the range
    95% of draws fall in, and which tables drive the spread.
    """
    from latris.operations import bn as bn_ops
    from latris.operations.bn_montecarlo import describe

    out = bn_ops.run_monte_carlo(target, state=state, evidence=_evidence(evidence) or None, soft=_dists(soft) or None,
                                 likelihood=_dists(likelihood) or None, runs=runs, seed=seed,
                                 max_seconds=max_seconds)
    recorded = bn_ops.record_monte_carlo(out) if record else None
    if json_mode():
        emit({
            "summary": describe(out), "runs": out["runs"], "seed": out["seed"],
            "states": {s: out["by_state"][s] for s in out["states"]},
            "tables": [{k: v for k, v in t.items() if k != "node"} for t in out["tables"]],
            "drivers": [{"table": d["label"], "rank_correlation": d["rho"]} for d in out["drivers"]],
            "run_id": recorded[1] if recorded else None,
        }, human=lambda: None, commit_sha=recorded[0] if recorded else None)
        return
    console.print(f"[bold]{escape(describe(out))}[/bold]\n")
    table = Table(show_header=True, header_style="bold")
    for col, justify in (("State", "left"), ("Point", "right"), ("Median", "right"), ("50% of draws", "right"),
                         ("95% of draws", "right")):
        table.add_column(col, justify=justify)  # type: ignore[arg-type]
    for st in out["states"]:
        b = out["by_state"][st]
        table.add_row(escape(st), f"{b['point']:.1%}", f"{b['p50']:.1%}", f"{b['p25']:.1%}–{b['p75']:.1%}",
                      f"{b['p2.5']:.1%}–{b['p97.5']:.1%}")
    console.print(table)
    for t in out["tables"]:
        if t["fixed"]:
            continue
        flag = "" if t["verification"] == "human-verified" else f" [yellow]({t['origin']}, unverified)[/yellow]"
        n = f"worth {t['n']:g}" if t["n"] else "row overrides only"
        console.print(f"  {escape(t['label'])}: {n}{flag}" + (f" — {escape(t['reason'])}" if t["reason"] else ""))
    fixed = [t["label"] for t in out["tables"] if t["fixed"]]
    if fixed:
        console.print(f"  [dim]held fixed: {escape(', '.join(fixed))}[/dim]")
    drivers = [d for d in out["drivers"] if d["rho"] is not None][:3]
    if drivers:
        console.print("  driven by: " + ", ".join(f"{escape(d['label'])} (ρ={d['rho']:+.2f})" for d in drivers))
    if recorded:
        sha, run_id = recorded
        console.print(f"\n[green]recorded[/green] · run [cyan]{run_id[:18]}…[/cyan] · commit [cyan]{sha[:10]}[/cyan]")


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
    if json_mode():
        payload = {
            "target": labels.get(result.target_id, result.target_id), "state": result.target_state,
            "baseline": round(result.baseline, 4),
            "given": {labels.get(k, k): v for k, v in (result.evidence or {}).items()},
            "parameters": [
                {"node": labels.get(f.node_id, f.node_id),
                 "given": {labels.get(k, k): v for k, v in f.parent_states.items()},
                 "state": f.state, "influence": round(f.influence, 4), "origin": f.origin,
                 "human_verified": f.verification == "human-verified", "weakly_grounded": bool(f.weak)}
                for f in result.findings
            ],
        }
        sha = bn_sensitivity.record_sensitivity(result)[0] if record else None
        emit(payload, human=lambda: None, commit_sha=sha)
        return
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


def _print_marginals(
    result, *, header: str, evidence: dict[str, str] | None = None, recorded: tuple[str, str] | None = None
) -> None:
    labels = _labels()
    if json_mode():
        emit({
            "given": {labels.get(k, k): v for k, v in (evidence or {}).items()},
            "soft": {labels.get(k, k): v for k, v in result.soft.items()},
            "likelihood": {labels.get(k, k): v for k, v in result.likelihood.items()},
            "marginals": {labels.get(nid, nid): {s: round(p, 4) for s, p in dist.items()}
                          for nid, dist in result.marginals.items()},
            "run_id": recorded[1] if recorded else None,
        }, human=lambda: None, commit_sha=recorded[0] if recorded else None)
        return
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
    if recorded:
        sha, run_id = recorded
        console.print(f"\n[green]recorded[/green] · run [cyan]{run_id[:18]}…[/cyan] · commit [cyan]{sha[:10]}[/cyan]")
