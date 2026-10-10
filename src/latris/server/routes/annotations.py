"""Annotation aggregation endpoint — returns all annotations for a target."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model
from latris.schema import (
    AssumptionLog,
    ChallengeLog,
    DecisionLog,
    EvidenceLinkSet,
    QuestionLog,
    SignoffLog,
)
from latris.server.deps import get_project_root

router = APIRouter(prefix="/api/annotations", tags=["annotations"])
Root = Annotated[Path, Depends(get_project_root)]


@router.get("/summary")
def annotation_summary(root: Root) -> dict[str, Any]:
    """Return per-target annotation counts for all targets in the project."""
    paths = ProjectPaths(root)

    # Collect all annotations by target_id
    counts: dict[str, dict[str, int]] = {}

    def bump(target_id: str, kind: str) -> None:
        if target_id not in counts:
            counts[target_id] = {}
        counts[target_id][kind] = counts[target_id].get(kind, 0) + 1

    # Global counts (project-level items where target_id is None)
    global_counts: dict[str, int] = {}

    def bump_global(kind: str) -> None:
        global_counts[kind] = global_counts.get(kind, 0) + 1

    # Evidence — per-target or project-level
    evidence = load_model(EvidenceLinkSet, paths.evidence_links_yaml)
    for e in evidence.entries:
        if e.target_id:
            bump(e.target_id, "evidence")
        else:
            bump_global("evidence")

    # Challenges — per-target or project-level
    challenges = load_model(ChallengeLog, paths.challenges_yaml)
    for c in challenges.entries:
        if c.target_id:
            bump(c.target_id, "challenge")
        else:
            bump_global("challenge")

    # Assumptions, decisions, questions — per-target or project-level
    assumptions = load_model(AssumptionLog, paths.assumptions_yaml)
    for a in assumptions.entries:
        if a.target_id:
            bump(a.target_id, "assumption")
        else:
            bump_global("assumption")

    decisions = load_model(DecisionLog, paths.decisions_yaml)
    for d in decisions.entries:
        if d.target_id:
            bump(d.target_id, "decision")
        else:
            bump_global("decision")

    questions = load_model(QuestionLog, paths.questions_yaml)
    for q in questions.entries:
        if q.target_id:
            bump(q.target_id, "question")
        else:
            bump_global("question")

    # Signoffs — per-target or project-level
    signoffs = load_model(SignoffLog, paths.signoffs_yaml)
    for s in signoffs.entries:
        if s.target_id:
            bump(s.target_id, "signoff")
        else:
            bump_global("signoff")

    return {
        "per_target": counts,
        "global": global_counts,
    }
