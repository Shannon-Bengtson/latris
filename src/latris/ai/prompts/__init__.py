"""Canonical prompt library.

The concept doc defines a fixed set of prompts the AI layer will support —
deliberately not an open chatbox. Each prompt is a ``PromptSpec`` with a
typed input schema and a template. Templates use ``{placeholders}`` that
will be substituted by the future call layer. No network calls here.
"""

from __future__ import annotations

from dataclasses import replace

from pydantic import BaseModel

from latris.ai import proposals as _proposals
from latris.ai.prompts import (
    compose,
    configure,
    evidence,
    fields,
    interpret,
    interrogation,
    model,
    provenance,
    references,
)
from latris.ai.prompts._guidance import (  # noqa: F401
    _EDGE_MECHANISM_GUIDANCE,
    _EDGE_POLARITY_GUIDANCE,
    _ENTITY_PROVENANCE_GUIDANCE,
    _EXISTENCE_ATTRIBUTE_CONVENTIONS,
    _EXISTENCE_ATTRIBUTE_DEFAULT_NOTE,
    _LOOP_CLOSURE_GUIDANCE,
    _MECHANISTIC_GRANULARITY_GUIDANCE,
    _NO_FABRICATION_GUIDANCE,
    _NODE_FEWSHOT,
    _NODE_KIND_RUBRIC,
    _SCOPE_CONTRACT_GUIDANCE,
)
from latris.ai.prompts._spec import (  # noqa: F401
    ModelTypeStr,
    PackName,
    PromptIntent,
    PromptMode,
    PromptScope,
    PromptSpec,
    ViewKind,
    _validate_model_type,
)
from latris.ai.prompts.fields import (  # noqa: F401
    FIELD_GUIDANCE,
    field_guidance,
)
from latris.ai.prompts.inputs import (  # noqa: F401
    AttackThisModelInputs,
    ChallengeEdgeInputs,
    ChallengeThisConnectionInputs,
    CompletenessGateInputs,
    CrossReferenceCheckInputs,
    DraftConceptualModelInputs,
    EdgeReclassifyInputs,
    EvidenceDemoteInputs,
    ExpandBibliographyInputs,
    ExplainThisElementInputs,
    ExtractCausalClaimsInputs,
    ExtractVariablesFromEvidenceInputs,
    FillProvenanceFieldInputs,
    FindCounterPathwayInputs,
    FindFoundationalReferencesInputs,
    FindNewConnectionsInputs,
    GenerateAssumptionsInputs,
    GeneratePackInputs,
    IdentifyResearchGapsInputs,
    InterpretSectionInputs,
    ProjectToFormalViewInputs,
    RaiseQuestionsInputs,
    RecommendApproachInputs,
    RunElicitationInterviewInputs,
    ScanEvidenceGapsInputs,
    ScopeCheckInputs,
    SteelmanOpposingViewInputs,
    SuggestCitationsInputs,
    SuggestConnectionsInputs,
    SuggestDecisionsInputs,
    SuggestEdgePolaritiesInputs,
    SuggestExclusionsInputs,
    SuggestVariablesInputs,
    SummarizeReferenceInputs,
    SyntheticPeerReviewInputs,
    VerifyClaimAgainstSourceInputs,
    _In,
)

# ---------- The library ----------
#
# ``_RAW_LIBRARY`` holds the per-prompt literals (input schema + template +
# classification), gathered from the modules beside this one — each holds one
# family of prompts as ``PROMPTS``. Response models and per-op temperature are
# attached to each spec by ``_wire`` at the bottom of this section, producing
# ``PROMPT_LIBRARY``.

_RAW_LIBRARY: dict[str, PromptSpec] = {
    **model.PROMPTS,
    **references.PROMPTS,
    **provenance.PROMPTS,
    **interpret.PROMPTS,
    **compose.PROMPTS,
    **configure.PROMPTS,
    **fields.PROMPTS,
    **evidence.PROMPTS,
    **interrogation.PROMPTS,
}


# ---------- Response-model + per-operation wiring ----------
#
# A prompt's output schema lives HERE (next to its spec), not in a separate
# ``RESPONSE_MODELS`` dict in call.py. ``call.py`` re-exports a derived alias
# for backwards compatibility, but ``spec.response_model`` is the single source
# of truth. ``_wire`` raises at import time if this mapping drifts out of
# bijection with the prompt specs — a stronger guarantee than a test alone.

