from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from latris.ai import call as call_module
from latris.ai import config as ai_config
from latris.ai import credentials as creds
from latris.ai import delegated as delegated_module
from latris.ai import interactions as inter_ops
from latris.ai import prompts as prompt_lib
from latris.ai.render import render as ai_render
from latris.cli._errors import handle_cli_errors
from latris.repo import git
from latris.repo.project import require_project
from latris.schema import HumanActor
from latris.schema.ids import id_timestamp

app = typer.Typer(
    help="AI layer — canonical prompts, interaction log, credentials, config.",
    no_args_is_help=True,
)
console = Console()

prompts_app = typer.Typer(help="Canonical prompt library.", no_args_is_help=True)
interactions_app = typer.Typer(
    help="Project-local AI interaction log (bespoke memory).",
    no_args_is_help=True,
)
key_app = typer.Typer(help="Manage API keys (stored in OS keyring).", no_args_is_help=True)
config_app = typer.Typer(help="Project-level AI defaults.", no_args_is_help=True)
call_app = typer.Typer(help="Run an AI prompt against the current project.", no_args_is_help=True)
task_app = typer.Typer(
    help="Delegated AI tasks — answer Latris prompts with an external agent (no API key needed).",
    no_args_is_help=True,
)
app.add_typer(prompts_app, name="prompts")
app.add_typer(interactions_app, name="interactions")
app.add_typer(key_app, name="key")
app.add_typer(config_app, name="config")
app.add_typer(call_app, name="call")
app.add_typer(task_app, name="task")


# ---------- prompts ----------


@prompts_app.command("list")
@handle_cli_errors
def prompts_list() -> None:
    """List the canonical prompts the AI layer supports."""
    specs = prompt_lib.list_all()
    table = Table(show_header=True, header_style="bold")
    table.add_column("Name", style="cyan")
    table.add_column("Title")
    table.add_column("Scope")
    table.add_column("Intent")
    table.add_column("Status")
    for p in specs:
        wired = p.name in call_module.RESPONSE_MODELS
        status = "[green]wired[/green]" if wired else "[yellow]spec only[/yellow]"
        table.add_row(p.name, p.title, p.scope.value, p.intent.value, status)
    console.print(table)
    wired_count = sum(1 for p in specs if p.name in call_module.RESPONSE_MODELS)
    console.print(f"\n[dim]{len(specs)} prompts registered, {wired_count} wired.[/dim]")


@prompts_app.command("show")
@handle_cli_errors
def prompts_show(
    name: str = typer.Argument(..., help="Prompt name, e.g. 'ChallengeThisConnection'."),
) -> None:
    """Show a prompt's template and input schema."""
    try:
        spec = prompt_lib.get(name)
    except KeyError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(f"[bold]{spec.name}[/bold] — {spec.title}")
    console.print(f"[dim]{spec.description}[/dim]\n")

    console.print("[bold]Inputs:[/bold]")
    for field_name, field in spec.inputs.model_fields.items():
        default = "" if field.is_required() else f" (default: {field.default!r})"
        desc = f" — {field.description}" if field.description else ""
        console.print(f"  • [cyan]{field_name}[/cyan]: {field.annotation}{default}{desc}")

    console.print("\n[bold]Template:[/bold]")
    console.print(spec.template)

    console.print(f"\n[bold]Expected output:[/bold] [dim]{spec.output_hint}[/dim]")


# ---------- interactions ----------


