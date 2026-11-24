"""Structured proposal schemas + apply() dispatchers.

Every prompt that mutates the substrate returns a pydantic ``*Proposal``.
``apply(paths)`` is the *only* way a proposal becomes a commit; it delegates
to existing ``operations/*`` so the same auto-commit + identity-guard path
is used whether the caller was a human or the AI. No proposal bypasses
``operations/``.

Prompts that are read-only (e.g. ExplainThisElement) return a
``*Result`` model with no ``apply()`` — the orchestrator logs them and
stops.
"""

from __future__ import annotations

from latris.ai.proposals._shared import (  # noqa: F401
    _ASSUMPTIONS_DESC,
    _CONFIDENCE_DESC,
    _SOURCE_BIBKEYS_DESC,
    _VALID_CONFIDENCE,
    CitationSuggestion,
    DecisionEntry,
    DraftAssumption,
    ExclusionEntry,
    ProvenanceBundle,
    QuestionEntry,
    _apply_provenance_bundle,
    _Base,
    _bind_entity_provenance,
    _cld_selected,
    _grouped_commit,
    _persist_edge_polarity,
    _record_value_conflict,
)
from latris.ai.proposals.compose import (  # noqa: F401
    ExtractedClaim,
    ExtractedClaimsResult,
    ExtractedVariable,
    ExtractedVariablesResult,
    SuggestedConnection,
    SuggestedConnectionsResult,
    SuggestedVariable,
    SuggestedVariablesResult,
)
from latris.ai.proposals.configure import (  # noqa: F401
    ApproachRecommendation,
    ApproachRecommendationResult,
    AttributeSuggestion,
    AttributeSuggestionsResult,
)
from latris.ai.proposals.elements import (  # noqa: F401
    ChallengeProposal,
    CitationsProposal,
    EvidenceAttachment,
    ExplanationResult,
    FillFieldProposal,
    SteelmanProposal,
)
from latris.ai.proposals.interpret import (  # noqa: F401
    InterpretProseResult,
)
from latris.ai.proposals.interrogation import (  # noqa: F401
    _CHALLENGE_EDGE_ACTIONS,
    _DEMOTE_ACTIONS,
    _DEMOTE_VERDICTS,
    _RECLASSIFY_TARGET_KINDS,
    _VALID_POLARITIES,
    _VERIFY_VERDICTS,
    ChallengeEdgeProposal,
    CompletenessGateResult,
    EdgeReclassifyAction,
    EdgeReclassifyProposal,
    EvidenceDemoteProposal,
    MissingVariableProposal,
    VerifyClaimAgainstSourceProposal,
)
from latris.ai.proposals.model import (  # noqa: F401
    AttackResult,
    CounterPathwayResult,
    DraftEdge,
    DraftEntity,
    DraftFraming,
    DraftModelProposal,
    EdgeProposal,
    ElicitationTurnResult,
    FormalViewProjectionResult,
    NewConnectionsProposal,
    PeerReviewResult,
    ProposedEdgeSketch,
    ReportDraft,
    ReportSection,
    ResearchGap,
    ResearchGapsResult,
    ScopeCheckResult,
)
from latris.ai.proposals.provenance import (  # noqa: F401
    AssumptionsProposal,
    DecisionsProposal,
    ExclusionsProposal,
    QuestionsProposal,
)
from latris.ai.proposals.references import (  # noqa: F401
    BibliographySearchPlan,
    CrossReferenceCheckResult,
    EvidenceGap,
    EvidenceGapsScanResult,
    EvidenceLinkSuggestion,
    ExpandBibliographyProposal,
    ReferenceRelevanceResult,
    SearchQuery,
    UncitedElement,
)