_RESPONSE_MODELS: dict[str, type[BaseModel]] = {
    "ExplainThisElement": _proposals.ExplanationResult,
    "ChallengeThisConnection": _proposals.ChallengeProposal,
    "SuggestCitations": _proposals.CitationsProposal,
    "DraftConceptualModel": _proposals.DraftModelProposal,
    "AttackThisModel": _proposals.AttackResult,
    "FindCounterPathway": _proposals.CounterPathwayResult,
    "ScopeCheck": _proposals.ScopeCheckResult,
    "FindNewConnections": _proposals.NewConnectionsProposal,
    "RunElicitationInterview": _proposals.ElicitationTurnResult,
    "GeneratePack": _proposals.ReportDraft,
    "SyntheticPeerReview": _proposals.PeerReviewResult,
    "IdentifyResearchGaps": _proposals.ResearchGapsResult,
    "SteelmanOpposingView": _proposals.SteelmanProposal,
    "ProjectToFormalView": _proposals.FormalViewProjectionResult,
    "ExpandBibliography": _proposals.BibliographySearchPlan,
    "CrossReferenceCheck": _proposals.CrossReferenceCheckResult,
    "SummarizeReference": _proposals.ReferenceRelevanceResult,
    "GenerateAssumptions": _proposals.AssumptionsProposal,
    "SuggestDecisions": _proposals.DecisionsProposal,
    "SuggestExclusions": _proposals.ExclusionsProposal,
    "RaiseQuestions": _proposals.QuestionsProposal,
    # Compose extraction + synthesis prompts
    "ExtractVariablesFromEvidence": _proposals.ExtractedVariablesResult,
    "ExtractCausalClaims": _proposals.ExtractedClaimsResult,
    "SuggestVariables": _proposals.SuggestedVariablesResult,
    "SuggestConnections": _proposals.SuggestedConnectionsResult,
    # Configure prompts
    "SuggestEdgePolarities": _proposals.AttributeSuggestionsResult,
    # Model-approach recommendation (Formalise → Model selection)
    "RecommendApproach": _proposals.ApproachRecommendationResult,
    # Inline per-field AI
    "FillProvenanceField": _proposals.FillFieldProposal,
    # Reference workflow — foundational vs network-aware
    "FindFoundationalReferences": _proposals.BibliographySearchPlan,
    # Evidence-gap scan across all interpret sections
    "ScanEvidenceGaps": _proposals.EvidenceGapsScanResult,
    # Interpretation prompts
    "InterpretStructuralSummary": _proposals.InterpretProseResult,
    "InterpretKeyFindings": _proposals.InterpretProseResult,
    "InterpretSensitivity": _proposals.InterpretProseResult,
    "InterpretAssumptions": _proposals.InterpretProseResult,
    "InterpretEvidenceGaps": _proposals.InterpretProseResult,
    "InterpretEvidenceCoverage": _proposals.InterpretProseResult,
    "InterpretAnswer": _proposals.InterpretProseResult,
    "InterpretImplications": _proposals.InterpretProseResult,
    "InterpretConfidence": _proposals.InterpretProseResult,
    "InterpretOpenQuestions": _proposals.InterpretProseResult,
    # AI interrogation Phase 2c — completeness gate
    "CompletenessGate": _proposals.CompletenessGateResult,
    # AI interrogation Phase 3a — adversarial edge reclassification
    "EdgeReclassify": _proposals.EdgeReclassifyProposal,
    # AI interrogation Phase 3b — element-scope adversarial mutation
    "ChallengeEdge": _proposals.ChallengeEdgeProposal,
    "EvidenceDemote": _proposals.EvidenceDemoteProposal,
    # AI interrogation Phase 4a — source verification (apply-time verbatim check)
    "VerifyClaimAgainstSource": _proposals.VerifyClaimAgainstSourceProposal,
}


# Per-operation temperature overrides (None → project/config default). Populated
# as prompts are re-authored to the effectiveness standard; extraction ops run
# cool for consistent granularity.
_OP_TEMPERATURE: dict[str, float] = {
    # Extraction/synthesis of nodes+edges — run cool so granularity and kind
    # assignment stay consistent run-to-run (the config default of 0.3 is warm
    # enough to visibly vary label phrasing).
    "ExtractVariablesFromEvidence": 0.1,
    "SuggestVariables": 0.1,
    "ExtractCausalClaims": 0.1,
    "SuggestConnections": 0.15,
    "FindNewConnections": 0.15,
    # Drafting multiple distinct framings is mildly generative — keep a little
    # warmth so the framings differ, but below the default.
    "DraftConceptualModel": 0.2,
}


# Prompts where the LLM returns an intermediate result (e.g. search queries)
# that the server transforms into the real proposal. These have no apply() on
# their response model but must stay pending in preview mode so the user can
# approve/reject the final result.
_SERVER_TRANSFORMED = {"ExpandBibliography", "FindFoundationalReferences"}


