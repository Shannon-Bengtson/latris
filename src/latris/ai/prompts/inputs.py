"""The input schema of each prompt."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from latris.ai.prompts._spec import ModelTypeStr, PackName, ViewKind


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


# ---------- Input schemas ----------


class DraftConceptualModelInputs(_In):
    focus: str = Field(..., description="Phenomenon or question to draft the model around.")
    reference_bibkeys: list[str] = Field(
        default_factory=list,
        description="References the assistant should ground the draft in.",
    )
    candidate_count: int = Field(3, ge=1, le=5, description="How many framings to generate.")


class RunElicitationInterviewInputs(_In):
    topic: str = Field(..., description="Area of the model under elicitation.")
    prior_turns: list[str] = Field(
        default_factory=list,
        description="Previous interview turns, most-recent last.",
    )


class FindNewConnectionsInputs(_In):
    focus_node_ids: list[str] = Field(
        default_factory=list,
        description="Restrict the search to edges touching these nodes.",
    )


class ProjectToFormalViewInputs(_In):
    view: ViewKind = Field(..., description="Target view: cld | dag.")


class ChallengeThisConnectionInputs(_In):
    target_id: str = Field(..., description="Edge ID (or node ID) to challenge.")
    target_attribute: str | None = Field(
        None,
        description="Specific attribute under challenge (e.g. 'polarity').",
    )


class AttackThisModelInputs(_In):
    scope_node_ids: list[str] = Field(
        default_factory=list,
        description="Optional subset of nodes to focus adversarial pressure on.",
    )


class FindCounterPathwayInputs(_In):
    model_type: ModelTypeStr = Field(
        "cld",
        description="Active model type — selects framing language for the attack.",
    )
    scope_node_ids: list[str] = Field(
        default_factory=list,
        description="Optional subset of nodes to focus the structural attack on.",
    )


class SteelmanOpposingViewInputs(_In):
    target_id: str = Field(..., description="The element whose opposing framing we want.")


class SyntheticPeerReviewInputs(_In):
    reviewer_role: str = Field(
        "domain expert",
        description="Persona the reviewer should adopt (e.g. 'statistician', 'policy lead').",
    )


class IdentifyResearchGapsInputs(_In):
    pass  # operates over the whole current model


class ScopeCheckInputs(_In):
    pass  # tests whether current substrate meets the foundation question/decision


class SuggestCitationsInputs(_In):
    target_id: str = Field(..., description="Element lacking evidence.")
    target_attribute: str = Field(..., description="Attribute that needs citation.")


class ExplainThisElementInputs(_In):
    target_id: str = Field(..., description="Element to explain.")


class GeneratePackInputs(_In):
    pack: PackName = Field(..., description="client | audit | review | workshop | publication")


class ExpandBibliographyInputs(_In):
    focus_area: str = Field("", description="Optional focus area for bibliography expansion.")


class CrossReferenceCheckInputs(_In):
    pass  # operates over the whole model


class SummarizeReferenceInputs(_In):
    bibkey: str = Field(..., description="Bibkey of the reference to summarize.")


class GenerateAssumptionsInputs(_In):
    target_id: str = Field(..., description="Element to generate assumptions for.")


class SuggestDecisionsInputs(_In):
    target_id: str = Field(..., description="Element the decision pertains to.")


class SuggestExclusionsInputs(_In):
    pass  # model-level — operates over entire model


class RaiseQuestionsInputs(_In):
    target_id: str = Field(..., description="Element to raise questions about.")


class InterpretSectionInputs(_In):
    section_type: str = Field(..., description="Interpretation section type ID.")
    model_type: ModelTypeStr = Field(..., description="Model type being interpreted (cld, dag, fcm).")
    claims: list[str] = Field(default_factory=list, description="Template-generated claims for context.")


class ExtractVariablesFromEvidenceInputs(_In):
    reference_bibkeys: list[str] = Field(
        default_factory=list,
        description="References to extract from (empty = all).",
    )


class ExtractCausalClaimsInputs(_In):
    node_labels: list[str] = Field(
        default_factory=list,
        description="Accepted node labels to find claims between.",
    )
    reference_bibkeys: list[str] = Field(
        default_factory=list,
        description="References to extract from (empty = all).",
    )


class SuggestVariablesInputs(_In):
    focus: str = Field("", description="Optional focus area for suggestions.")
    exclude_labels: list[str] = Field(default_factory=list, description="Labels to exclude (already accepted).")


class SuggestConnectionsInputs(_In):
    node_labels: list[str] = Field(
        default_factory=list,
        description="Accepted node labels to suggest connections between.",
    )
    focus: str = Field("", description="Optional focus area.")


class SuggestEdgePolaritiesInputs(_In):
    model_type: ModelTypeStr = Field("cld", description="Model type (cld or fcm).")
    edges: list[dict] = Field(
        default_factory=list,
        description="Edges to suggest polarities for: [{edge_id, from_label, to_label}].",
    )


class RecommendApproachInputs(_In):
    candidates: list[dict] = Field(
        default_factory=list,
        description="Available stable formalisms: [{id, name, best_for}].",
    )
    evidence_summary: str = Field(
        "",
        description="Brief summary of available evidence (datasets, references, model size).",
    )


class FillProvenanceFieldInputs(_In):
    target_kind: str = Field(
        ..., description="One of: 'project', 'entity', 'edge'."
    )
    target_id: str = Field(
        "",
        description="ID of the entity/edge. Empty string for project-level fields.",
    )
    field_path: str = Field(
        ...,
        description=(
            "Dotted path of the field to fill. Examples: 'description', "
            "'background', 'boundary', 'assumption.rationale', "
            "'citation.notes', 'challenge.argument'."
        ),
    )
    row_id: str = Field(
        "",
        description="Provenance row ID (assumption/citation/etc) when filling a per-row field.",
    )
    current_value: str = Field(
        "",
        description="The field's current value, so the AI can refine rather than overwrite.",
    )


class FindFoundationalReferencesInputs(_In):
    focus_area: str = Field(
        "",
        description=(
            "Optional topic or focus to bias the search. If empty, the AI uses "
            "the project's modelling question and background as the topic."
        ),
    )


class ScanEvidenceGapsInputs(_In):
    model_type: ModelTypeStr = Field(
        "cld",
        description="Active model type — gap detection is shaped by the formalism.",
    )


class VerifyClaimAgainstSourceInputs(_In):
    """Input shape for AI interrogation Phase 4a VerifyClaimAgainstSource.

    Element-scope: given an evidence link by (target_id, attribute,
    bibkey) and the claim text the link is supposed to support, the
    AI returns a verdict and (on `supports`) a verbatim quote drawn
    from the Reference's source_snapshot extract.
    """

    target_id: str | None = Field(
        None,
        description="Element the link is attached to (None for model-level).",
    )
    attribute: str = Field(..., description="Attribute the link claims to support.")
    bibkey: str = Field(..., description="Reference bibkey.")
    claim: str = Field(
        ...,
        description="The specific claim being verified — passed in by the GUI / orchestrator.",
    )


class ChallengeEdgeInputs(_In):
    """Input shape for AI interrogation Phase 3b ChallengeEdge.

    Element-scope adversarial mutation: given a single edge, the AI
    generates the strongest counter-mechanism plus one structured
    action — evidence search, polarity flip, or removal — with rationale.
    """

    edge_id: str = Field(..., description="Edge id to challenge.")
    model_type: ModelTypeStr = Field(
        "cld",
        description="Active model type — selects polarity vs weight semantics.",
    )


class EvidenceDemoteInputs(_In):
    """Input shape for AI interrogation Phase 3b EvidenceDemote.

    Element-scope: given an evidence link by (target, attribute, bibkey),
    the AI assesses whether the source actually supports the specific
    claim or only topically overlaps. Output is either a verdict change
    or removal, with rationale.
    """

    target_id: str = Field(..., description="Element the link is attached to (None for model-level).")
    attribute: str = Field(..., description="Attribute the link claims to support.")
    bibkey: str = Field(..., description="Reference bibkey identifying the citation.")


class EdgeReclassifyInputs(_In):
    """Input shape for AI interrogation Phase 3a EdgeReclassify.

    Model-scope adversarial mutation: the AI re-examines every edge's
    `kind` and proposes retags or removals with rationale, catching
    misclassified policy/governance/definitional links that inflated
    feedback-loop counts in the 4DWW capability run.
    """

    model_type: ModelTypeStr = Field(
        "cld",
        description="Active model type — reclassify always reasons against the substrate, but the framing is per model.",  # noqa: E501
    )


class CompletenessGateInputs(_In):
    """Input shape for AI interrogation Phase 2c CompletenessGate."""

    model_type: ModelTypeStr = Field(
        "cld", description="Active model type — completeness check is per model."
    )
    claims: list[str] = Field(
        default_factory=list,
        description=(
            "The claims that the upcoming Interpret* run will produce. The "
            "gate uses them to identify variables required by those claims."
        ),
    )
