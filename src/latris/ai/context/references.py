"""Reference management prompts: expand, cross-check and summarise the library, and find its gaps."""

from __future__ import annotations

from typing import Any

from latris.ai.context._shared import (
    SYSTEM_PREAMBLE,
    ContextPack,
    _format_block,
    _format_tier0_block,
    _foundation_summary,
    _load_foundation,
    _load_substrate,
    _project_activity_summary,
    _relevant_assumptions_exclusions,
)
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model
from latris.schema import ChallengeLog, EvidenceLinkSet, QuestionLog, ReferenceLibrary
from latris.schema.interpretation import INTERPRET_SECTION_IDS


def _build_expand_bibliography(paths: ProjectPaths, inputs: dict[str, Any]) -> ContextPack:
    foundation = _load_foundation(paths)
    substrate = _load_substrate(paths)
    refs = load_model(ReferenceLibrary, paths.references_yaml)
    evidence = load_model(EvidenceLinkSet, paths.evidence_links_yaml)
    focus = inputs.get("focus_area", "")

    by_id = {e.id: e for e in substrate.entities}
    entity_lines = [f"  - {e.label} ({e.kind})" for e in substrate.entities]
    edge_lines = []
    for edge in substrate.edges:
        src = by_id.get(edge.from_id)
        dst = by_id.get(edge.to_id)
        edge_lines.append(
            f"  - {src.label if src else edge.from_id} → {dst.label if dst else edge.to_id} ({edge.kind})"
        )
    ref_lines = [f"  - {r.bibkey}: {r.title} ({r.year})" for r in refs.entries]
    ev_lines = [f"  - {e.bibkey} → {e.target_id}/{e.attribute}" for e in evidence.entries]

    # Load provenance concerns that drive research needs
    challenges = load_model(ChallengeLog, paths.challenges_yaml)
    open_challenges = [c for c in challenges.entries if c.state == "open"]
    challenge_lines = [f"  - [{c.target_id[:12]}] {c.argument[:100]}" for c in open_challenges]

    questions = load_model(QuestionLog, paths.questions_yaml)
    open_questions = [q for q in questions.entries if q.disposition == "open"]
    question_lines = [f"  - {q.question}" for q in open_questions]

    asex = _relevant_assumptions_exclusions(paths)
    assumption_lines = [f"  - {a}" for a in asex["assumptions"]]
    exclusion_lines = [f"  - {e}" for e in asex["exclusions"]]

    user_message = (
        f"# Project foundation\n{_foundation_summary(foundation, header='Research question/decision')}"
        f"# Model structure\n"
        f"## Entities ({len(substrate.entities)})\n" + "\n".join(entity_lines) + "\n\n"
        f"## Edges ({len(substrate.edges)})\n" + "\n".join(edge_lines) + "\n\n"
        f"# Current references ({len(refs.entries)})\n" + "\n".join(ref_lines) + "\n\n"
        f"# Current evidence links ({len(evidence.entries)})\n"
        + "\n".join(ev_lines)
        + "\n\n"
        + _format_block("Open challenges (disputes needing evidence)", challenge_lines)
        + _format_block("Open questions (unknowns needing literature)", question_lines)
        + _format_block("Assumptions (claims needing validation)", assumption_lines)
        + _format_block("Exclusions (boundary decisions needing support)", exclusion_lines)
        + f"\n# Focus area\n{focus or '(none — whole model)'}\n\n"
        "# Task\n"
        "Propose 3–6 targeted search queries that would find the most "
        "relevant academic papers to strengthen this model's evidence base. "
        "Prioritise queries that would find papers to:\n"
        "- Resolve open challenges (evidence for/against disputed connections)\n"
        "- Answer open questions about mechanisms\n"
        "- Validate or challenge key assumptions\n"
        "- Support scope exclusion decisions\n\n"
        "Each query should be a concise keyword string suitable for "
        "academic database search (e.g. 'riparian buffer nutrient removal "
        "effectiveness New Zealand', 'E. coli concentration estuary "
        "rainfall correlation'). Include a brief rationale for each.\n"
        "Return a BibliographySearchPlan."
    )

    return ContextPack(system=SYSTEM_PREAMBLE, user=user_message)


