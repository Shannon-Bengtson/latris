from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape

from latris.cli._agent import CONFIRMED_BY_PERSON, default_by, require_person
from latris.cli._errors import handle_cli_errors
from latris.cli._output import emit
from latris.operations import build as build_ops

console = Console()


@handle_cli_errors
def build(
    spec: str = typer.Option(..., "--spec", help="YAML or JSON file describing the model; '-' reads stdin."),
    verified_by: str = typer.Option(
        None,
        "--verified-by",
        help="human | ai — who verified the citations in the spec apply (default: human; ai when an AI "
        "agent runs this).",
    ),
    confirmed_by_person: bool = CONFIRMED_BY_PERSON,
) -> None:
    """Add a whole model from one spec, as one commit.

    The spec is checked in full first; if anything doesn't resolve, nothing
    is changed. `latris docs` has a worked example. Keys:

    - ``context``: background, audience, boundary, intuition (what the
      person expects the answer to be) — the top of the report
    - ``factors``: label, kind, description, sources, contradicts
    - ``links``: from, to, polarity (+ or -), reason, confidence
      (low | medium | high | quantitative-pending | by-definition),
      sources, contradicts
    - ``sources``: key, title, authors, year, container, doi, url, notes,
      extract (the text you read), extract_url, extract_kind, cited_via (the source it was read in)
    - ``assumptions``: text, or text + target + rationale
    - ``questions``: text
    - ``findings``: statement, category (structure | dynamics |
      sensitivity | inference | diagnostics | recommendations), detail,
      targets — recorded as proposed; a person approves them
    - ``challenges``: argument, target
    - ``decisions``: statement, rationale, target
    - ``interpretation``: section, prose, by (ai | human)
    - ``outcome``: the factor the model explains (in a theory of change, the
      impact; in a fault tree or bow-tie, the top event)
    - ``sd``: roles, stocks, constants, equations, tables, uncertainty
      (node, distribution, params, reason), scenarios (name, set:
      ["Variable=value units"], extends, description, reason)
    - ``bn``: states, tables (node, parents, probabilities), noisy_or,
      uncertainty, scenarios (name, extends, observe / set: {node: state},
      soft / likelihood: {node: {state: value}}, tables:
      ["Node[Parent=state]=p1,p2"], description, reason)
    - ``toc``: levels (node, level: input | activity | output |
      short_term_outcome | long_term_outcome | impact)
    - ``ft``: events (node, type: top_event | intermediate_event |
      basic_event | undeveloped_event), gates (node, gate: and | or | vote,
      k), probabilities (node, probability, source, origin, verified, notes)
    - ``bowtie``: elements (node, type: hazard | top_event | threat |
      consequence | barrier | escalation_factor), barriers (node, type,
      status, owner, pfd, source, origin, verified, notes), frequencies
      (node, frequency per year, source, origin, verified, notes)
    - ``event_tree``: elements (node, type: initiating_event |
      functional_event | end_state), order (heading labels, left to right),
      sequences (answers: {heading: yes|no}, end_state), probabilities
      (node, p_yes, given: {heading: yes|no}, source, origin, verified),
      frequency (node, frequency per year, …)
    - ``mcda``: elements (node, type: option | criterion), criteria (node,
      weight, direction: higher | lower, worst, best, units, source, …),
      scores (option, criterion, value, source, origin, verified, notes)
    - ``ach``: elements (node, type: hypothesis | evidence_item), items
      (node, credibility, relevance: high | medium | low, source, …),
      ratings (item, hypothesis, rating: CC | C | N | I | II, rationale)
    - ``decision_tree``: objective (maximise | minimise), units, nodes (node,
      type: decision | chance | terminal), branches (link "Parent -> Child",
      label, probability, value, source, …), payoffs (node, value, source,
      …), uncertainties (node, uncertainty)
    - ``markov``: elements (node, type: state | strategy), settings
      (cycle_length, num_cycles, time_units, discount_rate,
      outcome_discount_rate, half_cycle_correction, wtp, cost_units,
      outcome_units), transitions (link "From -> To", probability, strategy,
      source, …), rewards (state, strategy, cost, utility, source, …), start
      (state, proportion)
    - ``analyses``: kind (simulate | monte_carlo | sensitivity | loops |
      bn_query | bn_explain | bn_monte_carlo | bn_compare | bn_sensitivity | toc_check |
      ft_analyse | bowtie_analyse | et_analyse | dag_estimate: treatment,
      outcome, dataset, adjust, columns, estimator | mcda_analyse |
      ach_analyse | dt_analyse | markov_analyse)
      + its options — run and recorded after building, so the report shows them

    Targets are factor labels or links written "From -> To". Quote YAML
    values that contain a colon.
    """
    verified_by = default_by(verified_by)
    if verified_by not in {"human", "ai"}:
        raise ValueError("--verified-by must be 'human' or 'ai'.")
    if verified_by == "human":
        require_person(confirmed_by_person, "--verified-by human")
    text = sys.stdin.read() if spec == "-" else Path(spec).read_text(encoding="utf-8")
    result = build_ops.build_from_spec(build_ops.load_spec(text), verified_by=verified_by)
    emit(
        asdict(result),
        commit_sha=result.commit_sha,
        human=lambda: console.print(
            f"[green]built[/green] {result.factors} factors, {len(result.links)} links, "
            f"{result.sources} sources, {result.citations} citations, {result.assumptions} assumptions, "
            f"{result.questions} questions"
            + (f", {result.parameters} parameters" if result.parameters else "")
            + (f", {len(result.analyses)} analyses run" if result.analyses else "")
            + f" · commit [cyan]{result.commit_sha[:10]}[/cyan]"
            + "".join(f"\n[yellow]note:[/yellow] {escape(n)}" for n in result.notes)
        ),
    )
    if result.missing_extras:
        # The model is built, but analyses it asked for didn't run: that must not look like success.
        raise typer.Exit(code=1)
