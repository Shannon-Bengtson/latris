"""Reference management proposals and results: search plans, bibliography, cross-reference checks, evidence gaps."""

from __future__ import annotations

from pydantic import Field

from latris.ai.proposals._shared import CitationSuggestion, _Base
from latris.operations.evidence import add_evidence
from latris.operations.provenance import add_question
from latris.operations.references import add_reference, list_references
from latris.repo.layout import ProjectPaths
from latris.schema.interpretation import InterpretSectionId


class SearchQuery(_Base):
    """A targeted search query for finding relevant literature."""

    query: str = Field(..., description="Search keywords for Semantic Scholar.")
    rationale: str = Field("", description="Why this search would strengthen the model.")


class BibliographySearchPlan(_Base):
    """ExpandBibliography LLM output — search queries, not full references.

    The server takes these queries, searches Semantic Scholar, and builds
    the actual ExpandBibliographyProposal from real results.
    """

    queries: list[SearchQuery] = Field(default_factory=list)


class ExpandBibliographyProposal(_Base):
    """ExpandBibliography output.  Proposed new references to add to the library."""

    new_references: list[CitationSuggestion] = Field(default_factory=list)

    def apply(self, paths: ProjectPaths) -> list[str]:
        known_bibkeys = {r.bibkey for r in list_references(paths.root)}
        created: list[str] = []
        for ref in self.new_references:
            if ref.bibkey in known_bibkeys:
                continue
            added, _ = add_reference(
                ref.bibkey,
                ref.title,
                authors=ref.authors,
                year=ref.year,
                doi=ref.doi,
                url=ref.url,
                root=paths.root,
            )
            created.append(added.bibkey)
            known_bibkeys.add(added.bibkey)
        return created


class UncitedElement(_Base):
    """An element that lacks evidence links."""

    element_id: str = Field(..., description="Node or edge ID.")
    label: str = Field("", description="Human-readable label.")
    attributes_without_evidence: list[str] = Field(
        default_factory=list,
        description="Attributes on this element with no citations.",
    )


class EvidenceLinkSuggestion(_Base):
    """A pattern-matched suggestion that an existing reference supports a
    specific (target, attribute) pair. Used by hybrid adversarial prompts
    that surface evidence-coverage gaps and propose closures."""

    target_id: str = Field(..., description="Entity or edge ID receiving the link.")
    attribute: str = Field(
        "existence",
        description=(
            "Attribute being supported. Default 'existence' means the "
            "reference supports the entity/edge as a whole. Other valid "
            "values include 'description', 'polarity', 'confidence', etc."
        ),
    )
    bibkey: str = Field(..., description="Bibkey of an existing reference in the library.")
    rationale: str = Field(
        "",
        description="One-line note on why this reference supports the target.",
    )


class CrossReferenceCheckResult(_Base):
    """CrossReferenceCheck output — hybrid prose + bounded mutation.

    The prose (``coverage_summary``, ``uncited_elements``,
    ``unused_references``) renders into the report. The structured
    ``suggested_links`` are evidence-link proposals that pair existing
    references in the library with currently-uncited elements; each is
    committed via ``add_evidence``.

    Bounded-mutation principle: only suggest links the AI has high
    confidence about. The audit prose is the deliverable; mutations are
    a bonus closure, not the main output.
    """

    uncited_elements: list[UncitedElement] = Field(default_factory=list)
    unused_references: list[str] = Field(
        default_factory=list,
        description="Bibkeys of references not cited by any element.",
    )
    coverage_summary: str = Field("", description="Overall evidence coverage assessment.")
    suggested_links: list[EvidenceLinkSuggestion] = Field(
        default_factory=list,
        description=(
            "Optional pattern-matched evidence-link suggestions: pairs "
            "of (existing reference bibkey, uncited element) where the "
            "AI judges the link plausible. Committed via add_evidence."
        ),
    )

    def apply(self, paths: ProjectPaths) -> list[str]:
        created: list[str] = []
        for link in self.suggested_links:
            entry, _ = add_evidence(
                link.target_id,
                link.attribute,
                link.bibkey,
                verified_by="ai",
                notes=link.rationale or None,
                root=paths.root,
            )
            descriptor = f"evidence:{link.bibkey}->{link.target_id}/{link.attribute}"
            created.append(descriptor)
        return created


class ReferenceRelevanceResult(_Base):
    """SummarizeReference output. Read-only — relevance of one reference to the model."""

    bibkey: str = Field(..., description="The reference being summarized.")
    relevance_summary: str = Field(..., description="How this reference relates to the model.")
    connected_elements: list[str] = Field(
        default_factory=list,
        description="Element labels that this reference supports or could support.",
    )


class EvidenceGap(_Base):
    """A single evidence gap detected by ScanEvidenceGaps."""

    section_type: InterpretSectionId = Field(
        ..., description="Interpret section the gap belongs to.",
    )
    claim: str = Field(
        "",
        description="The specific claim, assumption, or finding the gap concerns.",
    )
    gap_description: str = Field(
        ..., description="What evidence is missing or weak."
    )
    suggested_action: str = Field(
        "",
        description=(
            "Concrete next step — e.g. 'search for studies on X', "
            "'add expert elicitation', 'validate against dataset Y'."
        ),
    )
    severity: str = Field(
        "medium", description="low | medium | high — for sorting/filtering in the GUI."
    )


class EvidenceGapsScanResult(_Base):
    """ScanEvidenceGaps output — hybrid prose + bounded mutation.

    The prose (``summary``, gap descriptions) renders into the report.
    ``apply()`` logs each gap as an ``OpenQuestion`` so it's tracked,
    and applies any AI-pattern-matched ``EvidenceLink`` suggestions
    to attach existing references to specific elements.

    Note: evidence-link suggestions only apply when the AI identifies a
    plausible reference *already in the library* that supports a
    specific (target, attribute). The AI cannot fabricate references
    here — those go through SuggestCitations.
    """

    gaps: list[EvidenceGap] = Field(default_factory=list)
    summary: str = Field(
        "",
        description="One-paragraph overview of the model's evidence health.",
    )
    record_as_questions: bool = Field(
        True,
        description="Whether to log each gap as an OpenQuestion record.",
    )
    suggested_evidence_links: list[EvidenceLinkSuggestion] = Field(
        default_factory=list,
        description=(
            "Optional: when the AI can match an existing reference "
            "(by bibkey) to an uncited element, suggest the link here. "
            "Each link is committed via add_evidence."
        ),
    )

    def apply(self, paths: ProjectPaths) -> list[str]:
        created: list[str] = []
        if self.record_as_questions:
            for gap in self.gaps:
                qtext = (
                    f"[evidence/{gap.severity}] {gap.gap_description}"
                    + (f" — Suggested: {gap.suggested_action}" if gap.suggested_action else "")
                )
                entry, _ = add_question(
                    qtext,
                    root=paths.root,
                )
                created.append(entry.id)
        for link in self.suggested_evidence_links:
            entry, _ = add_evidence(
                link.target_id,
                link.attribute,
                link.bibkey,
                verified_by="ai",
                notes=link.rationale or None,
                root=paths.root,
            )
            # add_evidence returns (EvidenceLink, sha) but the link itself
            # has no id; use bibkey+target_id+attribute as the descriptor.
            descriptor = f"evidence:{link.bibkey}->{link.target_id}/{link.attribute}"
            created.append(descriptor)
        return created