def _build_cross_reference_check(paths: ProjectPaths, inputs: dict[str, Any]) -> ContextPack:
    foundation = _load_foundation(paths)
    substrate = _load_substrate(paths)
    refs = load_model(ReferenceLibrary, paths.references_yaml)
    evidence = load_model(EvidenceLinkSet, paths.evidence_links_yaml)

    by_id = {e.id: e for e in substrate.entities}

    # Pre-compute which elements have evidence so the LLM can focus on gaps
    cited_targets = {e.target_id for e in evidence.entries}
    entity_lines = [
        f"  - {e.id}: {e.label} ({e.kind})" + (" [HAS EVIDENCE]" if e.id in cited_targets else "")
        for e in substrate.entities
    ]
    edge_lines = []
    for edge in substrate.edges:
        src = by_id.get(edge.from_id)
        dst = by_id.get(edge.to_id)
        tag = " [HAS EVIDENCE]" if edge.id in cited_targets else ""
        edge_lines.append(
            f"  - {edge.id}: {src.label if src else edge.from_id} -> "
            f"{dst.label if dst else edge.to_id} ({edge.kind}){tag}"
        )
    ref_lines = [f"  - {r.bibkey}: {r.title}" for r in refs.entries]
    ev_lines = [f"  - {e.bibkey} -> {e.target_id}/{e.attribute}" for e in evidence.entries]

    # Token budget: only feed Tier-0 content for the top 20 most
    # relevant references. Cited bibkeys come first; uncited ones
    # fill the remainder so unused references can still be sanity-
    # checked against snapshot text.
    cited_bibkeys = {e.bibkey for e in evidence.entries}
    cited_refs = [r for r in refs.entries if r.bibkey in cited_bibkeys]
    uncited_refs = [r for r in refs.entries if r.bibkey not in cited_bibkeys]
    tier0_refs = (cited_refs + uncited_refs)[:20]

    user_message = (
        f"{_foundation_summary(foundation, header='Research question/decision')}"
        f"Entities ({len(substrate.entities)}):\n" + "\n".join(entity_lines) + "\n\n"
        f"Edges ({len(substrate.edges)}):\n" + "\n".join(edge_lines) + "\n\n"
        f"Reference library ({len(refs.entries)}):\n" + "\n".join(ref_lines) + "\n\n"
        + _format_tier0_block(
            tier0_refs,
            title=(
                f"Tier-0 source content for top {len(tier0_refs)} references "
                "(cited first, then uncited; abstracts / snapshots / user notes)"
            ),
        )
        + f"Evidence links ({len(evidence.entries)}):\n" + "\n".join(ev_lines) + "\n\n"
        "# Task\n"
        "Audit evidence coverage. Report:\n"
        "- uncited_elements: the TOP 10 most critical elements lacking "
        "evidence (prioritise by importance to the research question). "
        "Only include elements NOT tagged [HAS EVIDENCE] above.\n"
        "- unused_references: bibkeys not cited by any element. "
        "Use the Tier-0 source content above to judge whether an "
        "uncited reference looks topically relevant or genuinely "
        "off-scope; do NOT speculate beyond what the Tier-0 text says.\n"
        "- coverage_summary: a brief (2-3 sentence) assessment.\n"
        "Be concise. Return a CrossReferenceCheckResult."
    )

    return ContextPack(system=SYSTEM_PREAMBLE, user=user_message)


def _build_summarize_reference(paths: ProjectPaths, inputs: dict[str, Any]) -> ContextPack:
    foundation = _load_foundation(paths)
    substrate = _load_substrate(paths)
    refs = load_model(ReferenceLibrary, paths.references_yaml)
    evidence = load_model(EvidenceLinkSet, paths.evidence_links_yaml)

    bibkey = inputs["bibkey"]
    ref = next((r for r in refs.entries if r.bibkey == bibkey), None)
    ref_info = f"bibkey={bibkey}"
    if ref:
        ref_info = (
            f"bibkey={ref.bibkey}, title={ref.title!r}, "
            f"authors={ref.authors}, year={ref.year}, "
            f"doi={ref.doi}, url={ref.url}, notes={ref.notes}"
        )

    # Evidence links using this bibkey.
    ev_for_ref = [e for e in evidence.entries if e.bibkey == bibkey]
    ev_lines = [f"  - {e.target_id}/{e.attribute}" for e in ev_for_ref]

    entity_lines = [f"  - {e.id}: {e.label} ({e.kind})" for e in substrate.entities]

    user_message = (
        f"{_foundation_summary(foundation, header='Research question/decision')}"
        f"Reference: {ref_info}\n\n"
        f"Currently cited by ({len(ev_for_ref)}):\n" + "\n".join(ev_lines) + "\n\n"
        "Model entities:\n" + "\n".join(entity_lines) + "\n\n"
        "Summarize this reference's relevance to the model. "
        "What elements does it support? What gaps could it fill? "
        "Return a ReferenceRelevanceResult."
    )

    return ContextPack(
        system=SYSTEM_PREAMBLE,
        user=user_message,
        target_ids=[ref.id] if ref else [],
    )


