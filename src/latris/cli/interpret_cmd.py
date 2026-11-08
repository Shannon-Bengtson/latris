"""Interpret phase CLI — initialise sections, refresh claims, generate AI prose.

Mirrors the GUI server routes (`server/routes/interpret.py`) so the same
workflow is available from a script. The bare `ai call run InterpretXxx`
prompts only return prose to stdout; the prose lands in
``ai/interactions.jsonl`` but never reaches ``interpretation.yaml`` and
never appears in the report. ``interpret generate-prose`` closes that loop.
"""

from __future__ import annotations

import typer
from rich.console import Console

from latris.cli._errors import handle_cli_errors
from latris.cli._output import emit, json_mode

app = typer.Typer(
    help="Interpret phase: sections, claims, AI prose.",
    no_args_is_help=True,
)
console = Console()


def _sections_json(store) -> list[dict]:
    from latris.operations.interpret_registry import INTERPRET_SECTION_REGISTRY

    return [
        {"section": s.section_type, "model_type": s.model_type,
         "title": INTERPRET_SECTION_REGISTRY[s.section_type].display_name
         if s.section_type in INTERPRET_SECTION_REGISTRY else s.section_type,
         "claims": list(s.claims or []), "prose": s.prose or "", "state": s.generation_state,
         "stale": s.is_stale()}
        for s in store.sections
    ]


@app.command("initialise")
@handle_cli_errors
def initialise() -> None:
    """Create interpretation sections (with their claims) for all selected model types."""
    from latris.operations.interpret import initialise_sections

    store, sha, skipped = initialise_sections()
    if json_mode():
        emit({"sections": _sections_json(store), "skipped": [{"model_type": m, "reason": r} for m, r in skipped]},
             human=lambda: None, commit_sha=sha)
        return
    n = len(store.sections)
    console.print(
        f"[green]initialised[/green] {n} section(s) · commit [cyan]{sha[:10]}[/cyan]"
    )
    for s in store.sections:
        console.print(f"  · [cyan]{s.id[:20]}[/cyan]  {s.section_type} ({s.model_type})  state={s.generation_state}")
    for mid, reason in skipped:
        console.print(
            f"[yellow]skipped[/yellow] {mid.upper()}: {reason}",
            markup=False, highlight=False,
        )


@app.command("list")
@handle_cli_errors
def list_sections() -> None:
    """List interpretation sections with their status and lengths."""
    from latris.operations.interpret import load_interpretation

    store = load_interpretation()
    if json_mode():
        emit(_sections_json(store), human=lambda: None)
        return
    if not store.sections:
        console.print("[dim](no sections — run `interpret initialise` first)[/dim]")
        return
    for s in store.sections:
        prose_len = len(s.prose or "")
        claim_count = len(s.claims or [])
        console.print(
            f"[cyan]{s.id[:20]}[/cyan]  {s.section_type} ({s.model_type})  "
            f"state=[bold]{s.generation_state}[/bold]{' [yellow](out of date)[/yellow]' if s.is_stale() else ''}  "
            f"claims={claim_count}  prose={prose_len}c"
        )


@app.command("show")
@handle_cli_errors
def show(
    section: str = typer.Argument(..., help="Section ID, or section type (e.g. answer_to_question)."),
    model_type: str = typer.Option(None, "--model-type", "-m", help="Pick between model types' sections."),
) -> None:
    """Show a section's claims (what the model supports) and its current prose.

    The claims are what the prose should say — write from them with
    `latris interpret set-prose`.
    """
    from latris.operations.interpret import resolve_section

    s = resolve_section(section, model_type=model_type)

    def _human() -> None:
        console.print(f"[bold]{s.section_type}[/bold] ({s.model_type}) · {s.id} · state={s.generation_state}")
        if s.is_stale():
            console.print(
                "[yellow]The prose is out of date: the claims below changed after it was written. "
                "Rewrite it with `latris interpret set-prose`.[/yellow]"
            )
        console.print("\n[bold]Claims[/bold]")
        for i, claim in enumerate(s.claims, 1):
            console.print(f"  {i}. {claim}", markup=False, highlight=False)
        if not s.claims:
            console.print("  (none — run `latris interpret refresh-claims` after changing the model)")
        console.print("\n[bold]Prose[/bold]")
        console.print(s.prose or "(empty)", markup=False, highlight=False)

    emit(
        {"id": s.id, "section_type": s.section_type, "model_type": s.model_type, "claims": s.claims,
         "prose": s.prose, "generation_state": s.generation_state, "stale": s.is_stale()},
        human=_human,
    )


@app.command("set-prose")
@handle_cli_errors
def set_prose(
    section: str = typer.Argument(..., help="Section ID, or section type (e.g. answer_to_question)."),
    text: str = typer.Argument(..., help="The prose for this section."),
    model_type: str = typer.Option(None, "--model-type", "-m", help="Pick between model types' sections."),
    by: str = typer.Option(
        "human", "--by", help="human | ai — who wrote it. Agents writing prose themselves pass --by ai."
    ),
) -> None:
    """Write a section's prose yourself (no AI key needed).

    Stick to the section's claims (`latris interpret show`). `--by ai`
    records it as AI-written. Either way the report marks it out of date
    when the claims change.
    """
    from latris.operations.interpret import resolve_section, update_prose

    if by not in {"human", "ai"}:
        raise ValueError("--by must be 'human' or 'ai'")
    target = resolve_section(section, model_type=model_type)
    updated, sha = update_prose(
        target.id, text, source="ai" if by == "ai" else "human-edit", written_by_agent=by == "ai"
    )
    emit(
        {"id": updated.id, "section_type": updated.section_type, "generation_state": updated.generation_state},
        commit_sha=sha,
        human=lambda: console.print(
            f"[green]wrote[/green] {updated.section_type} ({updated.model_type}) · commit [cyan]{sha[:10]}[/cyan]"
        ),
    )


