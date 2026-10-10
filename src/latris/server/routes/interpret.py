"""Interpret phase routes — claims extraction, prose generation, CRUD."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from latris.server.deps import get_project_root

router = APIRouter(prefix="/api/interpret", tags=["interpret"])
Root = Annotated[Path, Depends(get_project_root)]


class ProseUpdateBody(BaseModel):
    prose: str


def _decorate_with_hedge_signals(sections: list, root: Path) -> list[dict[str, Any]]:
    """Attach hedge_active + coverage_ratio per section response.

    Computed at fetch time rather than persisted because hedge
    state is a function of current evidence coverage and accepted
    findings — it changes whenever the user adds an evidence link
    or accepts a finding.
    """
    from latris.operations.interpret import coverage_ratio, hedge_mode_active
    from latris.repo.layout import ProjectPaths

    paths = ProjectPaths(root)
    cache: dict[str, tuple[bool, float]] = {}
    decorated: list[dict[str, Any]] = []
    for section in sections:
        dumped = section.model_dump(mode="json")
        mt = section.model_type
        if mt and mt not in cache:
            _cited, _total, ratio = coverage_ratio(mt, paths)
            cache[mt] = (hedge_mode_active(mt, paths), ratio)
        active, ratio = cache.get(mt, (False, 1.0))
        dumped["hedge_active"] = active
        dumped["coverage_ratio"] = ratio
        decorated.append(dumped)
    return decorated


@router.get("")
def get_interpretation(root: Root) -> dict[str, Any]:
    """Load the full interpretation store."""
    from latris.operations.interpret import load_interpretation

    store = load_interpretation(root=root)
    return {"sections": _decorate_with_hedge_signals(store.sections, root)}


@router.post("/initialise")
def initialise(root: Root) -> dict[str, Any]:
    """Create interpretation sections for all applicable model types."""
    from latris.operations.interpret import initialise_sections

    store, sha, skipped = initialise_sections(root=root)
    return {
        "sections": _decorate_with_hedge_signals(store.sections, root),
        "commit_sha": sha,
        "skipped": [{"model_type": mid, "reason": reason} for mid, reason in skipped],
    }


@router.post("/refresh-claims/{section_id}")
def refresh_claims(section_id: str, root: Root) -> dict[str, Any]:
    """Re-extract claims for a single section."""
    from latris.operations.interpret import refresh_claims as _refresh

    section, sha = _refresh(section_id, root=root)
    decorated = _decorate_with_hedge_signals([section], root)[0]
    return {"section": decorated, "commit_sha": sha}


@router.post("/refresh-all-claims")
def refresh_all_claims(root: Root) -> dict[str, Any]:
    """Re-extract claims for all sections."""
    from latris.operations.interpret import refresh_all_claims as _refresh_all

    store, sha = _refresh_all(root=root)
    return {
        "sections": _decorate_with_hedge_signals(store.sections, root),
        "commit_sha": sha,
    }


@router.post("/generate-prose/{section_id}")
def generate_prose(section_id: str, root: Root) -> dict[str, Any]:
    """Run AI prompt to generate interpretation prose for a section."""
    from fastapi import HTTPException

    from latris.ai import config as ai_config
    from latris.ai.call import run_call
    from latris.ai.render import render as ai_render
    from latris.operations.completeness import load_report
    from latris.operations.interpret import (
        _find_section,
        load_interpretation,
        update_prose,
    )
    from latris.operations.interpret_registry import get_section_spec
    from latris.repo import git
    from latris.repo.layout import ProjectPaths
    from latris.schema.common import HumanActor

    store = load_interpretation(root=root)
    section = _find_section(store, section_id)
    spec = get_section_spec(section.section_type)

    # AI interrogation Phase 2c — blocking-mode gate check. When the
    # project's ai_config sets completeness_gate_blocking=True AND the
    # current report has any `severity=required` entry with status
    # `open`, refuse to generate prose. Default config keeps this off
    # (warn-only) until the gate is calibrated.
    paths = ProjectPaths(root)
    cfg = ai_config.load(paths)
    if cfg.completeness_gate_blocking and section.model_type:
        report = load_report(section.model_type, root=root)
        blocking = [
            mv.id
            for mv in report.entries
            if mv.severity == "required" and mv.disposition == "open"
        ]
        if blocking:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "completeness_gate_blocked",
                    "model_type": section.model_type,
                    "blocking_missing_variable_ids": blocking,
                },
            )

    # Get approver from git identity
    name, email = git.ensure_identity(root)
    approver = HumanActor(name=name, email=email)

    def _render(parsed):
        return ai_render(spec.prompt_name, parsed)

    # Call AI with claims as context. Pass root explicitly so the call does
    # not depend on process cwd (FastAPI serves from a threadpool).
    outcome = run_call(
        prompt_name=spec.prompt_name,
        inputs={
            "section_type": section.section_type,
            "model_type": section.model_type,
            "claims": section.claims,
            "_prompt_name": spec.prompt_name,
        },
        approver=approver,
        confirm=lambda _r, _p: True,
        render=_render,
        preview_only=False,
        root=root,
    )

    # outcome.rendered contains the prose (via the render function)
    prose = outcome.rendered or ""

    # Save prose with AI source
    section, sha = update_prose(section_id, prose, source="ai", root=root)
    decorated = _decorate_with_hedge_signals([section], root)[0]
    return {"section": decorated, "commit_sha": sha}


@router.patch("/{section_id}/prose")
def patch_prose(section_id: str, body: ProseUpdateBody, root: Root) -> dict[str, Any]:
    """Save a human edit to section prose."""
    from latris.operations.interpret import update_prose

    section, sha = update_prose(section_id, body.prose, source="human-edit", root=root)
    decorated = _decorate_with_hedge_signals([section], root)[0]
    return {"section": decorated, "commit_sha": sha}


@router.get("/sections-for-model/{model_type}")
def sections_for_model(model_type: str) -> dict[str, Any]:
    """Return applicable section specs for a model type."""
    from dataclasses import asdict

    from latris.operations.interpret_registry import get_sections_for_model_types

    specs = get_sections_for_model_types([model_type])
    return {"specs": [asdict(s) for s in specs]}
