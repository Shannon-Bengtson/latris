from __future__ import annotations

from string import Formatter

from pydantic import BaseModel

from latris.ai import prompts as prompt_lib
from latris.ai.prompts import PromptIntent, PromptScope


def _extract_placeholders(template: str) -> set[str]:
    """Top-level field names referenced by ``template``'s ``{placeholder}`` syntax.

    Handles ``{{`` / ``}}`` escapes via ``string.Formatter.parse`` and strips
    any ``.attr`` / ``[index]`` suffixes so e.g. ``{x.y}`` reports ``x``.
    """
    names: set[str] = set()
    for _literal, field_name, _spec, _conv in Formatter().parse(template):
        if not field_name:
            continue
        top = field_name.split(".", 1)[0].split("[", 1)[0]
        names.add(top)
    return names

EXPECTED_PROMPTS = {
    "DraftConceptualModel",
    "RunElicitationInterview",
    "FindNewConnections",
    "ProjectToFormalView",
    "ChallengeThisConnection",
    "AttackThisModel",
    "FindCounterPathway",
    "SteelmanOpposingView",
    "SyntheticPeerReview",
    "IdentifyResearchGaps",
    "ScopeCheck",
    "SuggestCitations",
    "ExplainThisElement",
    "GeneratePack",
    "ExpandBibliography",
    "CrossReferenceCheck",
    "SummarizeReference",
    "GenerateAssumptions",
    "SuggestDecisions",
    "SuggestExclusions",
    "RaiseQuestions",
    # Interpretation prompts
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
    # Compose extraction + synthesis prompts
    "ExtractVariablesFromEvidence",
    "ExtractCausalClaims",
    "SuggestVariables",
    "SuggestConnections",
    "SuggestEdgePolarities",
    # Model-approach recommendation (Formalise → Model selection)
    "RecommendApproach",
    # Inline per-field AI
    "FillProvenanceField",
    # Reference workflow — foundational mode (network-aware = ExpandBibliography)
    "FindFoundationalReferences",
    # Evidence-gap scan across all interpret sections
    "ScanEvidenceGaps",
    # AI interrogation Phase 2c — completeness gate
    "CompletenessGate",
    # AI interrogation Phase 3a — adversarial edge reclassification
    "EdgeReclassify",
    # AI interrogation Phase 3b — element-scope adversarial mutation
    "ChallengeEdge",
    "EvidenceDemote",
    # AI interrogation Phase 4a — source verification
    "VerifyClaimAgainstSource",
    # Story (Communicate phase)
    "StoryBeatProse",
}


def test_all_canonical_prompts_present() -> None:
    assert set(prompt_lib.PROMPT_LIBRARY.keys()) == EXPECTED_PROMPTS


def test_every_prompt_is_well_formed() -> None:
    for spec in prompt_lib.list_all():
        assert spec.name
        assert spec.title
        assert spec.description
        assert spec.template
        assert spec.output_hint
        assert issubclass(spec.inputs, BaseModel)
        assert spec.scope in PromptScope
        assert spec.intent in PromptIntent


def test_get_unknown_prompt_raises() -> None:
    try:
        prompt_lib.get("Hallucinate")
    except KeyError as exc:
        assert "Hallucinate" in str(exc)
    else:
        raise AssertionError("expected KeyError")


def test_inputs_schema_accepts_valid_input() -> None:
    spec = prompt_lib.get("ChallengeThisConnection")
    instance = spec.inputs(target_id="edge_01HZZZZZZZZZZZZZZZZZZZZZZZ")
    assert instance.target_id.startswith("edge_")
    assert instance.target_attribute is None


def test_inputs_schema_rejects_invalid_input() -> None:
    spec = prompt_lib.get("ChallengeThisConnection")
    try:
        spec.inputs(target_id="edge_X", unknown_field="x")
    except Exception as exc:
        # Either ValidationError (extra="forbid") or TypeError; either is fine.
        assert "unknown_field" in str(exc) or "extra" in str(exc).lower()
    else:
        raise AssertionError("expected extra field to be rejected")


def test_scope_and_intent_coverage() -> None:
    """Every prompt has an explicit (not default) scope and intent."""
    for spec in prompt_lib.list_all():
        # These should never be the PromptSpec defaults for the whole library;
        # each prompt must have a considered assignment.
        assert (spec.scope, spec.intent) != (PromptScope.model, PromptIntent.insight) or spec.name in {
            "AttackThisModel",
            "ScopeCheck",
            "SyntheticPeerReview",
            "IdentifyResearchGaps",
            "GeneratePack",
            "ProjectToFormalView",
            "CrossReferenceCheck",
            # Interpretation prompts (all model-level insight)
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
            # Compose extraction + synthesis prompts (model-level insight)
            "ExtractVariablesFromEvidence",
            "ExtractCausalClaims",
            "SuggestVariables",
            "SuggestConnections",
            "SuggestEdgePolarities",
            "RecommendApproach",
            # Evidence-gap scan (model-level insight)
            "ScanEvidenceGaps",
            # Story beat prose (model-level insight)
            "StoryBeatProse",
        }, f"{spec.name} has default scope/intent — was it deliberately set?"


def test_list_by_scope() -> None:
    model_prompts = prompt_lib.list_by_scope(PromptScope.model)
    element_prompts = prompt_lib.list_by_scope(PromptScope.element)
    assert len(model_prompts) + len(element_prompts) == len(prompt_lib.PROMPT_LIBRARY)
    assert all(p.scope == PromptScope.model for p in model_prompts)
    assert all(p.scope == PromptScope.element for p in element_prompts)
    # Known element-level prompts
    element_names = {p.name for p in element_prompts}
    assert "ExplainThisElement" in element_names
    assert "ChallengeThisConnection" in element_names
    assert "SuggestCitations" in element_names
    assert "SteelmanOpposingView" in element_names
    assert "SummarizeReference" in element_names


def test_template_placeholders_match_inputs() -> None:
    """Every ``{placeholder}`` in a template must name a field on its inputs schema.

    Catches the silent-drift failure mode where a template references a
    placeholder that no longer (or never did) correspond to an inputs field.
    Only the Interpret prompts actually ``.format()`` their templates at
    runtime, but the placeholders in other templates still function as
    documentation that the input field exists — so the rule is uniform.
    """
    for spec in prompt_lib.list_all():
        placeholders = _extract_placeholders(spec.template)
        if not placeholders:
            continue
        field_names = set(spec.inputs.model_fields.keys())
        unknown = placeholders - field_names
        assert not unknown, (
            f"{spec.name}: template references placeholder(s) {sorted(unknown)} "
            f"not present in {spec.inputs.__name__} (fields: {sorted(field_names)})"
        )


def test_list_by_intent() -> None:
    insights = prompt_lib.list_by_intent(PromptIntent.insight)
    actions = prompt_lib.list_by_intent(PromptIntent.action)
    workflows = prompt_lib.list_by_intent(PromptIntent.workflow)
    assert len(insights) + len(actions) + len(workflows) == len(prompt_lib.PROMPT_LIBRARY)
    assert all(p.intent == PromptIntent.insight for p in insights)
    assert all(p.intent == PromptIntent.action for p in actions)
    assert len(workflows) == 1  # only RunElicitationInterview
