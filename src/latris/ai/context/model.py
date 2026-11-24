"""Prompts about the model as a whole: draft it, attack it, review it, find what's missing."""

from __future__ import annotations

from typing import Any

from latris.ai.context._shared import (
    SYSTEM_PREAMBLE,
    ContextPack,
    _cld_loop_guidance,
    _edge_lines,
    _format_block,
    _format_kv_block,
    _foundation_summary,
    _load_foundation,
    _load_substrate,
    _project_activity_summary,
    _relevant_assumptions_exclusions,
    compose_system,
)
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model, load_model_or_default
from latris.schema import ChallengeLog, EvidenceLinkSet, ExclusionLog, PolaritySet, ReferenceLibrary


def _build_draft(paths: ProjectPaths, inputs: dict[str, Any]) -> ContextPack:
    foundation = _load_foundation(paths)
    substrate = _load_substrate(paths)
    references = load_model(ReferenceLibrary, paths.references_yaml).entries
    asex = _relevant_assumptions_exclusions(paths)

    entity_summary = [f'"{e.label}" ({e.kind})' for e in substrate.entities]
    edge_summary = [
        f'"{next((n.label for n in substrate.entities if n.id == e.from_id), e.from_id)}" '
        f'→ "{next((n.label for n in substrate.entities if n.id == e.to_id), e.to_id)}" ({e.kind})'
        for e in substrate.edges
    ]

    from latris.ai import prompts as _prompts

    focus = inputs.get("focus", foundation.statement)
    candidate_count = inputs.get("candidate_count", 3)
    bibkeys = inputs.get("reference_bibkeys", [])

    user_message = (
        f"# Project foundation\n"
        f"{_foundation_summary(foundation)}"
        f"# Focus\n{focus}\n\n"
        f"# Existing substrate\n"
        + _format_block("Entities", entity_summary)
        + _format_block("Edges", edge_summary)
        + _format_kv_block("Reference library", [{"bibkey": r.bibkey, "title": r.title} for r in references])
        + _format_block("Assumptions", asex["assumptions"])
        + _format_block("Exclusions", asex["exclusions"])
        + f"\n# Request\nProduce {candidate_count} distinct framings for the focus above."
        + (f" Ground them in these references: {bibkeys}." if bibkeys else "")
    )

    return ContextPack(system=compose_system(_prompts.get("DraftConceptualModel")), user=user_message)


def _build_attack(paths: ProjectPaths, inputs: dict[str, Any]) -> ContextPack:
    foundation = _load_foundation(paths)
    substrate = _load_substrate(paths)
    asex = _relevant_assumptions_exclusions(paths)
    challenges = load_model(ChallengeLog, paths.challenges_yaml).entries

    scope_ids = inputs.get("scope_node_ids", [])
    entities = substrate.entities
    if scope_ids:
        entities = [e for e in entities if e.id in scope_ids]

    entity_lines = [f'"{e.label}" ({e.kind}, id={e.id})' for e in entities]
    edge_lines = _edge_lines(substrate)

    challenge_lines = [f"{c.state}: {c.argument[:60]}" for c in challenges]
    activity = _project_activity_summary(paths)

    user_message = (
        f"# Project foundation\n"
        f"{_foundation_summary(foundation)}"
        + (activity + "\n" if activity else "")
        + _format_block("Entities" + (" (scoped)" if scope_ids else ""), entity_lines)
        + _format_block("Edges", edge_lines)
        + _format_block("Assumptions", asex["assumptions"])
        + _format_block("Exclusions", asex["exclusions"])
        + _format_block("Existing challenges", challenge_lines)
        + "\n# Task\n"
        "Identify the weakest load-bearing assumption in this model. "
        "Explain which conclusion fails if it's wrong. "
        "Return an AttackResult."
    )

    return ContextPack(
        system=SYSTEM_PREAMBLE,
        user=user_message,
        target_ids=scope_ids,
    )


