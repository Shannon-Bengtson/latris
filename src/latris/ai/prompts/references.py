"""Reference management prompts: expand, cross-check and summarise the library."""

from __future__ import annotations

from latris.ai.prompts._guidance import _EXISTENCE_ATTRIBUTE_DEFAULT_NOTE
from latris.ai.prompts._spec import PromptIntent, PromptScope, PromptSpec
from latris.ai.prompts.inputs import CrossReferenceCheckInputs, ExpandBibliographyInputs, SummarizeReferenceInputs

PROMPTS: dict[str, PromptSpec] = {
    "ExpandBibliography": PromptSpec(
        name="ExpandBibliography",
        title="Expand bibliography",
        description="Suggest new references to strengthen the model's evidence base. "
        "Uses Semantic Scholar to find real papers.",
        inputs=ExpandBibliographyInputs,
        template=(
            "Analyse the current model's entities, edges, and existing references. "
            "Identify the most critical evidence gaps. Focus: {focus_area}. "
            "Propose 3–8 references that would most strengthen the model's "
            "defensibility. For each, provide a bibkey, title, authors, year, "
            "and a URL (REQUIRED — a direct link to the paper, report, or "
            "resource so the user can verify it exists). Prefer URLs from "
            "publisher sites, government agencies, or institutional repositories. "
            "DOI is optional bonus. Do NOT fabricate references or URLs."
        ),
        output_hint="An ExpandBibliographyProposal with new_references.",
        scope=PromptScope.model,
        intent=PromptIntent.action,
    ),
    "CrossReferenceCheck": PromptSpec(
        name="CrossReferenceCheck",
        title="Cross-reference check",
        description="Audit evidence coverage and propose pattern-matched evidence-link closures.",
        inputs=CrossReferenceCheckInputs,
        template=(
            "Audit the model's evidence coverage. For each entity and edge, "
            "check whether its key attributes (description, polarity, confidence) "
            "have evidence links. List uncited elements and unused references. "
            "Provide a brief coverage summary with prioritised recommendations.\n\n"
            "When you can match an existing reference (by bibkey) to a "
            "currently-uncited element with high confidence, populate "
            "suggested_links with EvidenceLinkSuggestion entries. Each link "
            "must use a bibkey already in the project's reference library — "
            "DO NOT propose links to references that don't exist. "
            + _EXISTENCE_ATTRIBUTE_DEFAULT_NOTE + " "
            "Keep suggestions bounded — high-confidence pairs only, not "
            "exhaustive. The coverage prose is the primary output; links "
            "are a bonus closure."
        ),
        output_hint="A coverage audit + pattern-matched evidence-link suggestions (apply via add_evidence).",
        scope=PromptScope.model,
        intent=PromptIntent.action,
    ),
    "SummarizeReference": PromptSpec(
        name="SummarizeReference",
        title="Summarize reference",
        description="Summarize a reference's relevance to the current model.",
        inputs=SummarizeReferenceInputs,
        template=(
            "Summarize reference {bibkey} and assess its relevance to the "
            "current model. Write 2-3 short paragraphs covering:\n"
            "  - relevance: what the reference is about and how it bears on "
            "    the project's modelling question and substrate.\n"
            "  - supported elements: which existing entities, edges, or "
            "    attributes the reference plausibly supports (cite by label). "
            "    Distinguish elements it directly addresses from elements it "
            "    only topically overlaps with.\n"
            "  - gaps it could fill: uncited elements or open questions in "
            "    the model that this reference would help close.\n"
            "  - currency: whether the reference is still current, superseded, "
            "    or domain-stable, with a one-line justification.\n\n"
            "Ground the summary in what the supplied reference metadata and "
            "source-snapshot (if present) actually say. Do not speculate "
            "beyond the supplied extract."
        ),
        output_hint="A ReferenceRelevanceResult with relevance_summary and connected_elements.",
        scope=PromptScope.element,
        intent=PromptIntent.insight,
    ),
}
