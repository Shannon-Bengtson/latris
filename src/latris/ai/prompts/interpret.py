"""The interpretation prompts, one for each report section."""

from __future__ import annotations

from latris.ai.prompts._spec import PromptIntent, PromptScope, PromptSpec
from latris.ai.prompts.inputs import InterpretSectionInputs

PROMPTS: dict[str, PromptSpec] = {
    # ── Interpretation prompts ──────────────────────────────────────────
    "InterpretStructuralSummary": PromptSpec(
        name="InterpretStructuralSummary",
        title="Interpret structural summary",
        description="Synthesise structural analysis findings into a technical narrative.",
        inputs=InterpretSectionInputs,
        template=(
            "You are interpreting the structural analysis results of a {model_type} model. "
            "The claims below summarise what the analysis found. Write a concise technical "
            "narrative (2–4 paragraphs) that explains the structural properties, key "
            "topological features, and their significance."
        ),
        output_hint="An InterpretProseResult with technical prose.",
        scope=PromptScope.model,
        intent=PromptIntent.insight,
    ),
    "InterpretKeyFindings": PromptSpec(
        name="InterpretKeyFindings",
        title="Interpret key findings",
        description="Rank and explain the most important findings from analysis.",
        inputs=InterpretSectionInputs,
        template=(
            "You are interpreting the key findings from a {model_type} model analysis. "
            "The claims below are the highest-priority findings. Write a technical summary "
            "(2–4 paragraphs) explaining why these findings matter, how they relate to "
            "each other, and what patterns they reveal."
        ),
        output_hint="An InterpretProseResult with technical prose.",
        scope=PromptScope.model,
        intent=PromptIntent.insight,
    ),
    "InterpretSensitivity": PromptSpec(
        name="InterpretSensitivity",
        title="Interpret sensitivity",
        description="Explain what drives model sensitivity and robustness.",
        inputs=InterpretSectionInputs,
        template=(
            "You are interpreting sensitivity and robustness results for a "
            "{model_type} model. The claims summarise which elements or "
            "parameters (whichever the active formalism supplies — e.g. "
            "leverage points, loop members, or edge polarities for CLD; "
            "edge weights for FCM; arc-strength priors for DAG) have the "
            "greatest influence on the conclusions. Write a technical "
            "explanation (2–4 paragraphs) of what drives sensitivity, "
            "which results are robust to structural changes, and which are "
            "fragile. Where the model has no numeric parameters, frame "
            "sensitivity in terms of which structural choices most change "
            "the qualitative result."
        ),
        output_hint="An InterpretProseResult with technical prose.",
        scope=PromptScope.model,
        intent=PromptIntent.insight,
    ),
    "InterpretAssumptions": PromptSpec(
        name="InterpretAssumptions",
        title="Interpret assumptions & limitations",
        description="Explain how assumptions constrain interpretation of results.",
        inputs=InterpretSectionInputs,
        template=(
            "You are documenting the assumptions and limitations of a {model_type} model. "
            "The claims list the stated assumptions and diagnostic findings. Write a "
            "technical assessment (2–4 paragraphs) explaining how these assumptions "
            "constrain interpretation, what would change if assumptions were violated, "
            "and known limitations of the modelling approach."
        ),
        output_hint="An InterpretProseResult with technical prose.",
        scope=PromptScope.model,
        intent=PromptIntent.insight,
    ),
    "InterpretEvidenceGaps": PromptSpec(
        name="InterpretEvidenceGaps",
        title="Interpret evidence gaps",
        description="Explain where the evidence base is thin and what that means.",
        inputs=InterpretSectionInputs,
        template=(
            "You are assessing evidence gaps in a {model_type} model. The claims "
            "summarise coverage statistics and uncited elements. Write a technical "
            "assessment (2–3 paragraphs) explaining where the evidence base is thin, "
            "what risk that poses to interpretation, and what evidence collection "
            "would most strengthen the model."
        ),
        output_hint="An InterpretProseResult with technical prose.",
        scope=PromptScope.model,
        intent=PromptIntent.insight,
    ),
    "InterpretEvidenceCoverage": PromptSpec(
        name="InterpretEvidenceCoverage",
        title="Interpret evidence coverage",
        description="Audit cross-references between model elements and cited sources.",
        inputs=InterpretSectionInputs,
        template=(
            "You are auditing evidence coverage for a {model_type} model. The claims "
            "summarise which elements lack evidence and which references are unused. "
            "Write a technical assessment (2–3 paragraphs) identifying coverage gaps, "
            "explaining what risk they pose, and prioritising which elements most "
            "urgently need evidence support. When the claims distinguish verified-"
            "supporting links from unverified or proposed links, treat only the "
            "verified-supporting figure as evidence-backed coverage; unverified links "
            "are proposals that still need source-reading to substantiate."
        ),
        output_hint="An InterpretProseResult with technical prose.",
        scope=PromptScope.model,
        intent=PromptIntent.insight,
    ),
    "InterpretAnswer": PromptSpec(
        name="InterpretAnswer",
        title="Answer the modelling question",
        description="Synthesise analysis results into an answer to the project's modelling question.",
        inputs=InterpretSectionInputs,
        template=(
            "You are answering the project's modelling question using analysis results "
            "from a {model_type} model. The first claim states the question; subsequent "
            "claims are the inference findings. Write a clear, evidence-grounded answer "
            "(3–5 paragraphs). Reference specific model elements and findings. "
            "Acknowledge uncertainty where it exists."
        ),
        output_hint="An InterpretProseResult with stakeholder-facing prose.",
        scope=PromptScope.model,
        intent=PromptIntent.insight,
    ),
    "InterpretImplications": PromptSpec(
        name="InterpretImplications",
        title="Interpret implications",
        description="Explain what the results mean for decisions and interventions.",
        inputs=InterpretSectionInputs,
        template=(
            "You are explaining the practical implications of a {model_type} model's "
            "findings. The claims summarise recommended interventions and actions. "
            "Write a clear explanation (2–4 paragraphs) about what should be done, "
            "where to intervene, and what outcomes to expect. "
            "Be specific about mechanisms — explain why interventions work."
        ),
        output_hint="An InterpretProseResult with stakeholder-facing prose.",
        scope=PromptScope.model,
        intent=PromptIntent.insight,
    ),
    "InterpretConfidence": PromptSpec(
        name="InterpretConfidence",
        title="Assess confidence",
        description="Explain how much stakeholders should trust the results.",
        inputs=InterpretSectionInputs,
        template=(
            "You are writing a confidence assessment for a {model_type} model's results. "
            "The claims summarise evidence coverage and finding maturity. Write a balanced "
            "assessment (2–3 paragraphs) explaining how much confidence "
            "stakeholders should place in the results, what strengthens confidence, and "
            "what caveats apply. Be honest about limitations without being dismissive. "
            "When the claims distinguish verified-supporting coverage from "
            "unverified/proposed coverage, lead with the verified figure — an "
            "unverified link is a proposal, not evidence, and conflating the two "
            "inflates apparent rigour. If verified coverage is low, say so plainly."
        ),
        output_hint="An InterpretProseResult with stakeholder-facing prose.",
        scope=PromptScope.model,
        intent=PromptIntent.insight,
    ),
    "InterpretOpenQuestions": PromptSpec(
        name="InterpretOpenQuestions",
        title="Interpret open questions",
        description="Synthesise unresolved questions into a prioritised next-steps narrative.",
        inputs=InterpretSectionInputs,
        template=(
            "You are summarising open questions and next steps for a {model_type} model. "
            "The claims list unresolved questions and diagnostic issues. Write a clear "
            "summary (2–3 paragraphs) that prioritises what "
            "needs attention, distinguishes critical unknowns from nice-to-haves, and "
            "suggests concrete next steps for further investigation."
        ),
        output_hint="An InterpretProseResult with stakeholder-facing prose.",
        scope=PromptScope.model,
        intent=PromptIntent.insight,
    ),
}