@interactions_app.command("list")
@handle_cli_errors
def interactions_list(
    target: str = typer.Option(
        None,
        "--target",
        "-t",
        help="Only show interactions touching this target ID.",
    ),
    prompt: str = typer.Option(
        None,
        "--prompt",
        "-p",
        help="Filter by prompt name.",
    ),
    adoption: str = typer.Option(
        None,
        "--adoption",
        help="Filter by adoption state: pending | approved | rejected.",
    ),
    limit: int = typer.Option(20, "--limit", "-n", help="Max records (newest first)."),
) -> None:
    """List AI interactions recorded against this project (newest first)."""
    if adoption is not None and adoption not in ("pending", "approved", "rejected"):
        raise typer.BadParameter("--adoption must be pending | approved | rejected")
    records = inter_ops.list_interactions(
        target_id=target,
        prompt_name=prompt,
        adoption=adoption,  # type: ignore[arg-type]
        limit=limit,
    )
    if not records:
        console.print("[dim](no interactions recorded yet)[/dim]")
        return
    table = Table(show_header=True, header_style="bold")
    table.add_column("ID", style="cyan")
    table.add_column("When")
    table.add_column("Prompt")
    table.add_column("Model")
    table.add_column("Adoption")
    table.add_column("Summary")
    for r in records:
        adoption_style = {
            "approved": "green",
            "rejected": "red",
            "pending": "yellow",
        }[r.adoption]
        summary = r.response_summary
        if len(summary) > 50:
            summary = summary[:47] + "…"
        table.add_row(
            r.id[:20] + "…",
            id_timestamp(r.id).date().isoformat(),
            r.prompt_name,
            r.model_id,
            f"[{adoption_style}]{r.adoption}[/{adoption_style}]",
            summary,
        )
    console.print(table)


@interactions_app.command("show")
@handle_cli_errors
def interactions_show(
    interaction: str = typer.Argument(..., help="Interaction ID or prefix."),
) -> None:
    """Show a single interaction in full."""
    r = inter_ops.get_interaction(interaction)
    console.print(f"[bold]id:[/bold] {r.id}")
    console.print(f"[bold]timestamp:[/bold] {id_timestamp(r.id).isoformat()}")
    console.print(f"[bold]prompt:[/bold] {r.prompt_name}")
    console.print(f"[bold]model:[/bold] {r.model_id}")
    if r.target_ids:
        console.print(f"[bold]target_ids:[/bold] {', '.join(r.target_ids)}")
    if r.related_attributes:
        console.print(f"[bold]related_attributes:[/bold] {', '.join(r.related_attributes)}")
    console.print(f"[bold]adoption:[/bold] {r.adoption}")
    if r.approved_by:
        console.print(f"[bold]approved_by:[/bold] {r.approved_by.name}")
    console.print(f"[bold]summary:[/bold] {r.response_summary}")
    if r.response_full:
        console.print("[bold]full response:[/bold]")
        console.print(r.response_full)
    if r.prompt_inputs:
        console.print(f"[bold]inputs:[/bold] {r.prompt_inputs}")
    if r.proposal_ids:
        console.print(f"[bold]proposal_ids:[/bold] {', '.join(r.proposal_ids)}")
    if r.token_usage:
        console.print(f"[bold]token_usage:[/bold] {r.token_usage}")
    if r.cost_usd is not None:
        console.print(f"[bold]cost_usd:[/bold] ${r.cost_usd:.6f}")


# ---------- key ----------


@key_app.command("set")
@handle_cli_errors
def key_set(
    provider: str = typer.Argument(
        ...,
        help=(
            "Provider name (anthropic | openai | gemini | groq | ...). "
            "See `latris ai key list` for known env-var mappings."
        ),
    ),
) -> None:
    """Store an API key for ``provider`` in the OS keyring.

    The value is prompted via stdin with input hidden — never read from argv,
    so it won't appear in shell history or process listings.
    """
    value = typer.prompt(f"API key for {provider}", hide_input=True, confirmation_prompt=False)
    value = value.strip()
    if not value:
        console.print("[red]refusing to store empty key[/red]")
        raise typer.Exit(code=2)
    creds.set_key(provider, value)
    env_var = creds.PROVIDER_ENV.get(provider.lower())
    hint = f" (picked up as {env_var} at call time)" if env_var else ""
    console.print(f"[green]stored[/green] key for [bold]{provider}[/bold]{hint}")


@key_app.command("list")
@handle_cli_errors
def key_list() -> None:
    """List providers with a configured key. Never prints key values."""
    providers = creds.list_providers()
    if not providers:
        console.print("[dim](no keys configured) — set one with `latris ai key set <provider>`.[/dim]")
        return
    table = Table(show_header=True, header_style="bold")
    table.add_column("Provider", style="cyan")
    table.add_column("Source")
    table.add_column("Env var")
    for p in providers:
        source_style = "green" if p["source"] == "env" else "magenta"
        table.add_row(
            p["provider"],
            f"[{source_style}]{p['source']}[/{source_style}]",
            p.get("env_var") or "",
        )
    console.print(table)


