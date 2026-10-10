"""Human-readable rendering of AI proposal/result models.

Shared between the CLI and the server — both need to produce readable
text from pydantic structured output. Each prompt_name maps to a
render function that takes the parsed model and returns plain text.
"""

from __future__ import annotations

from pydantic import BaseModel

from latris.ai import proposals as p


def _render_explanation(parsed: p.ExplanationResult) -> str:
    out = [parsed.explanation]
    if parsed.referenced_ids:
        out.append("")
        out.append("Referenced: " + ", ".join(parsed.referenced_ids))
    return "\n".join(out)


def _render_challenge(parsed: p.ChallengeProposal) -> str:
    lines = [
        "Proposed challenge:",
        f"  target: {parsed.target_id}" + (f" / {parsed.target_attribute}" if parsed.target_attribute else ""),
        f"  argument: {parsed.argument}",
    ]
    if parsed.opening_turn:
        lines.append(f"  opening turn: {parsed.opening_turn}")
    if parsed.recommended_state:
        lines.append(f"  (advisory) recommended_state: {parsed.recommended_state}")
    return "\n".join(lines)


def _render_citations(parsed: p.CitationsProposal) -> str:
    lines: list[str] = []
    if parsed.new_references:
        lines.append("New references to add:")
        for r in parsed.new_references:
            bits = [f"  [{r.bibkey}] {r.title}"]
            if r.authors:
                bits.append(", ".join(r.authors))
            if r.year:
                bits.append(str(r.year))
            if r.doi:
                bits.append(f"DOI:{r.doi}")
            lines.append(" | ".join(bits))
    if parsed.evidence_links:
        lines.append("\nEvidence links to attach:")
        for e in parsed.evidence_links:
            lines.append(f"  {e.bibkey} -> {e.target_id}/{e.attribute}")
            lines.append(f"    rationale: {e.rationale}")
    if not lines:
        return "(no suggestions)"
    return "\n".join(lines)


def _render_draft(parsed: p.DraftModelProposal) -> str:
    lines: list[str] = []
    for i, framing in enumerate(parsed.framings):
        lines.append(f"\n--- Framing {i}: {framing.name} ---")
        if framing.rationale:
            lines.append(f"  Rationale: {framing.rationale}")
        lines.append("  Entities:")
        for ent in framing.entities:
            lines.append(f"    - {ent.label} ({ent.kind})")
            if ent.description:
                lines.append(f"      {ent.description}")
        lines.append("  Edges:")
        for edg in framing.edges:
            pol = f" [{edg.polarity}]" if edg.polarity else ""
            lines.append(f"    - {edg.from_label} -> {edg.to_label} ({edg.kind}){pol}")
            if edg.description:
                lines.append(f"      {edg.description}")
        if framing.assumptions:
            lines.append("  Assumptions:")
            for a in framing.assumptions:
                target = f" (re: {a.target_label})" if a.target_label else ""
                lines.append(f"    - {a.statement}{target}")
                if a.rationale:
                    lines.append(f"      {a.rationale}")
    return "\n".join(lines)


def _render_attack(parsed: p.AttackResult) -> str:
    lines = [
        f"Weakest assumption: {parsed.weakest_assumption}",
        f"\nArgument: {parsed.argument}",
    ]
    if parsed.affected_node_ids:
        lines.append(f"\nAffected nodes: {', '.join(parsed.affected_node_ids)}")
    if parsed.recommended_action:
        lines.append(f"\nRecommended action: {parsed.recommended_action}")
    proposed: list[str] = []
    if parsed.record_assumption:
        proposed.append(f"  - record assumption: {parsed.weakest_assumption}")
    if parsed.follow_up_question:
        proposed.append(f"  - log open question: {parsed.follow_up_question}")
    if proposed:
        lines.append("\nProposed records:")
        lines.extend(proposed)
    return "\n".join(lines)


