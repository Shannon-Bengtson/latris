"""Configure prompts: which modelling approach suits the question, and link polarities."""

from __future__ import annotations

from latris.ai.prompts._spec import PromptIntent, PromptScope, PromptSpec
from latris.ai.prompts.inputs import RecommendApproachInputs, SuggestEdgePolaritiesInputs

PROMPTS: dict[str, PromptSpec] = {
    "RecommendApproach": PromptSpec(
        name="RecommendApproach",
        title="Recommend a modelling approach",
        description="Given the modelling question, context, and available evidence, "
        "rank the available formalisms by suitability with a one-line rationale each.",
        inputs=RecommendApproachInputs,
        template=(
            "You are advising on which formal modelling approach(es) fit this "
            "project. Weigh the modelling question, background, the available "
            "evidence, AND the current model structure described above "
            "(including whether it contains feedback loops). For EACH candidate "
            "formalism, judge its suitability as 'recommended', 'consider', or "
            "'not_suited', and give a one-sentence rationale grounded in THIS "
            "project (not a generic description of the formalism).\n\n"
            "Structural fit is decisive: a formalism that REQUIRES AN ACYCLIC "
            "GRAPH (e.g. DAG, Bayesian network) cannot represent a model that "
            "contains feedback loops — mark it 'not_suited' and say so plainly. "
            "A formalism built around feedback loops (e.g. CLD) needs them to be "
            "present to be a good fit. Each candidate's structural fit is noted "
            "below.\n\n"
            "Candidate formalisms (with structural fit):\n{candidates}\n\n"
            "Available evidence:\n{evidence_summary}\n\n"
            "Multiple formalisms may be 'recommended' when modelling the question "
            "more than one way adds value (triangulation). Return an "
            "ApproachRecommendationResult."
        ),
        output_hint="An ApproachRecommendationResult with one ApproachRecommendation per candidate.",
        scope=PromptScope.model,
        intent=PromptIntent.insight,
    ),
    "SuggestEdgePolarities": PromptSpec(
        name="SuggestEdgePolarities",
        title="Suggest edge polarities",
        description="Given a CLD or FCM model, suggest polarity (+/−/~) or "
        "weight values for edges based on variable names, "
        "descriptions, and evidence.",
        inputs=SuggestEdgePolaritiesInputs,
        template=(
            "You are configuring a {model_type} model. For each edge, "
            "determine the polarity based on the causal relationship "
            "between from and to variables.\n"
            "Edges to analyse:\n{edges}\n"
            "Allowed CLD polarity values:\n"
            "  '+' — source and target move in the same direction.\n"
            "  '-' — source and target move in opposite directions.\n"
            "  '~' — ambiguous: literature is genuinely contested, "
            "       the relationship is non-monotonic, or the polarity "
            "       depends on a condition not captured by another "
            "       variable in the model. Prefer '+' or '-' when the "
            "       polarity is clear; '~' is for genuinely contested cases.\n\n"
            "Allowed FCM weight values (a float in [-1, +1]):\n"
            "  sign — positive weights mean source and target move in the "
            "       same direction; negative weights mean opposite directions.\n"
            "  magnitude — |w| encodes relative strength of influence "
            "       compared with other edges in the same model: |w|≈1.0 is "
            "       a strong, dominant driver; ≈0.5 is a moderate driver; "
            "       ≈0.25 is a weak but non-negligible driver. Magnitudes "
            "       are RELATIVE, not absolute — calibrate against the other "
            "       edges in the supplied edge list.\n"
            "  zero — use 0.0 only when you are confident the literature "
            "       finds no effect; for genuinely uncertain edges, use a "
            "       small magnitude with confidence='low' rather than 0.0.\n\n"
            "COHERENCE WITH EDGE DESCRIPTION — when an edge already has an "
            "'edge description' line, the description is the authoritative "
            "statement of the mechanism. Your polarity rationale MUST tell "
            "the same causal story as the description. If you believe the "
            "description's causal direction is wrong, do NOT silently invert "
            "the polarity. Instead, propose the polarity that matches the "
            "description, set confidence='low', and explain the disagreement "
            "in the rationale so a human reviewer can correct the description "
            "and the polarity together.\n\n"
            "For each edge, return: edge_id, value ('+', '-', or '~' for "
            "CLD; a float in [-1,+1] for FCM), rationale, and confidence "
            "(high/medium/low)."
        ),
        output_hint="An AttributeSuggestionsResult with a list of AttributeSuggestion items.",
        scope=PromptScope.model,
        intent=PromptIntent.insight,
    ),
}
