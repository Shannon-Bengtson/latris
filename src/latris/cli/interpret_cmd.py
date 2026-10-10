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

app = typer.Typer(
    help="Interpret phase: sections, claims, AI prose.",
    no_args_is_help=True,
)
console = Console()


@app.command("initialise")
@handle_cli_errors
def initialise() -> None:
    """Create interpretation sections for all selected model types."""
    from latris.operations.interpret import initialise_sections

    store, sha, skipped = initialise_sections()
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
    if not store.sections:
        console.print("[dim](no sections — run `interpret initialise` first)[/dim]")
        return
    for s in store.sections:
        prose_len = len(s.prose or "")
        claim_count = len(s.claims or [])
        console.print(
            f"[cyan]{s.id[:20]}[/cyan]  {s.section_type} ({s.model_type})  "
            f"state=[bold]{s.generation_state}[/bold]  claims={claim_count}  prose={prose_len}c"
        )


@app.command("refresh-claims")
@handle_cli_errors
def refresh_claims(
    section: str = typer.Option(
        None, "--section", "-s",
        help="Section ID to refresh. Omit to refresh all sections.",
    ),
) -> None:
    """Re-extract claims from project state into one or all sections."""
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
    else:
        sec, sha = _refresh_one(section)
        console.print(
            f"[green]refreshed[/green] {sec.section_type} "
            f"(claims={len(sec.claims)}) · commit [cyan]{sha[:10]}[/cyan]"
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
