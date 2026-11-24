"""Per-prompt context assembly — what the model sees when we call it.

Each canonical prompt has a bespoke context builder. The goal is *relevant*
context, not *all* context — a big project's substrate and log would blow
the context window and waste tokens. Builders pull the minimum useful slice
from the repo + interaction log.

Rejected past proposals are included, *explicitly labelled*, because
"we already tried this framing and rejected it" is valuable memory — but
must never be presented as fact.

Builder contract — every ``_build_*`` function:
- takes ``(paths: ProjectPaths, inputs: dict)`` and returns a ``ContextPack``;
- sets ``system`` to ``SYSTEM_PREAMBLE`` (the shared guardrails);
- populates ``target_ids`` / ``related_attributes`` so the resulting
  ``AIInteraction`` record is retrievable as memory for future calls;
- is registered in ``_BUILDERS`` under its prompt name (dispatched by
  ``build_context``), in 1:1 correspondence with ``PROMPT_LIBRARY`` and
  ``call.RESPONSE_MODELS``.
"""

from __future__ import annotations

from typing import Any

from latris.ai.context._shared import (  # noqa: F401
    APPROVED_TAG,
    REJECTED_TAG,
    SYSTEM_PREAMBLE,
    ContextPack,
    _attributes_for,
    _cld_loop_guidance,
    _edge_lines,
    _element_history_for,
    _existing_challenges_for_target,
    _format_block,
    _format_kv_block,
    _format_tier0_block,
    _foundation_summary,
    _load_foundation,
    _load_substrate,
    _neighbours_of_node,
    _past_interactions_for_target,
    _project_activity_summary,
    _relevant_assumptions_exclusions,
    _resolve_target,
    compose_system,
)
from latris.ai.context.compose import (  # noqa: F401
    _build_extract_claims,
    _build_extract_variables,
    _build_suggest_connections,
    _build_suggest_variables,
)
from latris.ai.context.configure import (  # noqa: F401
    _build_recommend_approach,
    _build_suggest_edge_polarities,
)
from latris.ai.context.elements import (  # noqa: F401
    _build_challenge,
    _build_explain,
    _build_fill_provenance_field,
    _build_steelman,
    _build_suggest_citations,
)
from latris.ai.context.interpret import (  # noqa: F401
    _build_interpret_section,
)
from latris.ai.context.interrogation import (  # noqa: F401
    _build_challenge_edge,
    _build_completeness_gate,
    _build_edge_reclassify,
    _build_evidence_demote,
    _build_verify_claim_against_source,
    _load_reference_for_verify,
)
from latris.ai.context.model import (  # noqa: F401
    _build_attack,
    _build_draft,
    _build_elicitation_interview,
    _build_find_connections,
    _build_find_counter_pathway,
    _build_generate_pack,
    _build_peer_review,
    _build_project_view,
    _build_research_gaps,
    _build_scope_check,
)
from latris.ai.context.provenance import (  # noqa: F401
    _build_generate_assumptions,
    _build_raise_questions,
    _build_suggest_decisions,
    _build_suggest_exclusions,
)
from latris.ai.context.references import (  # noqa: F401
    _build_cross_reference_check,
    _build_expand_bibliography,
    _build_foundational_references,
    _build_scan_evidence_gaps,
    _build_summarize_reference,
)
from latris.perf import span
from latris.repo.layout import ProjectPaths

_BUILDERS = {
    "ExplainThisElement": _build_explain,
    "ChallengeThisConnection": _build_challenge,
    "SuggestCitations": _build_suggest_citations,
    "DraftConceptualModel": _build_draft,
    "AttackThisModel": _build_attack,
    "FindCounterPathway": _build_find_counter_pathway,
    "ScopeCheck": _build_scope_check,
    "FindNewConnections": _build_find_connections,
    "RunElicitationInterview": _build_elicitation_interview,
    "GeneratePack": _build_generate_pack,
    "SyntheticPeerReview": _build_peer_review,
    "IdentifyResearchGaps": _build_research_gaps,
    "SteelmanOpposingView": _build_steelman,
    "ProjectToFormalView": _build_project_view,
    "ExpandBibliography": _build_expand_bibliography,
    "CrossReferenceCheck": _build_cross_reference_check,
    "SummarizeReference": _build_summarize_reference,
    "GenerateAssumptions": _build_generate_assumptions,
    "SuggestDecisions": _build_suggest_decisions,
    "SuggestExclusions": _build_suggest_exclusions,
    "RaiseQuestions": _build_raise_questions,
    # Compose extraction + synthesis
    "ExtractVariablesFromEvidence": _build_extract_variables,
    "ExtractCausalClaims": _build_extract_claims,
    "SuggestVariables": _build_suggest_variables,
    "SuggestConnections": _build_suggest_connections,
    # Configure
    "SuggestEdgePolarities": _build_suggest_edge_polarities,
    "RecommendApproach": _build_recommend_approach,
    # Interpretation — all share one builder
    "InterpretStructuralSummary": _build_interpret_section,
    "InterpretKeyFindings": _build_interpret_section,
    "InterpretSensitivity": _build_interpret_section,
    "InterpretAssumptions": _build_interpret_section,
    "InterpretEvidenceGaps": _build_interpret_section,
    "InterpretEvidenceCoverage": _build_interpret_section,
    "InterpretAnswer": _build_interpret_section,
    "InterpretImplications": _build_interpret_section,
    "InterpretConfidence": _build_interpret_section,
    "InterpretOpenQuestions": _build_interpret_section,
    # Inline per-field AI
    "FillProvenanceField": _build_fill_provenance_field,
    # Reference workflow — foundational mode
    "FindFoundationalReferences": _build_foundational_references,
    # Evidence-gap scan
    "ScanEvidenceGaps": _build_scan_evidence_gaps,
    # AI interrogation Phase 2c — completeness gate
    "CompletenessGate": _build_completeness_gate,
    # AI interrogation Phase 3a — adversarial edge reclassification
    "EdgeReclassify": _build_edge_reclassify,
    # AI interrogation Phase 3b — element-scope adversarial mutation
    "ChallengeEdge": _build_challenge_edge,
    "EvidenceDemote": _build_evidence_demote,
    # AI interrogation Phase 4a — source verification
    "VerifyClaimAgainstSource": _build_verify_claim_against_source,
}


def build_context(
    prompt_name: str,
    inputs: dict[str, Any],
    paths: ProjectPaths,
) -> ContextPack:
    """Dispatch to the per-prompt builder.

    Any prompt may carry an optional free-text ``steer`` input. It is injected
    uniformly here — as a ``<user_guidance>`` block at the end of the user
    message — rather than by each builder, so every operation is steerable
    through one code path. The system preamble states its precedence (it may
    refine emphasis but never override the schema/rules/safety).
    """
    builder = _BUILDERS.get(prompt_name)
    if builder is None:
        raise ValueError(f"no context builder for prompt {prompt_name!r}. Available: {sorted(_BUILDERS)}")
    with span("build_context", prompt=prompt_name):
        pack = builder(paths, inputs)
    _inject_steer(pack, inputs.get("steer"))
    return pack


def _inject_steer(pack: ContextPack, steer: Any) -> None:
    """Append the optional user steer to ``pack.user`` as a delimited block."""
    if not isinstance(steer, str) or not steer.strip():
        return
    pack.user = (
        pack.user.rstrip()
        + "\n\n<user_guidance>\n"
        + steer.strip()
        + "\n</user_guidance>"
    )