def _build_find_counter_pathway(paths: ProjectPaths, inputs: dict[str, Any]) -> ContextPack:
    """Context for FindCounterPathway — like _build_attack, plus references.

    The AI needs the reference library to ground its proposed counter-
    pathway in published mechanism rather than guessing. Mirrors the
    attack scaffolding so callers can flip between the two prompts
    cheaply.
    """
    foundation = _load_foundation(paths)
    substrate = _load_substrate(paths)
    references = load_model(ReferenceLibrary, paths.references_yaml).entries
    asex = _relevant_assumptions_exclusions(paths)
    challenges = load_model(ChallengeLog, paths.challenges_yaml).entries

    scope_ids = inputs.get("scope_node_ids", [])
    entities = substrate.entities
    if scope_ids:
        entities = [e for e in entities if e.id in scope_ids]

    entity_lines = [f'"{e.label}" ({e.kind}, id={e.id})' for e in entities]
    edge_lines = _edge_lines(substrate)

    challenge_lines = [f"{c.state}: {c.argument[:60]}" for c in challenges]

    user_message = (
        f"# Project foundation\n"
        f"{_foundation_summary(foundation)}"
        + _format_block("Entities" + (" (scoped)" if scope_ids else ""), entity_lines)
        + _format_block("Edges", edge_lines)
        + _format_block("Assumptions", asex["assumptions"])
        + _format_block("Exclusions", asex["exclusions"])
        + _format_block("Existing challenges", challenge_lines)
        + _format_kv_block(
            "Reference library",
            [{"bibkey": r.bibkey, "title": r.title} for r in references],
        )
        + "\n# Task\n"
        "Identify ONE missing causal pathway that, if added to this model, "
        "would weaken or invert its headline conclusion. Ground the "
        "pathway in a reference from the library when possible. "
        "Return a CounterPathwayResult."
    )

    return ContextPack(
        system=SYSTEM_PREAMBLE,
        user=user_message,
        target_ids=scope_ids,
    )


def _build_scope_check(paths: ProjectPaths, inputs: dict[str, Any]) -> ContextPack:
    foundation = _load_foundation(paths)
    substrate = _load_substrate(paths)
    exclusions = load_model(ExclusionLog, paths.exclusions_yaml).entries

    entity_lines = [f'"{e.label}" ({e.kind})' for e in substrate.entities]
    edge_lines = _edge_lines(substrate)

    boundary_section = ""
    if getattr(foundation, "boundary", None):
        boundary_section = f"\n# Model boundary\n{foundation.boundary}\n\n"

    activity = _project_activity_summary(paths)

    user_message = (
        f"# Project foundation\n"
        f"{_foundation_summary(foundation)}"
        + boundary_section
        + (activity + "\n" if activity else "")
        + _format_block("Current entities", entity_lines)
        + _format_block("Current edges", edge_lines)
        + _format_block("Exclusions", [e.statement for e in exclusions])
        + "\n# Task\n"
        "Does the current substrate adequately address the project foundation "
        "and stay within the model boundary (if defined)? "
        "Is the scope too narrow, too broad, or well-matched? "
        "Flag any elements that fall outside the stated boundary. Justify. "
        "Return a ScopeCheckResult."
    )

    return ContextPack(system=SYSTEM_PREAMBLE, user=user_message)


def _build_find_connections(paths: ProjectPaths, inputs: dict[str, Any]) -> ContextPack:
    foundation = _load_foundation(paths)
    substrate = _load_substrate(paths)
    focus_ids = inputs.get("focus_node_ids", [])

    entities = substrate.entities
    if focus_ids:
        entities = [e for e in entities if e.id in focus_ids]

    entity_lines = [f'"{e.label}" (kind={e.kind}, id={e.id})' for e in entities]
    edge_lines = _edge_lines(substrate)

    loop_guidance = _cld_loop_guidance(foundation, substrate, paths)

    from latris.ai import prompts as _prompts

    focus_note = (
        "\n# Focus\nRestrict proposals to the focus entities listed above; use "
        "their exact IDs for from_id / to_id.\n"
        if focus_ids
        else "\n# Focus\nConsider all entities above; use their exact IDs for from_id / to_id.\n"
    )
    user_message = (
        f"# Project foundation\n"
        f"{_foundation_summary(foundation)}"
        + _format_block("Entities" + (" (focus)" if focus_ids else ""), entity_lines)
        + _format_block("Existing edges", edge_lines)
        + loop_guidance
        + focus_note
    )

    return ContextPack(
        system=compose_system(_prompts.get("FindNewConnections")),
        user=user_message,
        target_ids=focus_ids,
    )