# Hybrid prompts produce critique prose AND a bounded structured proposal.
# The CLI prints the prose alongside the apply summary, so reviewers see
# both the critique and the audit-trail records that were created.
_HYBRID = {
    "AttackThisModel",
    "FindCounterPathway",
    "ScopeCheck",
    "IdentifyResearchGaps",
    "ScanEvidenceGaps",
    "CrossReferenceCheck",
    "EdgeReclassify",
    "ChallengeEdge",
    "EvidenceDemote",
    "VerifyClaimAgainstSource",
}


_READ_ONLY = {
    "ExplainThisElement",
    # RecommendApproach is read-only: the user accepts a recommendation, which
    # records a ModelChoice via its own route — the call never mutates.
    "RecommendApproach",
    # AttackThisModel, ScopeCheck, IdentifyResearchGaps, ScanEvidenceGaps,
    # and CrossReferenceCheck are now hybrid: their Result classes have
    # apply() methods that produce bounded provenance mutations
    # (assumptions, exclusions, questions, evidence-link suggestions)
    # alongside the critique prose that always renders into the report.
    # SyntheticPeerReview stays read-only — its value is the synthetic
    # external voice itself, and silent mutation from a synthetic
    # reviewer would erode the provenance distinction between
    # "AI surfaced a critique" and "the project formally accepted it".
    "RunElicitationInterview",
    "GeneratePack",
    "SyntheticPeerReview",
    "ProjectToFormalView",
    "SummarizeReference",
    # Compose extraction + synthesis (read-only)
    "ExtractVariablesFromEvidence",
    "ExtractCausalClaims",
    "SuggestVariables",
    "SuggestConnections",
    # SuggestEdgePolarities is *mutating* — its apply() commits all
    # suggestions via the Configure batch path. (Was previously read-only
    # because the GUI staged suggestions and applied them via a separate
    # /configure/apply-attributes call. The CLI dispatches apply directly.)
    # Inline per-field AI — GUI inserts value into editable field, user saves via normal mutation
    "FillProvenanceField",
    # Interpretation prompts (all read-only)
    "InterpretStructuralSummary",
    "InterpretKeyFindings",
    "InterpretSensitivity",
    "InterpretAssumptions",
    "InterpretEvidenceGaps",
    "InterpretEvidenceCoverage",
    "InterpretAnswer",
    "InterpretImplications",
    "InterpretConfidence",
    "InterpretOpenQuestions",
}


def _modes() -> dict[str, PromptMode]:
    modes: dict[str, PromptMode] = {}
    for mode, names in (("server_transformed", _SERVER_TRANSFORMED), ("hybrid", _HYBRID), ("read_only", _READ_ONLY)):
        for name in names:
            if name in modes:
                raise RuntimeError(f"prompt {name!r} is both {modes[name]} and {mode}")
            modes[name] = mode  # type: ignore[assignment]
    return modes


_MODES = _modes()


def _wire(raw: dict[str, PromptSpec]) -> dict[str, PromptSpec]:
    """Attach response model + per-op temperature to each spec.

    Raises at import if the response-model mapping drifts out of bijection with
    the prompt specs, so a missing/orphan wiring fails fast rather than at first
    call.
    """
    missing = set(raw) - set(_RESPONSE_MODELS)
    if missing:
        raise RuntimeError(f"prompts missing a response model: {sorted(missing)}")
    orphan = set(_RESPONSE_MODELS) - set(raw)
    if orphan:
        raise RuntimeError(f"response models with no prompt spec: {sorted(orphan)}")
    stray = set(_MODES) - set(raw)
    if stray:
        raise RuntimeError(f"modes given for unknown prompts: {sorted(stray)}")
    return {
        name: replace(
            spec,
            response_model=_RESPONSE_MODELS[name],
            temperature=_OP_TEMPERATURE.get(name),
            mode=_MODES.get(name, "mutating"),
        )
        for name, spec in raw.items()
    }


PROMPT_LIBRARY: dict[str, PromptSpec] = _wire(_RAW_LIBRARY)


def get(name: str) -> PromptSpec:
    if name not in PROMPT_LIBRARY:
        known = ", ".join(sorted(PROMPT_LIBRARY.keys()))
        raise KeyError(f"unknown prompt {name!r}. Known prompts: {known}")
    return PROMPT_LIBRARY[name]


def list_all() -> list[PromptSpec]:
    return sorted(PROMPT_LIBRARY.values(), key=lambda p: p.name)


def list_by_scope(scope: PromptScope) -> list[PromptSpec]:
    return sorted(
        [p for p in PROMPT_LIBRARY.values() if p.scope == scope],
        key=lambda p: p.name,
    )


def list_by_intent(intent: PromptIntent) -> list[PromptSpec]:
    return sorted(
        [p for p in PROMPT_LIBRARY.values() if p.intent == intent],
        key=lambda p: p.name,
    )