def _render_counter_pathway(parsed: p.CounterPathwayResult) -> str:
    lines = [
        f"Missing mechanism: {parsed.missing_mechanism}",
        f"\nArgument: {parsed.argument}",
    ]
    if parsed.supporting_bibkey:
        lines.append(f"\nSupporting reference: {parsed.supporting_bibkey}")
    if parsed.proposed_nodes:
        lines.append("\nProposed new nodes (advisory):")
        for n in parsed.proposed_nodes:
            lines.append(f"  - {n}")
    if parsed.proposed_edges:
        lines.append("\nProposed pathway edges (advisory — NOT auto-added):")
        for e in parsed.proposed_edges:
            tail = f" — {e.rationale}" if e.rationale else ""
            lines.append(f"  - {e.from_label} →({e.polarity}) {e.to_label}{tail}")
    if parsed.record_question and parsed.missing_mechanism.strip():
        lines.append("\nProposed records:")
        lines.append(f"  - log open question: counter-pathway '{parsed.missing_mechanism}'")
    return "\n".join(lines)


def _render_scope_check(parsed: p.ScopeCheckResult) -> str:
    lines = [f"Verdict: {parsed.verdict}"]
    if parsed.reasoning:
        lines.append(f"\nReasoning: {parsed.reasoning}")
    if parsed.suggestions:
        lines.append("\nSuggestions:")
        for s in parsed.suggestions:
            lines.append(f"  - {s}")
    if parsed.proposed_exclusions:
        lines.append("\nProposed exclusions:")
        for e in parsed.proposed_exclusions:
            lines.append(f"  - {e.statement} ({e.rationale})")
    if parsed.proposed_questions:
        lines.append("\nProposed questions:")
        for q in parsed.proposed_questions:
            lines.append(f"  - {q.question}")
    return "\n".join(lines)


def _render_find_connections(parsed: p.NewConnectionsProposal) -> str:
    lines: list[str] = []
    for i, prop in enumerate(parsed.proposals):
        lines.append(f"  [{i}] {prop.from_id} -> {prop.to_id} ({prop.kind})")
        if prop.description:
            lines.append(f"      {prop.description}")
        elif prop.rationale:
            lines.append(f"      {prop.rationale}")
    if not lines:
        return "(no new connections suggested)"
    return "Proposed new connections:\n" + "\n".join(lines)


def _render_peer_review(parsed: p.PeerReviewResult) -> str:
    lines = [
        f"Reviewer role: {parsed.reviewer_role}",
        f"\nScope: {parsed.scope_assessment}",
        f"\nRigor: {parsed.rigor_assessment}",
        f"\nEvidence: {parsed.evidence_assessment}",
    ]
    if parsed.major_risks:
        lines.append("\nMajor risks:")
        for r in parsed.major_risks:
            lines.append(f"  - {r}")
    if parsed.proposed_questions:
        lines.append("\nQuestions for the modeller:")
        for q in parsed.proposed_questions:
            lines.append(f"  ? {q}")
    return "\n".join(lines)


def _render_gaps(parsed: p.ResearchGapsResult) -> str:
    if not parsed.gaps:
        return "(no research gaps identified)"
    lines: list[str] = []
    for g in parsed.gaps:
        lines.append(f"  [{g.priority}] {g.description}")
        if g.affected_node_ids:
            lines.append(f"    affects: {', '.join(g.affected_node_ids)}")
        if g.suggested_action:
            lines.append(f"    action: {g.suggested_action}")
    return "Research gaps:\n" + "\n".join(lines)


def _render_steelman(parsed: p.SteelmanProposal) -> str:
    lines = [
        f"Steelman opposing view for: {parsed.target_id}",
        f"\n{parsed.opposing_view}",
    ]
    if parsed.rationale:
        lines.append(f"\nRationale: {parsed.rationale}")
    return "\n".join(lines)


def _render_projection(parsed: p.FormalViewProjectionResult) -> str:
    lines = [f"View: {parsed.target_view}"]
    if parsed.rationale:
        lines.append(f"\nRationale: {parsed.rationale}")
    if parsed.recommended_mappings:
        lines.append("\nRecommended mappings:")
        for m in parsed.recommended_mappings:
            parts = [f"{k}: {v}" for k, v in m.items()]
            lines.append(f"  - {'; '.join(parts)}")
    if parsed.conflicts:
        lines.append("\nConflicts:")
        for c in parsed.conflicts:
            lines.append(f"  ! {c}")
    return "\n".join(lines)