def _build_elicitation_interview(paths: ProjectPaths, inputs: dict[str, Any]) -> ContextPack:
    foundation = _load_foundation(paths)
    substrate = _load_substrate(paths)
    topic = inputs.get("topic", "")
    prior_turns = inputs.get("prior_turns", [])

    entity_lines = [f'"{e.label}" ({e.kind})' for e in substrate.entities]

    user_message = (
        f"# Project foundation\n"
        f"{_foundation_summary(foundation)}"
        f"# Elicitation topic\n{topic}\n\n"
        + _format_block("Current entities", entity_lines)
        + _format_block("Prior interview turns", prior_turns)
        + "\n# Task\n"
        "Ask ONE precise question that narrows the next entity, edge, or "
        "attribute. If the expert's answer would resolve something, include "
        "a proposed_edit dict. Return an ElicitationTurnResult."
    )

    return ContextPack(system=SYSTEM_PREAMBLE, user=user_message)


def _build_generate_pack(paths: ProjectPaths, inputs: dict[str, Any]) -> ContextPack:
    from latris.exporters.markdown import render as md_render

    pack_name = inputs.get("pack", "client")
    # Use the markdown exporter to assemble a pack-filtered view of the project
    md_content = md_render(paths, pack=pack_name)

    user_message = (
        f"# Generate a {pack_name} report pack\n\n"
        "Below is the structured project data filtered for this pack. "
        "Turn this into a polished, narrative report. Every claim must "
        "reference a provenance entry or citation. Do not invent facts.\n\n"
        f"{md_content}\n\n"
        "# Task\n"
        "Produce a ReportDraft with `pack` set to the pack name above and "
        "`sections` as a list of ReportSection objects. Each section has a "
        "concise heading (no leading '#') and self-contained markdown "
        "content. Split the report into multiple sections — one per "
        "topical area — rather than emitting the whole report as one "
        "string. This bounds the impact of any single JSON-escape issue."
    )

    return ContextPack(system=SYSTEM_PREAMBLE, user=user_message)


def _build_peer_review(paths: ProjectPaths, inputs: dict[str, Any]) -> ContextPack:
    foundation = _load_foundation(paths)
    substrate = _load_substrate(paths)
    asex = _relevant_assumptions_exclusions(paths)
    challenges = load_model(ChallengeLog, paths.challenges_yaml).entries
    evidence = load_model(EvidenceLinkSet, paths.evidence_links_yaml).entries

    reviewer_role = inputs.get("reviewer_role", "domain expert")

    entity_lines = [f'"{e.label}" ({e.kind})' for e in substrate.entities]
    edge_lines = _edge_lines(substrate)

    challenge_lines = [f"{c.state}: {c.argument[:60]}" for c in challenges]
    evidence_lines = [f"{ev.target_id}/{ev.attribute} ← {ev.bibkey}" for ev in evidence]
    activity = _project_activity_summary(paths)

    user_message = (
        f"# Project foundation\n"
        f"{_foundation_summary(foundation)}"
        + (activity + "\n" if activity else "")
        + _format_block("Entities", entity_lines)
        + _format_block("Edges", edge_lines)
        + _format_block("Assumptions", asex["assumptions"])
        + _format_block("Exclusions", asex["exclusions"])
        + _format_block("Existing challenges", challenge_lines)
        + _format_block("Evidence links", evidence_lines)
        + f"\n# Task\n"
        f"You are a {reviewer_role} reviewing this model. Structure your "
        "review as: scope assessment, rigor assessment, evidence assessment, "
        "major risks, and questions you would ask the modeller. "
        "Return a PeerReviewResult."
    )

    return ContextPack(system=SYSTEM_PREAMBLE, user=user_message)