@key_app.command("unset")
@handle_cli_errors
def key_unset(
    provider: str = typer.Argument(..., help="Provider to remove from the keyring."),
) -> None:
    removed = creds.unset_key(provider)
    if removed:
        console.print(f"[green]removed[/green] key for {provider}")
    else:
        console.print(f"[yellow]no keyring entry[/yellow] for {provider}")


# ---------- config ----------


@config_app.command("show")
@handle_cli_errors
def config_show() -> None:
    """Print the project's AI config (or defaults if no file exists)."""
    paths = require_project()
    cfg = ai_config.load(paths)
    table = Table(show_header=True, header_style="bold")
    table.add_column("Key", style="cyan")
    table.add_column("Value")
    for field_name, value in cfg.model_dump().items():
        table.add_row(field_name, str(value))
    console.print(table)
    p = ai_config.config_path(paths)
    if p.exists():
        console.print(f"[dim]source: {p.relative_to(paths.root).as_posix()}[/dim]")
    else:
        console.print("[dim](using built-in defaults — no ai_config.yaml yet)[/dim]")


@config_app.command("set")
@handle_cli_errors
def config_set(
    key: str = typer.Argument(..., help="default_model | temperature | max_tokens"),
    value: str = typer.Argument(..., help="New value for the key."),
) -> None:
    """Update an AI config value. Writes to .graph-tooling/ai_config.yaml."""
    paths = require_project()
    cfg = ai_config.load(paths)
    coerced: object
    if key in ("temperature",):
        coerced = float(value)
    elif key in ("max_tokens",):
        coerced = int(value)
    elif key in ("default_model",):
        coerced = value
    else:
        console.print(f"[red]unknown config key: {key}[/red]")
        raise typer.Exit(code=2)
    updated = cfg.model_copy(update={key: coerced})
    # Re-validate via the model (catches range checks, secret-leak guard).
    updated = ai_config.AIConfig.model_validate(updated.model_dump())
    path = ai_config.save(paths, updated)
    console.print(f"[green]wrote[/green] {key} = {coerced!r} → {path.relative_to(paths.root).as_posix()}")


# ---------- call ----------
#
# Rendering of AI results is owned by latris.ai.render (shared with the
# server). `render(prompt_name, parsed)` dispatches via its RENDERERS table and
# falls back to a JSON dump for any prompt without a bespoke renderer.


def _resolve_approver() -> HumanActor:
    """Derive the HumanActor from git identity."""
    paths = require_project()
    name, email = git.ensure_identity(paths.root)
    return HumanActor(name=name, email=email)


def _confirm_fn(assume_yes: bool):
    if assume_yes:
        return lambda rendered, parsed=None: True

    def ask(rendered: str, parsed=None) -> bool:
        console.print()
        console.print("[bold]Proposal:[/bold]")
        console.print(rendered)
        console.print()
        return typer.confirm("Apply this proposal?", default=False)

    return ask


def _print_call_outcome(*, prompt_name: str, outcome: call_module.CallOutcome) -> None:
    """Print the shared post-call summary: prose for read-only/hybrid prompts,
    then the adoption line with interaction id, model, and cost."""
    # For read-only and hybrid prompts, the rendered prose IS part of the
    # deliverable (read-only: prose only; hybrid: prose + bounded mutation).
    # Print it before the outcome summary so the user sees the critique,
    # not just the bookkeeping. For pure-mutating prompts, the user already
    # saw the rendered proposal during the [y/N] confirmation in interactive
    # mode — no need to re-print there.
    if (
        prompt_name in call_module.READ_ONLY_PROMPTS
        or prompt_name in call_module.HYBRID_PROMPTS
    ) and outcome.rendered:
        console.print()
        # markup=False/highlight=False: don't let rich interpret brackets or
        # quotes in the model's prose as style tags.
        console.print(outcome.rendered, markup=False, highlight=False)
        console.print()

    usage = outcome.token_usage or {}
    cost = f"${outcome.cost_usd:.4f}" if outcome.cost_usd else "—"
    if outcome.adoption == "approved":
        console.print(
            f"[green]approved[/green] · interaction [cyan]{outcome.interaction_id[:20]}…[/cyan]"
            f" · model [magenta]{outcome.model}[/magenta] · cost {cost}" + (f" · tokens {usage}" if usage else "")
        )
        if outcome.applied_ids:
            console.print(f"[green]applied[/green]: {', '.join(outcome.applied_ids)}")
    else:
        console.print(
            f"[yellow]rejected[/yellow] · interaction [cyan]{outcome.interaction_id[:20]}…[/cyan]"
            f" · model [magenta]{outcome.model}[/magenta] · cost {cost}"
        )