def _render_expand_bibliography(parsed) -> str:
    """Render either BibliographySearchPlan (from LLM) or ExpandBibliographyProposal (after search)."""
    # BibliographySearchPlan (queries from LLM)
    if hasattr(parsed, "queries"):
        if not parsed.queries:
            return "(no search queries proposed)"
        lines = ["Search queries:"]
        for i, q in enumerate(parsed.queries):
            lines.append(f"  [{i + 1}] {q.query}")
            if q.rationale:
                lines.append(f"      {q.rationale}")
        return "\n".join(lines)
    # ExpandBibliographyProposal (real results)
    if not parsed.new_references:
        return "(no new references proposed)"
    lines = ["Proposed references:"]
    for r in parsed.new_references:
        bits = [f"[{r.bibkey}] {r.title}"]
        if r.authors:
            bits.append(", ".join(r.authors[:3]))
        if r.year:
            bits.append(str(r.year))
        if r.doi:
            bits.append(f"DOI:{r.doi}")
        lines.append("  " + " | ".join(bits))
    return "\n".join(lines)


def _render_cross_reference_check(parsed: p.CrossReferenceCheckResult) -> str:
    lines: list[str] = []
    if parsed.coverage_summary:
        lines.append(parsed.coverage_summary)
    if parsed.uncited_elements:
        lines.append(f"\nUncited elements ({len(parsed.uncited_elements)}):")
        for e in parsed.uncited_elements:
            label = e.label or e.element_id[:16]
            attrs = ", ".join(e.attributes_without_evidence) if e.attributes_without_evidence else "general"
            lines.append(f"  - {label} (missing: {attrs})")
    if parsed.unused_references:
        lines.append(f"\nUnused references ({len(parsed.unused_references)}):")
        for bibkey in parsed.unused_references:
            lines.append(f"  - {bibkey}")
    if not parsed.uncited_elements and not parsed.unused_references:
        lines.append("\nAll elements have evidence; all references are cited.")
    return "\n".join(lines)


def _render_reference_relevance(parsed: p.ReferenceRelevanceResult) -> str:
    lines = [f"Reference: {parsed.bibkey}", f"\n{parsed.relevance_summary}"]
    if parsed.connected_elements:
        lines.append(f"\nConnected elements: {', '.join(parsed.connected_elements)}")
    return "\n".join(lines)


def _render_assumptions(parsed: p.AssumptionsProposal) -> str:
    if not parsed.assumptions:
        return "(no assumptions generated)"
    lines = [f"Assumptions for {parsed.target_id[:16]}:"]
    for a in parsed.assumptions:
        lines.append(f"  - {a.statement}")
        if a.rationale:
            lines.append(f"    {a.rationale}")
    return "\n".join(lines)


def _render_decisions(parsed: p.DecisionsProposal) -> str:
    if not parsed.decisions:
        return "(no decisions suggested)"
    lines = [f"Decisions for {parsed.target_id[:16]}:"]
    for d in parsed.decisions:
        lines.append(f"  - {d.statement}")
        lines.append(f"    Rationale: {d.rationale}")
    return "\n".join(lines)


def _render_exclusions(parsed: p.ExclusionsProposal) -> str:
    if not parsed.exclusions:
        return "(no exclusions suggested)"
    lines = ["Proposed exclusions:"]
    for e in parsed.exclusions:
        lines.append(f"  - {e.statement}")
        lines.append(f"    Rationale: {e.rationale}")
    return "\n".join(lines)


def _render_questions(parsed: p.QuestionsProposal) -> str:
    if not parsed.questions:
        return "(no questions raised)"
    lines = [f"Questions for {parsed.target_id[:16]}:"]
    for q in parsed.questions:
        lines.append(f"  ? {q.question}")
    return "\n".join(lines)