@app.command("refresh-claims")
@handle_cli_errors
def refresh_claims(
    section: str = typer.Option(
        None, "--section", "-s",
        help="Section ID to refresh. Omit to refresh all sections.",
    ),
) -> None:
    """Re-extract claims from project state into one or all sections.

    Prose written against the old claims is then marked out of date, in
    `interpret list`/`show`, `check handover` and the report.
    """
    from latris.operations.interpret import (
        refresh_all_claims as _refresh_all,
    )
    from latris.operations.interpret import (
        refresh_claims as _refresh_one,
    )

    if section is None:
        store, sha = _refresh_all()
        n = len(store.sections)
        console.print(f"[green]refreshed[/green] {n} section(s) · commit [cyan]{sha[:10]}[/cyan]")
        stale = [x.section_type for x in store.sections if x.is_stale()]
        if stale:
            console.print(f"[yellow]out of date (rewrite the prose):[/yellow] {', '.join(stale)}")
    else:
        sec, sha = _refresh_one(section)
        console.print(
            f"[green]refreshed[/green] {sec.section_type} "
            f"(claims={len(sec.claims)}) · commit [cyan]{sha[:10]}[/cyan]"
            + (" · [yellow]prose out of date[/yellow]" if sec.is_stale() else "")
        )


def _generate_one(section_id: str, *, model: str | None) -> tuple[str, str | None, float | None]:
    """Generate AI prose for one section and persist it. Returns
    (section_type, interaction_id, cost_usd)."""
    from latris.ai.call import run_call
    from latris.ai.render import render as ai_render
    from latris.operations.interpret import (
        _find_section,
        load_interpretation,
        update_prose,
    )
    from latris.operations.interpret_registry import get_section_spec
    from latris.repo import git
    from latris.repo.project import require_project
    from latris.schema.common import HumanActor

    paths = require_project()
    store = load_interpretation(root=paths.root)
    section = _find_section(store, section_id)
    spec = get_section_spec(section.section_type)

    name, email = git.ensure_identity(paths.root)
    approver = HumanActor(name=name, email=email)

    def _render(parsed):
        return ai_render(spec.prompt_name, parsed)

    outcome = run_call(
        prompt_name=spec.prompt_name,
        inputs={
            "section_type": section.section_type,
            "model_type": section.model_type,
            "claims": section.claims,
            "_prompt_name": spec.prompt_name,
        },
        model_override=model,
        approver=approver,
        confirm=lambda _r, _p: True,
        render=_render,
        preview_only=False,
        root=paths.root,
    )

    prose = outcome.rendered or ""
    if prose:
        update_prose(section_id, prose, source="ai", root=paths.root)
    return section.section_type, outcome.interaction_id, outcome.cost_usd


@app.command("generate-prose")
@handle_cli_errors
def generate_prose(
    section: str = typer.Argument(..., help="Section ID."),
    model: str = typer.Option(None, "--model", "-m"),
    yes: bool = typer.Option(
        False, "--yes", "-y", hidden=True, help="Accepted for symmetry; interpret prompts auto-approve."
    ),
) -> None:
    """Run the AI prompt for a section and persist its prose into interpretation.yaml."""
    _ = yes  # Interpret prompts are read-only; prose persistence is automatic.
    section_type, interaction_id, cost = _generate_one(section, model=model)
    cost_str = f"${cost:.4f}" if cost is not None else "—"
    short_id = (interaction_id or "")[:20]
    console.print(
        f"[green]generated[/green] {section_type} · interaction "
        f"[cyan]{short_id}…[/cyan] · cost {cost_str}"
    )


@app.command("generate-all")
@handle_cli_errors
def generate_all(
    model: str = typer.Option(None, "--model", "-m"),
    yes: bool = typer.Option(
        False, "--yes", "-y", hidden=True, help="Accepted for symmetry; interpret prompts auto-approve."
    ),
) -> None:
    """One-shot: generate AI prose for every section. Continues past per-section errors."""
    _ = yes
    from latris.operations.interpret import load_interpretation

    store = load_interpretation()
    if not store.sections:
        # No sections is no longer always an error — the Interpret
        # initialiser legitimately produces 0 sections when every
        # selected model type fails structural readiness (e.g. CLD
        # selected with no loops, DAG selected with cycles). Print a
        # friendly note and exit success; if the user genuinely
        # forgot initialise they can run it themselves.
        console.print(
            "[dim]no sections to generate — run `interpret initialise` "
            "first, or check that at least one selected model type "
            "passes structural readiness.[/dim]"
        )
        return

    total_cost = 0.0
    failed: list[tuple[str, str]] = []
    for s in store.sections:
        try:
            section_type, _interaction_id, cost = _generate_one(s.id, model=model)
            if cost is not None:
                total_cost += cost
            console.print(f"  · {section_type}: ok ({f'${cost:.4f}' if cost else '—'})")
        except Exception as exc:  # noqa: BLE001 — per-section tolerance on purpose
            failed.append((s.section_type, str(exc)))
            console.print(f"  · [red]{s.section_type}: {exc}[/red]")

    console.print(
        f"\n[green]done[/green] · {len(store.sections) - len(failed)}/{len(store.sections)} "
        f"sections · total cost ${total_cost:.4f}"
    )
    if failed:
        raise typer.Exit(code=1)