def _build_research_gaps(paths: ProjectPaths, inputs: dict[str, Any]) -> ContextPack:
    foundation = _load_foundation(paths)
    substrate = _load_substrate(paths)
    references = load_model(ReferenceLibrary, paths.references_yaml).entries
    evidence = load_model(EvidenceLinkSet, paths.evidence_links_yaml).entries
    challenges = load_model(ChallengeLog, paths.challenges_yaml).entries

    entity_lines = [f'"{e.label}" (kind={e.kind}, id={e.id})' for e in substrate.entities]
    edge_lines = []
    for e in substrate.edges:
        src = next((n.label for n in substrate.entities if n.id == e.from_id), e.from_id)
        dst = next((n.label for n in substrate.entities if n.id == e.to_id), e.to_id)
        edge_lines.append(f'"{src}" → "{dst}" ({e.kind}, id={e.id})')

    evidence_lines = [f"{ev.target_id}/{ev.attribute} ← {ev.bibkey}" for ev in evidence]
    ref_lines = [f"{r.bibkey}: {r.title}" for r in references]
    open_challenges = [f"{c.target_id}: {c.argument[:60]}" for c in challenges if c.state == "open"]
    activity = _project_activity_summary(paths)

    user_message = (
        f"# Project foundation\n"
        f"{_foundation_summary(foundation)}"
        + (activity + "\n" if activity else "")
        + _format_block("Entities", entity_lines)
        + _format_block("Edges", edge_lines)
        + _format_block("Reference library", ref_lines)
        + _format_block("Evidence coverage", evidence_lines)
        + _format_block("Open challenges", open_challenges)
        + "\n# Task\n"
        "Survey the model's attributes and evidence. Identify gaps whose "
        "closure would most increase defensibility. For each gap, specify "
        "priority (high/medium/low), affected node IDs, and a suggested "
        "action. Return a ResearchGapsResult."
    )

    return ContextPack(system=SYSTEM_PREAMBLE, user=user_message)


def _build_project_view(paths: ProjectPaths, inputs: dict[str, Any]) -> ContextPack:
    foundation = _load_foundation(paths)
    substrate = _load_substrate(paths)
    view = inputs.get("view", "cld")

    entity_lines = [f'"{e.label}" (kind={e.kind}, id={e.id})' for e in substrate.entities]
    edge_lines = []
    for e in substrate.edges:
        src = next((n.label for n in substrate.entities if n.id == e.from_id), e.from_id)
        dst = next((n.label for n in substrate.entities if n.id == e.to_id), e.to_id)
        edge_lines.append(f'"{src}" → "{dst}" (kind={e.kind}, id={e.id})')

    # Load polarity for CLD relevance
    polarity_path = paths.view_attribute_path("cld", "polarity")
    polarity = load_model_or_default(PolaritySet, polarity_path)
    polarity_lines = [f"{p.target_id}: {p.value}" for p in polarity.entries]

    view_constraints = {
        "cld": "CLD requires polarity (+/-) on every edge. Flag edges missing polarity.",
        "dag": "DAG must be acyclic. Flag any cycles in the proposed projection.",
    }

    user_message = (
        f"# Project foundation\n"
        f"{_foundation_summary(foundation)}"
        f"# Target view: {view}\n"
        f"Constraint: {view_constraints.get(view, 'Unknown view type.')}\n\n"
        + _format_block("Entities", entity_lines)
        + _format_block("Edges", edge_lines)
        + _format_block("Polarity assignments", polarity_lines)
        + "\n# Task\n"
        f"Recommend how to project the substrate to the {view} view. "
        "For each entity/edge, say whether it maps, needs modification, or "
        "should be excluded. Flag any constraint violations. "
        "Return a FormalViewProjectionResult."
    )

    return ContextPack(system=SYSTEM_PREAMBLE, user=user_message)