RENDERERS: dict[str, callable] = {
    "ExplainThisElement": _render_explanation,
    "ChallengeThisConnection": _render_challenge,
    "SuggestCitations": _render_citations,
    "DraftConceptualModel": _render_draft,
    "AttackThisModel": _render_attack,
    "FindCounterPathway": _render_counter_pathway,
    "ScopeCheck": _render_scope_check,
    "FindNewConnections": _render_find_connections,
    "RunElicitationInterview": lambda parsed: (
        f"Question: {parsed.question}" + (f"\nProposed edit: {parsed.proposed_edit}" if parsed.proposed_edit else "")
    ),
    "GeneratePack": lambda parsed: f"--- {parsed.pack} pack ---\n{parsed.render_markdown()}",
    "SyntheticPeerReview": _render_peer_review,
    "IdentifyResearchGaps": _render_gaps,
    "SteelmanOpposingView": _render_steelman,
    "ProjectToFormalView": _render_projection,
    "ExpandBibliography": _render_expand_bibliography,
    "CrossReferenceCheck": _render_cross_reference_check,
    "SummarizeReference": _render_reference_relevance,
    "GenerateAssumptions": _render_assumptions,
    "SuggestDecisions": _render_decisions,
    "SuggestExclusions": _render_exclusions,
    "RaiseQuestions": _render_questions,
    # Configure prompts
    "SuggestEdgePolarities": lambda parsed: parsed.model_dump_json(indent=2),
    # Interpretation prompts — prose is the rendered output
    "InterpretStructuralSummary": lambda parsed: parsed.prose,
    "InterpretKeyFindings": lambda parsed: parsed.prose,
    "InterpretSensitivity": lambda parsed: parsed.prose,
    "InterpretAssumptions": lambda parsed: parsed.prose,
    "InterpretEvidenceGaps": lambda parsed: parsed.prose,
    "InterpretEvidenceCoverage": lambda parsed: parsed.prose,
    "InterpretAnswer": lambda parsed: parsed.prose,
    "InterpretImplications": lambda parsed: parsed.prose,
    "InterpretConfidence": lambda parsed: parsed.prose,
    "InterpretOpenQuestions": lambda parsed: parsed.prose,
    # Story (Communicate phase) — prose is the rendered output
    "StoryBeatProse": lambda parsed: parsed.prose,
    # Inline per-field AI — value is the deliverable; rationale shown as tooltip
    "FillProvenanceField": lambda parsed: parsed.value,
    # Foundational references — search plan (same shape as ExpandBibliography intermediate)
    "FindFoundationalReferences": _render_expand_bibliography,
    # Evidence-gap scan — short summary then per-section gaps
    "ScanEvidenceGaps": lambda parsed: (
        (parsed.summary + "\n\n" if parsed.summary else "")
        + "\n".join(
            f"[{g.severity}] {g.section_type}: {g.gap_description}"
            for g in parsed.gaps
        )
    ),
    # AI interrogation Phase 4a — source verification
    "VerifyClaimAgainstSource": lambda parsed: (
        f"[{parsed.confidence}] verdict: {parsed.verdict}"
        + (f"\nquote: \"{parsed.quote}\"" if parsed.verdict == "supports" and parsed.quote else "")
        + (f"\nrationale: {parsed.rationale}" if parsed.rationale else "")
        + (f"\n\n{parsed.summary}" if parsed.summary else "")
    ),
    # AI interrogation Phase 3b — element-scope adversarial mutation
    "ChallengeEdge": lambda parsed: (
        (parsed.summary + "\n\n" if parsed.summary else "")
        + (
            f"[{parsed.confidence}] action: {parsed.action}"
            + (f" → query: {parsed.search_query!r}" if parsed.action == "evidence_search" else "")
            + (f" → polarity: {parsed.new_polarity}" if parsed.action == "polarity_flip" else "")
            + (f"\nrationale: {parsed.rationale}" if parsed.rationale else "")
        )
    ),
    "EvidenceDemote": lambda parsed: (
        (parsed.summary + "\n\n" if parsed.summary else "")
        + (
            f"[{parsed.confidence}] action: {parsed.action}"
            + (f" → verdict: {parsed.new_verdict}" if parsed.action == "change_verdict" else "")
            + (f"\nrationale: {parsed.rationale}" if parsed.rationale else "")
        )
    ),
    # AI interrogation Phase 3a — adversarial edge reclassification
    "EdgeReclassify": lambda parsed: (
        (parsed.summary + "\n\n" if parsed.summary else "")
        + "\n".join(
            (
                f"[{a.confidence}] {a.target_id}: keep"
                if a.action == "keep"
                else f"[{a.confidence}] {a.target_id}: retag → {a.new_kind} — {a.rationale}"
                if a.action == "retag"
                else f"[{a.confidence}] {a.target_id}: remove — {a.rationale}"
            )
            for a in parsed.actions
        )
    ),
}


def render(prompt_name: str, parsed: BaseModel) -> str:
    """Render a parsed AI result to human-readable text.

    Falls back to JSON dump if no renderer is registered.
    """
    renderer = RENDERERS.get(prompt_name)
    if renderer:
        return renderer(parsed)
    return parsed.model_dump_json(indent=2)