def _run(
    *,
    prompt_name: str,
    inputs: dict,
    model: str | None,
    assume_yes: bool,
    dry_run: bool,
) -> None:
    approver = _resolve_approver()

    def render_parsed(parsed):
        return ai_render(prompt_name, parsed)

    outcome = call_module.run_call(
        prompt_name=prompt_name,
        inputs=inputs,
        model_override=model,
        approver=approver,
        confirm=_confirm_fn(assume_yes),
        render=render_parsed,
        dry_run=dry_run,
    )

    if dry_run:
        console.print("[yellow]dry-run[/yellow] — no adapter call, no log write.")
        console.print(outcome.applied_ids[0] if outcome.applied_ids else "(empty)")
        return

    _print_call_outcome(prompt_name=prompt_name, outcome=outcome)


@call_app.command("explain")
@handle_cli_errors
def call_explain(
    target: str = typer.Argument(..., help="Node or edge to explain (ID / prefix / label)."),
    model: str = typer.Option(None, "--model", "-m"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Assemble prompt, no API call."),
    yes: bool = typer.Option(
        False, "--yes", "-y", hidden=True, help="Accepted for symmetry; this command is read-only."
    ),
) -> None:
    """ExplainThisElement — read-only prose explanation, logged only."""
    _run(
        prompt_name="ExplainThisElement",
        inputs={"target_id": target},
        model=model,
        assume_yes=yes,
        dry_run=dry_run,
    )


@call_app.command("challenge")
@handle_cli_errors
def call_challenge(
    target: str = typer.Argument(..., help="Node or edge to challenge."),
    attribute: str = typer.Option(None, "--attribute", "-a", help="Specific attribute (e.g. 'polarity')."),
    model: str = typer.Option(None, "--model", "-m"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    yes: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    """ChallengeThisConnection — AI drafts a challenge; you approve or reject."""
    _run(
        prompt_name="ChallengeThisConnection",
        inputs={"target_id": target, "target_attribute": attribute},
        model=model,
        assume_yes=yes,
        dry_run=dry_run,
    )


@call_app.command("draft")
@handle_cli_errors
def call_draft(
    focus: str = typer.Argument(..., help="Phenomenon or question to draft a model around."),
    candidate_count: int = typer.Option(3, "--count", "-c", help="Number of framings (1-5)."),
    bibkeys: str = typer.Option("", "--bibkeys", "-b", help="Comma-separated bibkeys to ground in."),
    model: str = typer.Option(None, "--model", "-m"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    yes: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    """DraftConceptualModel — AI generates candidate framings; you pick one."""
    refs = [b.strip() for b in bibkeys.split(",") if b.strip()] if bibkeys else []
    approver = _resolve_approver()

    def render_parsed(parsed):
        return ai_render("DraftConceptualModel", parsed)

    def confirm_draft(rendered: str, parsed=None) -> bool:
        if yes:
            if parsed and hasattr(parsed, "selected_index") and parsed.framings:
                parsed.selected_index = 0
            return True
        console.print()
        console.print("[bold]Candidate framings:[/bold]")
        console.print(rendered)
        console.print()
        if not parsed or not parsed.framings:
            return False
        choice = typer.prompt(
            f"Pick a framing index (0-{len(parsed.framings) - 1}), or 'none' to reject",
            default="none",
        )
        if choice.strip().lower() == "none":
            return False
        try:
            idx = int(choice)
            if idx < 0 or idx >= len(parsed.framings):
                console.print(f"[red]Index {idx} out of range[/red]")
                return False
            parsed.selected_index = idx
            return True
        except ValueError:
            console.print("[red]Invalid input[/red]")
            return False

    outcome = call_module.run_call(
        prompt_name="DraftConceptualModel",
        inputs={"focus": focus, "candidate_count": candidate_count, "reference_bibkeys": refs},
        model_override=model,
        approver=approver,
        confirm=confirm_draft,
        render=render_parsed,
        dry_run=dry_run,
    )

    if dry_run:
        console.print("[yellow]dry-run[/yellow]")
        console.print(outcome.applied_ids[0] if outcome.applied_ids else "(empty)")
        return

    cost = f"${outcome.cost_usd:.4f}" if outcome.cost_usd else "—"
    if outcome.adoption == "approved":
        console.print(
            f"[green]approved[/green] · interaction [cyan]{outcome.interaction_id[:20]}…[/cyan]"
            f" · model [magenta]{outcome.model}[/magenta] · cost {cost}"
        )
        if outcome.applied_ids:
            console.print(f"[green]applied[/green]: {', '.join(outcome.applied_ids)}")
    else:
        console.print(f"[yellow]rejected[/yellow] · interaction [cyan]{outcome.interaction_id[:20]}…[/cyan]")


@call_app.command("attack")
@handle_cli_errors
def call_attack(
    scope_nodes: str = typer.Option("", "--scope-nodes", "-s", help="Comma-separated node IDs to focus on."),
    model: str = typer.Option(None, "--model", "-m"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    yes: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    """AttackThisModel — AI identifies the weakest assumption (read-only)."""
    node_ids = [n.strip() for n in scope_nodes.split(",") if n.strip()] if scope_nodes else []
    _run(
        prompt_name="AttackThisModel",
        inputs={"scope_node_ids": node_ids},
        model=model,
        assume_yes=yes,
        dry_run=dry_run,
    )


@call_app.command("find-counter-pathway")
@handle_cli_errors
def call_find_counter_pathway(
    scope_nodes: str = typer.Option("", "--scope-nodes", "-s", help="Comma-separated node IDs to focus on."),
    model: str = typer.Option(None, "--model", "-m"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    yes: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    """FindCounterPathway — surface the strongest missing counter-mechanism."""
    node_ids = [n.strip() for n in scope_nodes.split(",") if n.strip()] if scope_nodes else []
    _run(
        prompt_name="FindCounterPathway",
        inputs={"scope_node_ids": node_ids},
        model=model,
        assume_yes=yes,
        dry_run=dry_run,
    )


@call_app.command("scope-check")
@handle_cli_errors
def call_scope_check(
    model: str = typer.Option(None, "--model", "-m"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    yes: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    """ScopeCheck — does the model address the project foundation? (read-only)"""
    _run(
        prompt_name="ScopeCheck",
        inputs={},
        model=model,
        assume_yes=yes,
        dry_run=dry_run,
    )


@call_app.command("find-connections")
@handle_cli_errors
def call_find_connections(
    focus_nodes: str = typer.Option("", "--focus-nodes", "-f", help="Comma-separated node IDs."),
    model: str = typer.Option(None, "--model", "-m"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    yes: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    """FindNewConnections — AI suggests missing edges; you pick which to apply."""
    node_ids = [n.strip() for n in focus_nodes.split(",") if n.strip()] if focus_nodes else []
    approver = _resolve_approver()

    def render_parsed(parsed):
        return ai_render("FindNewConnections", parsed)

    def confirm_connections(rendered: str, parsed=None) -> bool:
        if yes:
            if not parsed or not parsed.proposals:
                return False  # empty proposal set — treat --yes as a no-op, not an apply
            parsed.approved_indices = list(range(len(parsed.proposals)))
            return True
        console.print()
        console.print("[bold]Proposed new connections:[/bold]")
        console.print(rendered)
        console.print()
        if not parsed or not parsed.proposals:
            return False
        choice = typer.prompt(
            "Enter indices to approve (comma-separated, e.g. '0,2'), or 'none'",
            default="none",
        )
        if choice.strip().lower() == "none":
            return False
        try:
            indices = [int(x.strip()) for x in choice.split(",")]
            parsed.approved_indices = indices
            return True
        except ValueError:
            console.print("[red]Invalid input[/red]")
            return False

    outcome = call_module.run_call(
        prompt_name="FindNewConnections",
        inputs={"focus_node_ids": node_ids},
        model_override=model,
        approver=approver,
        confirm=confirm_connections,
        render=render_parsed,
        dry_run=dry_run,
    )

    if dry_run:
        console.print("[yellow]dry-run[/yellow]")
        console.print(outcome.applied_ids[0] if outcome.applied_ids else "(empty)")
        return

    cost = f"${outcome.cost_usd:.4f}" if outcome.cost_usd else "—"
    if outcome.adoption == "approved":
        console.print(
            f"[green]approved[/green] · interaction [cyan]{outcome.interaction_id[:20]}…[/cyan]"
            f" · model [magenta]{outcome.model}[/magenta] · cost {cost}"
        )
        if outcome.applied_ids:
            console.print(f"[green]applied[/green]: {', '.join(outcome.applied_ids)}")
    else:
        console.print(f"[yellow]rejected[/yellow] · interaction [cyan]{outcome.interaction_id[:20]}…[/cyan]")


@call_app.command("suggest-citations")
@handle_cli_errors
def call_suggest_citations(
    target: str = typer.Argument(..., help="Node or edge needing citation."),
    attribute: str = typer.Argument(..., help="Attribute needing citation (e.g. 'description')."),
    model: str = typer.Option(None, "--model", "-m"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    yes: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    """SuggestCitations — AI proposes references + evidence links you approve."""
    _run(
        prompt_name="SuggestCitations",
        inputs={"target_id": target, "target_attribute": attribute},
        model=model,
        assume_yes=yes,
        dry_run=dry_run,
    )


@call_app.command("peer-review")
@handle_cli_errors
def call_peer_review(
    reviewer_role: str = typer.Option("domain expert", "--role", "-r", help="Persona the reviewer should adopt."),
    model: str = typer.Option(None, "--model", "-m"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    yes: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    """SyntheticPeerReview — model-level structured review (read-only)."""
    _run(
        prompt_name="SyntheticPeerReview",
        inputs={"reviewer_role": reviewer_role},
        model=model,
        assume_yes=yes,
        dry_run=dry_run,
    )


@call_app.command("research-gaps")
@handle_cli_errors
def call_research_gaps(
    model: str = typer.Option(None, "--model", "-m"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    yes: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    """IdentifyResearchGaps — find gaps that would strengthen the model (read-only)."""
    _run(
        prompt_name="IdentifyResearchGaps",
        inputs={},
        model=model,
        assume_yes=yes,
        dry_run=dry_run,
    )


@call_app.command("steelman")
@handle_cli_errors
def call_steelman(
    target: str = typer.Argument(..., help="Node or edge to steelman against."),
    model: str = typer.Option(None, "--model", "-m"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    yes: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    """SteelmanOpposingView — strongest counter-framing, added as contested view."""
    _run(
        prompt_name="SteelmanOpposingView",
        inputs={"target_id": target},
        model=model,
        assume_yes=yes,
        dry_run=dry_run,
    )


@call_app.command("project-view")
@handle_cli_errors
def call_project_view(
    view: str = typer.Argument(..., help="Target view: cld | dag."),
    model: str = typer.Option(None, "--model", "-m"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    yes: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    """ProjectToFormalView — view projection recommendations (read-only)."""
    _run(
        prompt_name="ProjectToFormalView",
        inputs={"view": view},
        model=model,
        assume_yes=yes,
        dry_run=dry_run,
    )


@call_app.command("run")
@handle_cli_errors
def call_run(
    prompt: str = typer.Argument(..., help="Prompt name from PROMPT_LIBRARY (e.g. SuggestVariables)."),
    inputs_json: str = typer.Option("{}", "--inputs", "-i", help="JSON object of prompt inputs."),
    model: str = typer.Option(None, "--model", "-m"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    yes: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    """Run any prompt by name. Generic dispatcher for power-user scripting."""
    if prompt not in prompt_lib.PROMPT_LIBRARY:
        known = ", ".join(sorted(prompt_lib.PROMPT_LIBRARY.keys())[:6]) + ", …"
        raise typer.BadParameter(
            f"unknown prompt: {prompt!r}. Try `latris ai prompts list`. Known: {known}"
        )
    try:
        inputs = json.loads(inputs_json) if inputs_json else {}
    except json.JSONDecodeError as e:
        raise typer.BadParameter(f"--inputs must be valid JSON: {e}")  # noqa: B904
    if not isinstance(inputs, dict):
        raise typer.BadParameter(f"--inputs must be a JSON object (got {type(inputs).__name__})")
    _run(prompt_name=prompt, inputs=inputs, model=model, assume_yes=yes, dry_run=dry_run)


# ---------- task (delegated calls — bring your own agent) ----------


def _task_prompt_name(task_path: str) -> str:
    """Read the prompt name from a task package file (parse-level peek so the
    render closure and the outcome summary know which prompt they serve; the
    authoritative validation happens in delegated.load_task)."""
    data = json.loads(Path(task_path).read_text(encoding="utf-8"))
    prompt_name = data.get("prompt_name") if isinstance(data, dict) else None
    if not isinstance(prompt_name, str) or not prompt_name:
        raise typer.BadParameter(f"task file {task_path} is missing a 'prompt_name' string")
    return prompt_name


@task_app.command("emit")
@handle_cli_errors
def task_emit(
    prompt: str = typer.Argument(..., help="Prompt name from PROMPT_LIBRARY (e.g. ExplainThisElement)."),
    inputs_json: str = typer.Option("{}", "--inputs", "-i", help="JSON object of prompt inputs."),
    output: str = typer.Option(None, "--output", "-o", help="Write the task package here (default: stdout)."),
) -> None:
    """Emit a self-contained task package for an external agent to answer.

    Writes nothing to the project — no adapter call, no log entry, no API key
    needed. Hand the JSON to your agent; ingest its answer with
    `latris ai task apply`.
    """
    if prompt not in prompt_lib.PROMPT_LIBRARY:
        known = ", ".join(sorted(prompt_lib.PROMPT_LIBRARY.keys())[:6]) + ", …"
        raise typer.BadParameter(
            f"unknown prompt: {prompt!r}. Try `latris ai prompts list`. Known: {known}"
        )
    try:
        inputs = json.loads(inputs_json) if inputs_json else {}
    except json.JSONDecodeError as e:
        raise typer.BadParameter(f"--inputs must be valid JSON: {e}")  # noqa: B904
    if not isinstance(inputs, dict):
        raise typer.BadParameter(f"--inputs must be a JSON object (got {type(inputs).__name__})")
    package = delegated_module.build_task_package(prompt, inputs)
    text = json.dumps(package, indent=2, ensure_ascii=False)
    if output:
        out_path = Path(output)
        out_path.write_text(text + "\n", encoding="utf-8")
        console.print(f"[green]task written[/green] → {out_path}")
    else:
        # typer.echo, not console.print: rich would word-wrap long JSON lines
        # (sometimes inside string literals) and interpret [...] sequences.
        typer.echo(text)


@task_app.command("apply")
@handle_cli_errors
def task_apply(
    task: str = typer.Option(..., "--task", "-t", help="Task package file from `latris ai task emit`."),
    response: str = typer.Option(..., "--from", help="The agent's response JSON file."),
    actor: str = typer.Option(
        None,
        "--actor",
        help="Agent name for attribution (model_id becomes external-agent:<name>).",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Approve mutating proposals without prompting."),
) -> None:
    """Apply an external agent's answer through the standard approval pipeline.

    The prompt name and inputs are read back from the task file. The answer is
    validated against the prompt's response schema, then flows through the same
    render → human-approve → apply → interaction-log pipeline as
    `latris ai call run`: read-only prompts need no confirmation; mutating
    prompts prompt [y/N] unless --yes.
    """
    prompt_name = _task_prompt_name(task)

    def render_parsed(parsed):
        return ai_render(prompt_name, parsed)

    outcome = delegated_module.finalize_delegated(
        task_path=task,
        response_path=response,
        actor=actor,
        approver=_resolve_approver(),
        confirm=_confirm_fn(yes),
        render=render_parsed,
    )
    _print_call_outcome(prompt_name=prompt_name, outcome=outcome)
