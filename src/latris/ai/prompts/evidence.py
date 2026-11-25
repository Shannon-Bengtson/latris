"""Prompts that look for evidence: foundational references, and the gaps in what is cited."""

from __future__ import annotations

from latris.ai.prompts._guidance import _EXISTENCE_ATTRIBUTE_DEFAULT_NOTE, _NO_FABRICATION_GUIDANCE
from latris.ai.prompts._spec import PromptIntent, PromptScope, PromptSpec
from latris.ai.prompts.inputs import FindFoundationalReferencesInputs, ScanEvidenceGapsInputs
from latris.schema.interpretation import INTERPRET_SECTION_IDS

PROMPTS: dict[str, PromptSpec] = {
    "FindFoundationalReferences": PromptSpec(
        name="FindFoundationalReferences",
        title="Find foundational references",
        description=(
            "Search for foundational/seminal references for the project topic "
            "without using the current model state. Use this when starting a "
            "literature base from scratch."
        ),
        inputs=FindFoundationalReferencesInputs,
        template=(
            "Find foundational, seminal, or canonical references on the "
            "topic, suitable for anchoring a fresh literature base. "
            "Focus area (optional): {focus_area}\n"
            "Do NOT bias toward the current substrate — propose breadth, "
            "not gap-filling. Return 3-6 search queries with rationales.\n\n"
            + _NO_FABRICATION_GUIDANCE
        ),
        output_hint="A BibliographySearchPlan with 3-6 broad search queries.",
        scope=PromptScope.model,
        intent=PromptIntent.action,
    ),
    "ScanEvidenceGaps": PromptSpec(
        name="ScanEvidenceGaps",
        title="Scan model for evidence gaps",
        description=(
            "Sweep the model and identify missing or weak evidence. Each gap "
            "is parked as an OpenQuestion record so it's tracked through "
            "the normal discharge workflow. Optional pattern-matched "
            "evidence-link suggestions close gaps where existing references "
            "in the library plausibly support specific elements."
        ),
        inputs=ScanEvidenceGapsInputs,
        template=(
            "You are auditing a {model_type} model for evidence completeness. "
            "Across all interpretation sections (" + ", ".join(INTERPRET_SECTION_IDS) + "), identify specific "
            "claims that lack evidence, references that are stale or weakly "
            "linked, and assumptions that have not been challenged.\n\n"
            "Return an EvidenceGapsScanResult with:\n"
            "  - gaps: each tagged with section_type, claim, gap_description, "
            "    suggested_action, severity (low|medium|high). Default "
            "    record_as_questions=True parks each gap as an OpenQuestion "
            "    so reviewers can discharge it.\n"
            "  - summary: one-paragraph overview of the model's evidence "
            "    health.\n"
            "  - suggested_evidence_links: OPTIONAL. When you can match a "
            "    reference already in the library (by bibkey) to a "
            "    specific uncited element with high confidence, propose the "
            "    link here. "
            + _EXISTENCE_ATTRIBUTE_DEFAULT_NOTE +
            " DO NOT propose links to references that aren't in the library."
        ),
        output_hint="A gap inventory + bounded provenance: questions per gap, optional evidence-link closures.",
        scope=PromptScope.model,
        intent=PromptIntent.action,
    ),
}