def _build_foundational_references(paths: ProjectPaths, inputs: dict[str, Any]) -> ContextPack:
    """Context for FindFoundationalReferences.

    Deliberately excludes the substrate, edges, claims, and existing
    references — this prompt finds *foundational* references for the
    topic, suitable for anchoring a fresh literature base. Network-aware
    expansion is handled by ExpandBibliography.
    """
    foundation = _load_foundation(paths)
    focus_area = (inputs.get("focus_area") or "").strip()

    user_message = (
        f"{_foundation_summary(foundation)}"
        + (f"# Focus area\n{focus_area}\n\n" if focus_area else "")
        + "# Task\n"
        + "Propose 3-6 search queries that would surface foundational, "
        "seminal, or canonical references on this topic. Aim for breadth "
        "and depth-of-field — the user is *starting* a literature base, "
        "not filling gaps in an existing one. Do NOT bias toward any "
        "particular variables or framings the user might pursue; assume "
        "the substrate is empty. Return a BibliographySearchPlan."
    )

    return ContextPack(system=SYSTEM_PREAMBLE, user=user_message)


def _build_scan_evidence_gaps(paths: ProjectPaths, inputs: dict[str, Any]) -> ContextPack:
    """Context for ScanEvidenceGaps.

    Includes the full substrate, all references with available metadata,
    all evidence links, and assumptions — this prompt audits the model's
    evidence completeness across all interpret sections at once.
    """
    foundation = _load_foundation(paths)
    substrate = _load_substrate(paths)
    refs = load_model(ReferenceLibrary, paths.references_yaml)
    evidence = load_model(EvidenceLinkSet, paths.evidence_links_yaml)
    asex = _relevant_assumptions_exclusions(paths)
    model_type = inputs.get("model_type", "cld")

    entity_lines = [f'- "{e.label}" ({e.kind}, id={e.id})' for e in substrate.entities]
    edge_lines = []
    for e in substrate.edges:
        src = next((n.label for n in substrate.entities if n.id == e.from_id), e.from_id)
        dst = next((n.label for n in substrate.entities if n.id == e.to_id), e.to_id)
        edge_lines.append(f'- "{src}" → "{dst}" ({e.kind}, id={e.id})')

    ref_lines = [f"- {r.bibkey}: {r.title}" for r in refs.entries]
    ev_lines = [
        f"- {ev.bibkey} → {ev.target_id}/{ev.attribute}" for ev in evidence.entries
    ]

    activity = _project_activity_summary(paths)

    user_message = (
        f"# Project foundation\n{_foundation_summary(foundation)}"
        + (activity + "\n" if activity else "")
        + f"# Active model type\n{model_type}\n\n"
        + f"# Entities ({len(substrate.entities)})\n"
        + ("\n".join(entity_lines) + "\n\n" if entity_lines else "(none)\n\n")
        + f"# Edges ({len(substrate.edges)})\n"
        + ("\n".join(edge_lines) + "\n\n" if edge_lines else "(none)\n\n")
        + f"# References ({len(refs.entries)})\n"
        + ("\n".join(ref_lines) + "\n\n" if ref_lines else "(none)\n\n")
        + f"# Evidence links ({len(evidence.entries)})\n"
        + ("\n".join(ev_lines) + "\n\n" if ev_lines else "(none)\n\n")
        + _format_block("Assumptions", asex["assumptions"])
        + _format_block("Exclusions", asex["exclusions"])
        + "# Task\n"
        + "Audit the model for evidence gaps across these Interpret "
        "sections: " + ", ".join(INTERPRET_SECTION_IDS) + ". For each gap, "
        "specify section_type, the claim or element it concerns, a "
        "concrete gap_description, a suggested_action, and a severity "
        "(low/medium/high). Return an EvidenceGapsScanResult with the "
        "gaps list and a one-paragraph summary."
    )

    return ContextPack(system=SYSTEM_PREAMBLE, user=user_message)
