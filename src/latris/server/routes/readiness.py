"""Readiness scores — computable from substrate + attributes + provenance."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from latris.operations.readiness import (
    BuildPhaseReadiness,
    InterpretReadiness,
    TransitionReadiness,
    assess_all_readiness,
    assess_build_readiness,
    assess_interpret_readiness,
    assess_transition_readiness,
)
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model, load_model_or_default
from latris.schema import (
    ChallengeLog,
    DescriptionSet,
    EvidenceLinkSet,
    PolaritySet,
    QuestionLog,
    Substrate,
)
from latris.server.deps import Root

router = APIRouter(prefix="/api/readiness", tags=["readiness"])


@router.get("")
def readiness(root: Root) -> dict[str, Any]:
    paths = ProjectPaths(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    descriptions = load_model(DescriptionSet, paths.descriptions_yaml)
    polarity_path = paths.view_attribute_path("cld", "polarity")
    polarity = load_model_or_default(PolaritySet, polarity_path)
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


@router.get("/build", response_model=BuildPhaseReadiness)
def build_readiness(root: Root) -> BuildPhaseReadiness:
    """Build-phase readiness: per-selected-model-type scores."""
    return assess_build_readiness(root=root)


@router.get("/interpret", response_model=InterpretReadiness)
def interpret_readiness(root: Root) -> InterpretReadiness:
    """Model→Interpret readiness: requires analysis runs + findings."""
    return assess_interpret_readiness(root=root)


@router.get("/transitions", response_model=TransitionReadiness)
def transition_readiness(root: Root) -> TransitionReadiness:
    """The traffic light on each step between phases (the last is the handover check)."""
    return assess_transition_readiness(root=root)
