"""Prompts that propose provenance records: assumptions, decisions, exclusions, questions."""

from __future__ import annotations

from latris.ai.prompts._spec import PromptIntent, PromptScope, PromptSpec
from latris.ai.prompts.inputs import (
    GenerateAssumptionsInputs,
    RaiseQuestionsInputs,
    SuggestDecisionsInputs,
    SuggestExclusionsInputs,
)

PROMPTS: dict[str, PromptSpec] = {
    "GenerateAssumptions": PromptSpec(
        name="GenerateAssumptions",
        title="Generate assumptions",
        description="Generate assumptions underlying a model element.",
        inputs=GenerateAssumptionsInputs,
        template=(
            "Identify the key assumptions underlying {target_id}. "
            "Focus on: why this element exists, what must be true for it "
            "to hold, and what simplifications have been made. "
            "Produce 2–5 specific, falsifiable assumption statements."
        ),
        output_hint="An AssumptionsProposal with target_id and a list of assumptions.",
        scope=PromptScope.element,
        intent=PromptIntent.action,
    ),
    "SuggestDecisions": PromptSpec(
        name="SuggestDecisions",
        title="Suggest decisions",
        description="Document modelling choices made for a model element.",
        inputs=SuggestDecisionsInputs,
        template=(
            "Identify the key modelling decisions embedded in {target_id}. "
            "Focus on: why this representation was chosen over alternatives, "
            "what trade-offs were accepted, and what scope boundaries apply. "
            "Produce 1–4 decision statements with rationales."
        ),
        output_hint="A DecisionsProposal with target_id and a list of decisions.",
        scope=PromptScope.element,
        intent=PromptIntent.action,
    ),
    "SuggestExclusions": PromptSpec(
        name="SuggestExclusions",
        title="Suggest exclusions",
        description="Propose scope boundaries and negative claims for the model.",
        inputs=SuggestExclusionsInputs,
        template=(
            "Analyse the current model and identify what is intentionally "
            "excluded from scope. Focus on: adjacent phenomena not modelled, "
            "temporal/spatial boundaries, simplifications that omit complexity, "
            "and validity limits. Produce 2–5 exclusion statements."
        ),
        output_hint="An ExclusionsProposal with a list of exclusions.",
        scope=PromptScope.model,
        intent=PromptIntent.action,
    ),
    "RaiseQuestions": PromptSpec(
        name="RaiseQuestions",
        title="Raise questions",
        description="Surface open questions about a model element.",
        inputs=RaiseQuestionsInputs,
        template=(
            "Identify unresolved structural questions about {target_id}. "
            "Focus on: uncertain mechanisms, missing evidence, contested "
            "relationships, and areas where expert input is needed. "
            "Produce 2–5 specific, actionable questions.\n\n"
            "Do NOT emit questions about your own prompting, source-tier "
            "availability, grounding instructions, or how to handle empty "
            "extracts. Those are tooling concerns, not model concerns, and "
            "do not belong in the project's open questions. Every question "
            "you emit must be one a domain expert reviewer could discharge "
            "by investigating the substantive subject matter."
        ),
        output_hint="A QuestionsProposal with target_id and a list of questions.",
        scope=PromptScope.element,
        intent=PromptIntent.action,
    ),
}
