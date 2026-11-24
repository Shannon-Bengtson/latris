"""Compose prompts: extract variables and claims from evidence, suggest variables and connections."""

from __future__ import annotations

from latris.ai.prompts._guidance import (
    _EDGE_MECHANISM_GUIDANCE,
    _LOOP_CLOSURE_GUIDANCE,
    _MECHANISTIC_GRANULARITY_GUIDANCE,
    _NO_FABRICATION_GUIDANCE,
    _NODE_FEWSHOT,
    _NODE_KIND_RUBRIC,
    _SCOPE_CONTRACT_GUIDANCE,
)
from latris.ai.prompts._spec import PromptIntent, PromptScope, PromptSpec
from latris.ai.prompts.inputs import (
    ExtractCausalClaimsInputs,
    ExtractVariablesFromEvidenceInputs,
    SuggestConnectionsInputs,
    SuggestVariablesInputs,
)

PROMPTS: dict[str, PromptSpec] = {
    # ── Compose extraction prompts ────────────────────────────────────
    "ExtractVariablesFromEvidence": PromptSpec(
        name="ExtractVariablesFromEvidence",
        title="Extract variables from evidence",
        description="Identify key variables and concepts mentioned across references in the evidence base.",
        inputs=ExtractVariablesFromEvidenceInputs,
        template=(
            "You are extracting variables from the project's reference library. "
            "For each variable, return a label (concise name), an entity kind, "
            "a short description, and the bibkey(s) where it appears. "
            "Exclude variables that already exist in the substrate.\n"
            "Entity kind MUST be exactly one of: concept, variable, event, "
            "actor, state, decision, hazard. Do not invent other kinds. "
            "Map CLD-style roles (driver, lever, outcome, stock) to "
            "'variable' for measurable quantities or 'concept' for abstract "
            "drivers.\n"
            + _SCOPE_CONTRACT_GUIDANCE + "\n\n"
            + _MECHANISTIC_GRANULARITY_GUIDANCE + "\n\n"
            + _NODE_KIND_RUBRIC + "\n\n"
            + _NODE_FEWSHOT + "\n\n"
            + _NO_FABRICATION_GUIDANCE
        ),
        output_hint="An ExtractedVariablesResult with a list of ExtractedVariable items.",
        scope=PromptScope.model,
        intent=PromptIntent.insight,
    ),
    "ExtractCausalClaims": PromptSpec(
        name="ExtractCausalClaims",
        title="Extract causal claims from evidence",
        description="Identify causal relationships stated or implied in references, between the accepted node set.",
        inputs=ExtractCausalClaimsInputs,
        template=(
            "You are extracting causal claims from the project's reference library. "
            "Focus on relationships between the given node labels. "
            "For each claim, return from_label, to_label, edge kind "
            "(causal, temporal, association), a description (one sentence "
            "stating the mechanism this edge represents — what the connection "
            "means in the system), a rationale (why you extracted this claim "
            "from the evidence), the bibkey(s), and the supporting quote or "
            "claim text from the reference. Description and rationale are "
            "distinct: description explains the mechanism; rationale explains "
            "the extraction decision.\n\n"
            + _SCOPE_CONTRACT_GUIDANCE + "\n\n"
            + _EDGE_MECHANISM_GUIDANCE + "\n\n"
            + _NO_FABRICATION_GUIDANCE
        ),
        output_hint="An ExtractedClaimsResult with a list of ExtractedClaim items.",
        scope=PromptScope.model,
        intent=PromptIntent.insight,
    ),
    "SuggestVariables": PromptSpec(
        name="SuggestVariables",
        title="Suggest missing variables",
        description="Given the modelling question and existing structure, "
        "suggest important variables that are missing.",
        inputs=SuggestVariablesInputs,
        template=(
            "You are helping build a conceptual model. Given the modelling question "
            "and the existing/accepted nodes, suggest additional variables or concepts "
            "that are likely important but not yet included. "
            "For each, provide a label, kind, description, and rationale for inclusion.\n"
            "Entity kind MUST be exactly one of: concept, variable, event, "
            "actor, state, decision, hazard. Do not invent other kinds. "
            "Map CLD-style roles (driver, lever, outcome, stock) to "
            "'variable' for measurable quantities or 'concept' for abstract "
            "drivers.\n"
            + _SCOPE_CONTRACT_GUIDANCE + "\n\n"
            + _MECHANISTIC_GRANULARITY_GUIDANCE + "\n\n"
            + _NODE_KIND_RUBRIC + "\n\n"
            + _NODE_FEWSHOT + "\n\n"
            + _NO_FABRICATION_GUIDANCE
        ),
        output_hint="A SuggestedVariablesResult with a list of SuggestedVariable items.",
        scope=PromptScope.model,
        intent=PromptIntent.insight,
    ),
    "SuggestConnections": PromptSpec(
        name="SuggestConnections",
        title="Suggest missing connections",
        description="Given accepted nodes and evidence, suggest plausible connections that should exist between them.",
        inputs=SuggestConnectionsInputs,
        template=(
            "You are helping build a conceptual model. This is the "
            "*Compose-phase* connection suggester: nodes have been accepted "
            "into the substrate but the edge set is still being built up "
            "from evidence. (Contrast with FindNewConnections, which runs "
            "during interrogation on a more-mature model and focuses on "
            "load-bearing omissions.)\n\n"
            "Given the accepted nodes and any available evidence, suggest "
            "plausible causal or associative connections between them. "
            "Propose 3-8 high-value candidates — not an exhaustive pairwise "
            "sweep. For each, provide from_label, to_label, kind, a "
            "description (one sentence stating what this connection means — "
            "the mechanism in the system), a rationale (why you are "
            "suggesting this connection), and a confidence level. "
            "Description and rationale are distinct: description explains "
            "the mechanism; rationale explains the suggestion.\n\n"
            + _SCOPE_CONTRACT_GUIDANCE + "\n\n"
            + _EDGE_MECHANISM_GUIDANCE + "\n\n"
            + _LOOP_CLOSURE_GUIDANCE + "\n\n"
            + _NO_FABRICATION_GUIDANCE + "\n\n"
            "DECISION VARIABLE — the entity whose label most closely matches "
            "the project's modelling question is the *decision variable under "
            "study*. It is exogenous by construction. Do NOT propose "
            "`decision_rule` or `governance` edges that point TO this variable; "
            "such edges make the policy endogenous in its own analysis and "
            "inflate the apparent strength of reinforcing loops."
        ),
        output_hint="A SuggestedConnectionsResult with a list of SuggestedConnection items.",
        scope=PromptScope.model,
        intent=PromptIntent.insight,
    ),
}
