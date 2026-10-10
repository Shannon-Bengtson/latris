"""Readiness scores — computable from substrate + attributes + provenance."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from latris.operations.readiness import (
    assess_all_readiness,
    assess_build_readiness,
    assess_interpret_readiness,
    assess_transition_readiness,
)
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model
from latris.schema import (
    ChallengeLog,
    DescriptionSet,
    EvidenceLinkSet,
    PolaritySet,
    QuestionLog,
    Substrate,
)
from latris.server.deps import get_project_root

router = APIRouter(prefix="/api/readiness", tags=["readiness"])
Root = Annotated[Path, Depends(get_project_root)]


@router.get("")
def readiness(root: Root) -> dict[str, Any]:
    paths = ProjectPaths(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    descriptions = load_model(DescriptionSet, paths.descriptions_yaml)
    polarity_path = paths.view_attribute_path("cld", "polarity")
    polarity = load_model(PolaritySet, polarity_path) if polarity_path.exists() else PolaritySet()
    evidence = load_model(EvidenceLinkSet, paths.evidence_links_yaml)
    challenges = load_model(ChallengeLog, paths.challenges_yaml)
    questions = load_model(QuestionLog, paths.questions_yaml)

    entity_ids = {e.id for e in substrate.entities}
    edge_ids = {e.id for e in substrate.edges}
    all_ids = entity_ids | edge_ids
    total = len(all_ids) if all_ids else 1  # avoid division by zero

    desc_ids = {e.target_id for e in descriptions.entries}
    pol_edge_ids = {e.target_id for e in polarity.entries if e.target_id in edge_ids}
    evidence_ids = {e.target_id for e in evidence.entries}
    open_challenges = [c for c in challenges.entries if c.state == "open"]
    open_questions = [q for q in questions.entries if q.disposition == "open"]

    nodes_without_desc = [e for e in substrate.entities if e.id not in desc_ids]
    edges_without_polarity = [e for e in substrate.edges if e.id not in pol_edge_ids]
    elements_without_evidence = [eid for eid in all_ids if eid not in evidence_ids]

    # Workshop ready: all nodes described, no open questions
    workshop_score = int(100 * len(desc_ids & entity_ids) / max(len(entity_ids), 1))

    # Report ready: all elements have evidence
    report_score = int(100 * len(evidence_ids & all_ids) / total)

    # CLD ready: all edges have polarity
    cld_total = len(edge_ids) if edge_ids else 1
    cld_score = int(100 * len(pol_edge_ids) / cld_total)

    # Per-model-type readiness (registry-driven)
    from dataclasses import asdict

    model_type_readiness = [asdict(r) for r in assess_all_readiness(root=root)]

    return {
        "scores": {
            "workshop": workshop_score,
            "report": report_score,
            "cld": cld_score,
        },
        "model_types": model_type_readiness,
        "gaps": {
            "nodes_without_description": [{"id": e.id, "label": e.label} for e in nodes_without_desc],
            "edges_without_polarity": [
                {"id": e.id, "from_id": e.from_id, "to_id": e.to_id} for e in edges_without_polarity
            ],
            "open_challenges": len(open_challenges),
            "open_questions": len(open_questions),
            "elements_without_evidence": len(elements_without_evidence),
        },
    }


@router.get("/build")
def build_readiness(root: Root) -> dict[str, Any]:
    """Build-phase readiness: per-selected-model-type scores."""
    from dataclasses import asdict

    result = assess_build_readiness(root=root)
    return {
        "selected_model_types": result.selected_model_types,
        "model_scores": {k: asdict(v) for k, v in result.model_scores.items()},
        "composite_score": result.composite_score,
        "summary": result.summary,
    }


@router.get("/interpret")
def interpret_readiness(root: Root) -> dict[str, Any]:
    """Model→Interpret readiness: requires analysis runs + findings."""
    from dataclasses import asdict

    result = assess_interpret_readiness(root=root)
    return asdict(result)


@router.get("/transitions")
def transition_readiness(root: Root) -> dict[str, Any]:
    """All four phase-transition traffic-light states."""
    from dataclasses import asdict

    result = assess_transition_readiness(root=root)
    return {"transitions": [asdict(t) for t in result.transitions]}
