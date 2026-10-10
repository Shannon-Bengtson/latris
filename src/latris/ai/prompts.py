"""Canonical prompt library.

The concept doc defines a fixed set of prompts the AI layer will support —
deliberately not an open chatbox. Each prompt is a ``PromptSpec`` with a
typed input schema and a template. Templates use ``{placeholders}`` that
will be substituted by the future call layer. No network calls here.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from latris.ai import proposals as _proposals
from latris.schema.model_types import get_model_type


def _validate_model_type(value: str) -> str:
    """Validate against the model-type registry; raises ValueError on unknown ID.

    Mirrors the pattern used by ``View.kind`` in ``schema/views.py`` so prompt
    inputs reject typos at construction time rather than at downstream
    string-comparison sites.
    """
    get_model_type(value)
    return value


ModelTypeStr = Annotated[str, AfterValidator(_validate_model_type)]
"""A model-type identifier validated against ``MODEL_TYPE_REGISTRY``."""

PackName = Literal["client", "audit", "review", "workshop", "publication"]
"""Pack names mirroring the keys of ``exporters/packs.py:PACKS``."""

ViewKind = Literal["cld", "dag"]
"""Stable formal-view kinds the projector supports."""


class PromptScope(StrEnum):
    """Whether the prompt operates on the whole model or a selected element."""

    model = "model"
    element = "element"


class PromptIntent(StrEnum):
    """What kind of result the prompt produces."""

    insight = "insight"  # read-only analysis — displayed inline
    action = "action"  # mutating proposal — preview → approve/reject → apply
    workflow = "workflow"  # special multi-turn interaction (e.g. elicitation)


@dataclass(frozen=True)
class PromptSpec:
    name: str
    title: str
    description: str
    inputs: type[BaseModel]
    template: str
    output_hint: str
    scope: PromptScope = PromptScope.model
    intent: PromptIntent = PromptIntent.insight
    # The structured-output schema this prompt returns. Attached below via
    # ``_wire`` so a prompt is defined in ONE place (the spec) rather than
    # smeared across a separate ``RESPONSE_MODELS`` dict. Optional only so the
    # per-prompt literals can omit it; ``_wire`` guarantees every live spec
    # carries one (guard test: tests/ai/test_prompt_contract.py).
    response_model: type[BaseModel] | None = None
    # Per-operation temperature override. ``None`` → use the project/config
    # default. Extraction/transformation ops run cool for consistent
    # granularity; generative critique keeps the default.
    temperature: float | None = None


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


class StoryBeatProseInputs(_In):
    beat_kind: str = Field(..., description="The beat's narrative role (hook, system_tour, answer, etc.).")
    source_text: str = Field("", description="Grounded content to rewrite into public register.")
    model_type: str = Field("", description="Model type being narrated.")


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


# ---------- Shared guidance blocks ----------
#
# These constants are interpolated into multiple prompt templates so that
# tightening guidance in one place can't silently leave a duplicate behind.
# Keep them tightly worded — they appear verbatim in user-facing prompts.

_MECHANISTIC_GRANULARITY_GUIDANCE = (
    "MECHANISTIC GRANULARITY: prefer specific, measurable, intervenable "
    "variables over broad trends or framings. A good variable is the "
    "lever, flow, stock, or quantity someone could in principle "
    "observe or act on.\n"
    "Examples (good → bad):\n"
    "  good: 'phosphorus loading', 'fertiliser application rate', "
    "'riparian vegetation cover', 'mean residence time'\n"
    "  bad:  'agricultural trends', 'land-use pressure', "
    "'ecosystem health', 'environmental concerns'\n"
    "If a candidate is a category or trend, decompose it into the "
    "underlying mechanistic drivers and produce those instead."
)

_LOOP_CLOSURE_GUIDANCE = (
    "LOOP CLOSURE (CLDs only): when the project is configured as a CLD, "
    "the user message will include a loop-closure-guidance block listing "
    "current loops and candidate closure pairs. CLDs are defined by "
    "feedback structure — if 0 or 1 loops are detected, you MUST "
    "propose at least one reinforcing and one balancing loop with a "
    "named mechanism, using the candidate pairs as starting points. "
    "Name in each rationale which loop a new edge participates in."
)

_EXISTENCE_ATTRIBUTE_CONVENTIONS = (
    "Attribute conventions:\n"
    "  'existence' — the reference supports that this entity or edge "
    "belongs in the model (its presence is empirically grounded). Prefer "
    "this when citing evidence for an entity or edge as a whole.\n"
    "  'description', 'polarity', 'confidence', etc. — the reference "
    "specifically supports that named field of the target. Use these "
    "narrower attributes when the evidence is field-specific."
)

_EXISTENCE_ATTRIBUTE_DEFAULT_NOTE = (
    "Default attribute is 'existence' (the reference supports the "
    "element as a whole); use a narrower attribute only when the "
    "evidence is field-specific."
)

_NO_FABRICATION_GUIDANCE = (
    "Do NOT fabricate content not present in the supplied evidence or "
    "project context — no invented references, URLs, quotes, variables, "
    "or claims. If you cannot find adequate evidence, say so rather "
    "than inventing."
)

_NODE_KIND_RUBRIC = (
    "NODE KIND — assign the most specific kind that fits; do NOT default "
    "everything to 'concept'. Choose exactly one:\n"
    "  variable — a measurable or observable quantity that can rise or fall "
    "(e.g. 'weekly hours worked', 'applicants per opening'). PREFER THIS "
    "whenever the node is something you could in principle measure.\n"
    "  concept — an abstract driver or construct with no direct measure "
    "(e.g. 'organisational culture'). Use only when no measurable proxy fits.\n"
    "  event — a discrete occurrence at a point in time (e.g. 'policy launch').\n"
    "  actor — a person, organisation, or agent that acts (e.g. 'key client').\n"
    "  state — a condition that holds over a period (e.g. 'understaffed').\n"
    "  decision — a deliberate choice an actor controls (e.g. 'adopt four-day week').\n"
    "  hazard — a threat or adverse possibility (e.g. 'loss of a key client').\n"
    "If genuinely none fit, use 'concept' and note why in the description. "
    "Never invent a kind outside this list."
)

_NODE_FEWSHOT = (
    "<examples>\n"
    "  <example>\n"
    "    context: model about adopting a four-day work week\n"
    "    good: 'weekly hours worked' (variable), 'applicants per opening' "
    "(variable), 'voluntary attrition rate' (variable), 'adopt four-day "
    "week' (decision)\n"
    "    bad:  'Employee Well-being' (concept), 'Recruitment Strength' "
    "(concept), 'Productivity' (concept)\n"
    "    why:  the bad items are broad framings dumped as 'concept'. "
    "Decompose each into the measurable lever that carries the effect — "
    "well-being to 'self-reported burnout score' + 'sick days per month'; "
    "recruitment strength to 'applicants per opening' + 'offer-acceptance rate'.\n"
    "  </example>\n"
    "  <example>\n"
    "    context: coastal water-quality model\n"
    "    good: 'phosphorus loading' (variable), 'fertiliser application rate' "
    "(variable), 'riparian vegetation cover' (variable)\n"
    "    bad:  'agricultural trends', 'ecosystem health', 'land-use pressure'\n"
    "    why:  categories and trends, not levers. Decompose into the "
    "mechanistic quantity someone could observe or act on.\n"
    "  </example>\n"
    "</examples>"
)

_EDGE_MECHANISM_GUIDANCE = (
    "EDGE MECHANISM — each edge is ONE direct causal step. State the "
    "mechanism (how the source changes the target) in the description, not a "
    "restatement of the labels. When an existing node M plausibly sits on the "
    "path from A to Z (A acts on Z *through* M), propose A→M and M→Z rather "
    "than the shortcut A→Z. Prefer a few load-bearing edges over an "
    "exhaustive pairwise sweep."
)

_ENTITY_PROVENANCE_GUIDANCE = (
    "PROVENANCE — capture the reasoning behind each node/edge in the same "
    "proposal, so the model is defensible without a second pass:\n"
    "  assumptions — add an assumption ONLY where the element rests on a "
    "non-obvious premise that, if wrong, would change the model (state it and "
    "why). Do NOT manufacture one per element; most elements need none. An "
    "empty list is the right answer when nothing non-obvious is at stake.\n"
    "  source_bibkeys — when a node or claim is grounded in one of the supplied "
    "references, list that reference's bibkey. Use ONLY bibkeys present in the "
    "supplied evidence; never invent one. Leave empty if the element is "
    "reasoned rather than sourced.\n"
    "  confidence — optionally 'low' / 'medium' / 'high' for how well-supported "
    "the element is."
)

_EDGE_POLARITY_GUIDANCE = (
    "EDGE POLARITY (CLDs) — when the project is a CLD, give each causal edge a "
    "polarity and a one-line polarity_rationale, authored together with the "
    "description so they cannot drift:\n"
    "  polarity — '+' if the source increases the target (or both move the "
    "same way), '-' if the source decreases it (they move oppositely), '~' if "
    "genuinely non-monotonic or contested.\n"
    "  polarity_rationale MUST tell the SAME causal story as the description. "
    "If you think the description's direction is wrong, do NOT silently invert "
    "the polarity — set the polarity that matches the description, mark "
    "confidence='low', and flag the disagreement in the rationale so a human "
    "can reconcile both. Leave polarity empty for non-CLD projects or "
    "non-causal edge kinds."
)

_SCOPE_CONTRACT_GUIDANCE = (
    "SCOPE CONTRACT — the project context may declare coverage dimensions, a "
    "granularity level, and an intended audience. When present, treat them as "
    "binding:\n"
    "  - Coverage dimensions: the model MUST span EVERY listed dimension — do "
    "not omit one, and do not stray far outside them. This is what keeps "
    "repeated runs covering the same ground.\n"
    "  - Granularity level: every node must match the stated level of "
    "resolution (e.g. a specific measurable variable vs a broad theme) and the "
    "abstraction level must stay UNIFORM across the whole model.\n"
    "  - Audience: frame the variables and mechanisms for the stated audience.\n"
    "If a field is absent from the project context, use your own judgement for "
    "that aspect."
)


# ---------- The library ----------
#
# ``_RAW_LIBRARY`` holds the per-prompt literals (input schema + template +
# classification). Response models and per-op temperature are attached to each
# spec by ``_wire`` at the bottom of this section, producing ``PROMPT_LIBRARY``.

_RAW_LIBRARY: dict[str, PromptSpec] = {
    "DraftConceptualModel": PromptSpec(
        name="DraftConceptualModel",
        title="Draft a conceptual model",
        description="Generate multiple candidate framings (nodes + edges) from a modelling question.",
        inputs=DraftConceptualModelInputs,
        template=(
            "You are drafting candidate conceptual models (framings) for a "
            "modelling question. The focus, the existing substrate, and any "
            "grounding references are provided in the user message.\n\n"
            "Produce the requested number of distinct framings. Each framing "
            "is a list of entities (label, kind, description, and — where "
            "warranted — assumptions / source_bibkeys / confidence) and edges "
            "(from_label, to_label, kind, a description of the causal "
            "mechanism, polarity + polarity_rationale for CLDs, and the same "
            "per-element provenance fields). Return structured edit "
            "proposals, not prose.\n\n"
            + _SCOPE_CONTRACT_GUIDANCE + "\n\n"
            + _MECHANISTIC_GRANULARITY_GUIDANCE + "\n\n"
            + _NODE_KIND_RUBRIC + "\n\n"
            + _NODE_FEWSHOT + "\n\n"
            + _EDGE_MECHANISM_GUIDANCE + "\n\n"
            + _EDGE_POLARITY_GUIDANCE + "\n\n"
            + _ENTITY_PROVENANCE_GUIDANCE + "\n\n"
            "DECISION VARIABLE — the entity whose label most closely matches "
            "the modelling question's primary subject is the *decision "
            "variable under study*. It is exogenous by construction. Do NOT "
            "propose `decision_rule` or `governance` edges that point TO "
            "this variable; such edges make the policy endogenous in its "
            "own analysis and inflate the apparent strength of reinforcing "
            "loops. Decision-rule edges between other variables (e.g. "
            "budget allocation between departments) remain valid.\n\n"
            + _NO_FABRICATION_GUIDANCE
        ),
        output_hint="A list of candidate framings. Each framing is a pydantic-validated "
        "Substrate subset. Human approves one (or none) before any commit.",
        scope=PromptScope.model,
        intent=PromptIntent.action,
    ),
    "RunElicitationInterview": PromptSpec(
        name="RunElicitationInterview",
        title="Run an elicitation interview",
        description="Interview-style Q&A to extract entities and relations from a user.",
        inputs=RunElicitationInterviewInputs,
        template=(
            "You are interviewing the user to elicit the next piece of "
            "their model for topic: {topic}\n"
            "Prior turns: {prior_turns}\n\n"
            "Ask ONE precise question that narrows the next entity or edge. "
            "The question should be the smallest piece of information whose "
            "answer would unblock the next concrete step in the model.\n\n"
            "Question anti-patterns to avoid:\n"
            "  - Compound questions ('What is X and how does it relate to Y?') "
            "    — split into separate turns.\n"
            "  - Yes/no framings ('Is A connected to B?') unless you genuinely "
            "    expect a binary signal and will follow up either way.\n"
            "  - Vague openers ('Tell me more about the system') — narrow to "
            "    one entity, edge, attribute, or boundary.\n"
            "  - Questions whose answer is already in the prior turns or the "
            "    current substrate.\n\n"
            "Example (bad → good):\n"
            "  bad:  'What are the main drivers and how do they interact?'\n"
            "  good: 'You named soil moisture as a driver of crop yield. "
            "        Does soil moisture also feed back through irrigation "
            "        decisions, or is the irrigation rate set independently?'"
        ),
        output_hint="One question + a proposed structured edit if the user's answer would resolve it.",
        scope=PromptScope.model,
        intent=PromptIntent.workflow,
    ),
    "FindNewConnections": PromptSpec(
        name="FindNewConnections",
        title="Find new plausible connections",
        description="Suggest edges that are plausible but absent from the current model.",
        inputs=FindNewConnectionsInputs,
        template=(
            "Given the current substrate, suggest plausible edges not yet "
            "present. This is the *interrogation-phase* connection sweep — "
            "the model already has accepted entities and the goal is to "
            "find load-bearing edges that are missing. (Contrast with "
            "SuggestConnections, which runs during Compose before entities "
            "are accepted and tends to be more exploratory.)\n\n"
            "The user message lists the existing nodes and, if the sweep is "
            "focused, the focus nodes to restrict to (otherwise consider all "
            "nodes). For each proposed edge, justify with a one-line "
            "mechanism in the description. Propose 3-8 high-value candidates — "
            "not an exhaustive sweep; the reviewer will triage.\n\n"
            "MEDIATOR ROUTING: when proposing a connection from A to Z, first "
            "scan the existing node list for any node M that plausibly "
            "mediates the relationship — i.e. A causes Z *through* M. If such "
            "an M exists, propose two edges (A → M and M → Z) instead of the "
            "shortcut A → Z. Only propose direct A → Z when no existing node "
            "sits naturally on the causal path; skipping a present mediator "
            "misrepresents causality. In each rationale, briefly say WHY you "
            "chose direct vs mediated so the human reviewer can judge.\n\n"
            + _SCOPE_CONTRACT_GUIDANCE + "\n\n"
            + _LOOP_CLOSURE_GUIDANCE + "\n\n"
            + _EDGE_POLARITY_GUIDANCE + "\n\n"
            + _ENTITY_PROVENANCE_GUIDANCE + "\n\n"
            "DECISION VARIABLE — the entity whose label most closely matches "
            "the project's modelling question is the *decision variable under "
            "study*. It is exogenous by construction. Do NOT propose "
            "`decision_rule` or `governance` edges that point TO this variable; "
            "such edges make the policy endogenous in its own analysis and "
            "inflate the apparent strength of reinforcing loops."
        ),
        output_hint="A list of candidate Edge proposals with per-edge mechanism, polarity, and provenance.",
        scope=PromptScope.model,
        intent=PromptIntent.action,
    ),
    "ProjectToFormalView": PromptSpec(
        name="ProjectToFormalView",
        title="Project to a formal view",
        description="Map the lingua-franca substrate to a specific view (CLD, DAG).",
        inputs=ProjectToFormalViewInputs,
        template=(
            "Project the current substrate to the {view} view. "
            "Respect the view's constraints (DAG acyclicity, CLD polarity, etc.). "
            "Propose the view entity/edge lists and any mappings to Layer 2."
        ),
        output_hint="A View* model + MappingRegistry additions.",
        scope=PromptScope.model,
        intent=PromptIntent.insight,
    ),
    "ChallengeThisConnection": PromptSpec(
        name="ChallengeThisConnection",
        title="Challenge this connection",
        description="Argue against a specific edge or attribute.",
        inputs=ChallengeThisConnectionInputs,
        template=(
            "Argue against {target_id} (attribute: {target_attribute}). "
            "Focus on mechanism, confounding, directionality, and scope. "
            "Produce a single Challenge with a terminal recommendation."
        ),
        output_hint="A Challenge model (state=open) + recommended terminal state.",
        scope=PromptScope.element,
        intent=PromptIntent.action,
    ),
    "AttackThisModel": PromptSpec(
        name="AttackThisModel",
        title="Attack this model",
        description="Model-level adversarial pass — what assumption, if wrong, breaks the conclusion?",
        inputs=AttackThisModelInputs,
        template=(
            "Identify the weakest load-bearing assumption in the current model. "
            "Optional focus: {scope_node_ids}. "
            "Explain which conclusion fails if the assumption is wrong.\n\n"
            "ALWAYS populate:\n"
            "  - weakest_assumption: short statement of the assumption.\n"
            "  - argument: why this assumption is the weakest.\n"
            "  - affected_node_ids: nodes whose conclusions depend on it.\n"
            "  - record_assumption: True (default) — formalises the named "
            "    assumption as a contested Assumption record.\n"
            "  - follow_up_question: ONE discharge-able question reviewers "
            "    should track. Phrased as 'Does X actually hold for our "
            "    context?' or similar. Keep concise."
        ),
        output_hint="A short argument identifying a single critical assumption + bounded provenance records.",
        scope=PromptScope.model,
        intent=PromptIntent.action,
    ),
    "FindCounterPathway": PromptSpec(
        name="FindCounterPathway",
        title="Find a missing counter-pathway",
        description="What causal pathway, if added, would most weaken the headline conclusion?",
        inputs=FindCounterPathwayInputs,
        template=(
            "Identify ONE causal pathway that is MISSING from the current "
            "model and that, if added, would weaken or invert the headline "
            "conclusion. Use the reference library to ground the pathway "
            "in published mechanism. Optional focus: {scope_node_ids}.\n\n"
            "AttackThisModel attacks the weakest assumption; this prompt "
            "attacks the weakest *structural omission*. Look especially for "
            "counter-loops and negative feedback the AI may have skipped — "
            "e.g. workload intensification, compensating behaviour, "
            "regulatory pushback, capacity ceilings.\n\n"
            "ALWAYS populate:\n"
            "  - missing_mechanism: short name (1-4 words) for the pathway.\n"
            "  - argument: 2-3 sentences explaining why this pathway "
            "    weakens the headline.\n"
            "  - proposed_nodes: labels of nodes that would represent the "
            "    mechanism, if any are not already in the model.\n"
            "  - proposed_edges: list of {{from_label, to_label, polarity, "
            "    rationale}} sketching the pathway. ADVISORY ONLY — these "
            "    are NOT auto-added to the model.\n"
            "  - supporting_bibkey: the most relevant reference, or null.\n"
            "  - record_question: True (default) — formalises the missing "
            "    mechanism as a tracked open question for the reviewer.\n\n"
            "Do NOT auto-add nodes or edges. The output is advisory. "
            "Limit yourself to ONE pathway per call — the most important "
            "missing mechanism, not a list."
        ),
        output_hint=(
            "A short proposal naming the missing pathway + one tracked open "
            "question for the human reviewer to discharge."
        ),
        scope=PromptScope.model,
        intent=PromptIntent.action,
    ),
    "SteelmanOpposingView": PromptSpec(
        name="SteelmanOpposingView",
        title="Steelman the opposing view",
        description="Strongest version of the counter-framing to a given element.",
        inputs=SteelmanOpposingViewInputs,
        template=(
            "Construct the STRONGEST version of the position opposing "
            "{target_id} — the one a good-faith expert would actually defend, "
            "not a strawman.\n\n"
            "Structure the steelman as 2-3 short paragraphs covering:\n"
            "  - mechanism: what causal story does the opposing view tell, "
            "    and which observations would be consistent with it?\n"
            "  - conditions: under what assumptions, contexts, or scope is "
            "    the opposing view most plausible?\n"
            "  - what it would take to update: name the evidence or test "
            "    that would distinguish the two views.\n\n"
            "This is a contested-view annotation, NOT a replacement edit. "
            "Do not propose deleting or flipping the current framing — the "
            "steelman is recorded alongside it so reviewers can weigh both."
        ),
        output_hint="A contested_views entry attached to the target's attribute set.",
        scope=PromptScope.element,
        intent=PromptIntent.action,
    ),
    "SyntheticPeerReview": PromptSpec(
        name="SyntheticPeerReview",
        title="Synthetic peer review",
        description="Review the whole model as a role-playing peer would.",
        inputs=SyntheticPeerReviewInputs,
        template=(
            "Review the current model as a {reviewer_role}. "
            "Structure your review as: scope, rigor, evidence, major risks."
        ),
        output_hint="A structured review comment, optionally with proposed Questions or Challenges.",
        scope=PromptScope.model,
        intent=PromptIntent.insight,
    ),
    "IdentifyResearchGaps": PromptSpec(
        name="IdentifyResearchGaps",
        title="Identify research gaps",
        description="What critical pieces would strengthen the model most?",
        inputs=IdentifyResearchGapsInputs,
        template=(
            "Survey the current model's attributes and evidence. "
            "Identify gaps whose closure would most increase defensibility.\n\n"
            "Each ResearchGap MUST include description, priority "
            "(high|medium|low), affected_node_ids when applicable, and "
            "suggested_action. record_as_questions defaults to True — "
            "each gap is parked as an OpenQuestion record so reviewers can "
            "track and discharge it. Set record_as_questions=False only "
            "when the gaps are deliberately exploratory."
        ),
        output_hint="A list of gap descriptions; each becomes an OpenQuestion via apply().",
        scope=PromptScope.model,
        intent=PromptIntent.action,
    ),
    "ScopeCheck": PromptSpec(
        name="ScopeCheck",
        title="Scope & boundary check",
        description="Does the current model answer the modelling question and stay within the defined model boundary?",
        inputs=ScopeCheckInputs,
        template=(
            "Compare the current model to both the modelling question and the "
            "model boundary (if defined). Is the scope too narrow, too broad, "
            "or well-matched? Flag any elements outside the boundary. Justify.\n\n"
            "When verdict='too-broad': populate proposed_exclusions with "
            "concrete boundary statements that should be formally recorded.\n"
            "When verdict='too-narrow': populate proposed_questions with "
            "discharge-able questions about whether to bring something in scope.\n"
            "When verdict='well-matched': leave both empty (no mutation needed). "
            "Keep proposals to a small handful — 1-3 each — not a flood."
        ),
        output_hint="A verdict + bounded provenance records (exclusions or questions).",
        scope=PromptScope.model,
        intent=PromptIntent.action,
    ),
    "SuggestCitations": PromptSpec(
        name="SuggestCitations",
        title="Suggest citations",
        description="Propose references for an attribute that lacks evidence.",
        inputs=SuggestCitationsInputs,
        template=(
            "Propose 2–5 references supporting {target_id} / {target_attribute}.\n\n"
            + _EXISTENCE_ATTRIBUTE_CONVENTIONS + "\n\n"
            "Prefer sources already in the research base. "
            "Every NEW reference MUST include a url field with a direct link "
            "to the paper/report (publisher site, institutional repository, or "
            "government agency). DOI is optional bonus.\n\n"
            + _NO_FABRICATION_GUIDANCE
        ),
        output_hint="A list of Reference suggestions + proposed EvidenceLinks.",
        scope=PromptScope.element,
        intent=PromptIntent.action,
    ),
    "ExplainThisElement": PromptSpec(
        name="ExplainThisElement",
        title="Explain this element",
        description="Why does this node/edge exist in the current framing?",
        inputs=ExplainThisElementInputs,
        template=(
            "Explain {target_id} for a domain-aware reviewer who is new to "
            "this specific model. Write 2-4 short paragraphs covering:\n"
            "  - role: what {target_id} represents in the system, and what "
            "    kind of element it is (node / edge / etc.).\n"
            "  - dependencies: which incoming influences shape it and which "
            "    outgoing influences it shapes; name them by label, not ID.\n"
            "  - link to foundation: how it relates to the project's "
            "    modelling question, decision, or boundary.\n"
            "  - evidence: what supporting references or assumptions back it, "
            "    if any are attached.\n\n"
            "This is read-only — do NOT propose edits, additions, or "
            "challenges. Keep the prose grounded in the substrate as it "
            "actually is; do not speculate beyond what the context supplies."
        ),
        output_hint="A plain-prose explanation, no edits proposed.",
        scope=PromptScope.element,
        intent=PromptIntent.insight,
    ),
    "GeneratePack": PromptSpec(
        name="GeneratePack",
        title="Generate a report pack",
        description="Produce a structured report (client / audit / review / workshop / publication).",
        inputs=GeneratePackInputs,
        template=(
            "Generate the {pack} pack using the current substrate, evidence, "
            "provenance, and challenge history. Every claim must cite a commit "
            "or a provenance entry.\n\n"
            "Return the report as a list of ReportSection items, each with a "
            "concise `heading` and self-contained `content` (markdown). Keep "
            "each section focused on one topic — splitting the report into "
            "smaller sections bounds the impact of any single string-escape "
            "issue in the structured output."
        ),
        output_hint="A ReportDraft with one ReportSection per topical heading.",
        scope=PromptScope.model,
        intent=PromptIntent.insight,
    ),
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
    # ── Story (Communicate phase) ─────────────────────────────────────
    "StoryBeatProse": PromptSpec(
        name="StoryBeatProse",
        title="Write a story beat",
        description="Rewrite grounded interpretation content into a single plain-language story beat for a public audience.",  # noqa: E501
        inputs=StoryBeatProseInputs,
        template=(
            "You are writing one beat of a public-facing story that explains a "
            "model to a general, non-technical audience. This beat's role is "
            "'{beat_kind}'. Rewrite the source content in plain language: short "
            "sentences, no jargon, assume no prior knowledge. Keep it to 1–3 "
            "short paragraphs. CRITICAL: do not introduce any facts, numbers, or "
            "claims that are not present in the source content — you are changing "
            "the register, not the substance."
        ),
        output_hint="An InterpretProseResult with public-register prose.",
        scope=PromptScope.model,
        intent=PromptIntent.insight,
    ),
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
    "FillProvenanceField": PromptSpec(
        name="FillProvenanceField",
        title="Fill this field with AI",
        description=(
            "Suggest a value for a single provenance field (description, "
            "rationale, evidence note, etc.). The user reviews and saves "
            "via the normal field-edit path; nothing commits without "
            "explicit save."
        ),
        inputs=FillProvenanceFieldInputs,
        template=(
            "Suggest a value for the {target_kind} field {field_path}.\n"
            "Current value: {current_value}\n"
            "Use the project context above to make the suggestion specific, "
            "mechanistic, and consistent with the modelling question. "
            "Return a FillFieldProposal with `value`, `rationale`, and "
            "`confidence`."
        ),
        output_hint="A FillFieldProposal with the suggested field value.",
        scope=PromptScope.element,
        intent=PromptIntent.insight,
    ),
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
            "Across all interpretation sections (key_findings, sensitivity, "
            "assumptions, evidence_gaps, evidence_coverage, answer, "
            "implications, confidence, open_questions), identify specific "
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
    "VerifyClaimAgainstSource": PromptSpec(
        name="VerifyClaimAgainstSource",
        title="Verify claim against source",
        description=(
            "Audit-grade evidence verification. Given an evidence link "
            "and the claim it supposedly supports, the AI reads the "
            "Reference's source_snapshot extract and returns one of "
            "supports / contradicts / orthogonal / insufficient_extract. "
            "On `supports` the AI must include a verbatim quote that "
            "appears in the extract; the apply()-time validator rejects "
            "the proposal otherwise. The model cannot self-attest."
        ),
        inputs=VerifyClaimAgainstSourceInputs,
        template=(
            "You are verifying whether a cited source actually supports "
            "a specific claim. The user message gives you the claim, "
            "the source-snapshot extract, and metadata about the "
            "evidence link.\n\n"
            "Decide one of:\n"
            "  - supports: the extract contains language that backs "
            "    the claim. You MUST include a verbatim quote drawn "
            "    from the extract (copy-paste exact characters, "
            "    including punctuation). The quote will be checked "
            "    character-for-character against the stored extract; "
            "    paraphrases or near-matches are rejected.\n"
            "  - contradicts: the extract addresses the claim and "
            "    states the opposite. No quote required.\n"
            "  - orthogonal: the extract is on-topic but does not "
            "    address the specific claim. No quote required.\n"
            "  - insufficient_extract: the extract is too narrow / "
            "    only an abstract / does not contain enough text to "
            "    decide. Use this when you'd need to read more of the "
            "    source.\n\n"
            "Return a `summary` paragraph that names what the source "
            "actually says vs. what the claim asserts (the critique "
            "prose), plus a confidence (high/medium/low).\n\n"
            "Hard rules:\n"
            "- The verbatim quote MUST be a contiguous span of "
            "  characters from the extract. Do not splice multiple "
            "  parts together.\n"
            "- Do not invent text not present in the extract.\n"
            "- If you cannot find verbatim language that supports "
            "  the claim, choose orthogonal or insufficient_extract — "
            "  do NOT pick supports with a paraphrased quote.\n"
        ),
        output_hint=(
            "A VerifyClaimAgainstSourceProposal with verdict, "
            "rationale, confidence, summary, and (when verdict="
            "supports) a verbatim quote that the apply-time validator "
            "checks against the stored extract."
        ),
        scope=PromptScope.element,
        intent=PromptIntent.action,
    ),
    "ChallengeEdge": PromptSpec(
        name="ChallengeEdge",
        title="Challenge this edge",
        description=(
            "Adversarial pass on a single low-coverage or low-confidence "
            "edge. Generates the strongest counter-mechanism and proposes "
            "one of three actions: evidence_search (record an open question "
            "for a targeted search), polarity_flip (reverse the sign on a "
            "CLD edge), or remove (detach the edge entirely with rationale)."
        ),
        inputs=ChallengeEdgeInputs,
        template=(
            "You are challenging a single edge in a {model_type} model. "
            "Read the edge's source and destination labels, polarity (if "
            "any), description, and any attached evidence. Articulate the "
            "STRONGEST counter-mechanism — the mechanism that, if true, "
            "either reverses the sign or makes the edge irrelevant.\n\n"
            "Then choose ONE action:\n"
            "  - evidence_search: write a query the human should run "
            "    (Semantic Scholar, OpenAlex, etc.) that would settle "
            "    whether the edge holds. Records as an OpenQuestion.\n"
            "  - polarity_flip: pick a new polarity from + / - / ambiguous "
            "    when the counter-mechanism implies the sign is wrong.\n"
            "  - remove: detach the edge entirely when the counter-mechanism "
            "    suggests the relation is not real (or is wholly subsumed "
            "    by another edge).\n\n"
            "All actions carry a rationale and confidence (high/medium/low). "
            "ALSO produce a `summary` paragraph that is the critique prose "
            "itself — the strongest argument against the edge as currently "
            "encoded.\n\n"
            "Hard rules:\n"
            "- Pick ONE action, not multiple. The reviewer triages.\n"
            "- evidence_search query must be a literal search string, not "
            "  a sentence describing what to search.\n"
            "- polarity_flip is only valid for CLD models with a current "
            "  polarity attribute on the edge — otherwise pick a different "
            "  action.\n"
        ),
        output_hint=(
            "A ChallengeEdgeProposal with critique prose (summary), one "
            "action variant (evidence_search | polarity_flip | remove), "
            "rationale, and confidence."
        ),
        scope=PromptScope.element,
        intent=PromptIntent.action,
    ),
    "EvidenceDemote": PromptSpec(
        name="EvidenceDemote",
        title="Demote this evidence link",
        description=(
            "Adversarial pass on a single evidence link. Asks whether the "
            "cited source actually supports the specific claim, or only "
            "topically overlaps with it. Output is either a verdict change "
            "(supports → orthogonal / contradicts / insufficient_extract / "
            "unverified) or removal entirely, with rationale."
        ),
        inputs=EvidenceDemoteInputs,
        template=(
            "You are auditing one evidence link. The user message gives you "
            "the cited reference (title, abstract or source-snapshot when "
            "available), the target element, and the attribute the link "
            "claims to support.\n\n"
            "Decide whether the source genuinely supports the specific "
            "claim attached to this link, or only topically overlaps with "
            "it. Then pick ONE action:\n"
            "  - change_verdict: set support_verdict to one of unverified / "
            "    supports / contradicts / orthogonal / insufficient_extract. "
            "    Use orthogonal when the source is on-topic but does not "
            "    address THIS claim. Use insufficient_extract when the "
            "    snapshot/abstract is too thin to decide and a deeper "
            "    fetch is needed.\n"
            "  - remove: detach the link entirely when the source has no "
            "    bearing on the claim and the citation is misleading.\n\n"
            "Action carries a rationale and confidence (high/medium/low). "
            "ALSO produce a `summary` paragraph naming what the source "
            "actually says vs. what the claim asserts.\n\n"
            "Hard rules:\n"
            "- Do NOT promote to `supports` from this prompt — Phase 4 "
            "  promotes via verbatim-quote validation, not by AI fiat.\n"
            "- If the source-snapshot is missing entirely (only title is "
            "  available), prefer change_verdict→insufficient_extract over "
            "  remove. Removal is for misleading citations, not unread ones.\n"
        ),
        output_hint=(
            "An EvidenceDemoteProposal with one action (change_verdict | "
            "remove), rationale, confidence, and summary critique prose."
        ),
        scope=PromptScope.element,
        intent=PromptIntent.action,
    ),
    "EdgeReclassify": PromptSpec(
        name="EdgeReclassify",
        title="Reclassify edges",
        description=(
            "Adversarial pass over every edge to catch misclassified "
            "policy / governance / definitional links currently typed as "
            "causal. Each action is a retag (to the right kind) or a "
            "remove (with rationale) — non-causal kinds are excluded "
            "from loop and centrality analysis, so retagging is enough "
            "to repair the inflation bug without deleting structure."
        ),
        inputs=EdgeReclassifyInputs,
        template=(
            "You are reviewing a {model_type} model for edge-kind "
            "misclassification — the bug pattern from the 4DWW capability "
            "run, where policy/decision links and definitional identities "
            "were typed as causal and inflated feedback-loop counts.\n\n"
            "For each edge in the substrate, decide one of:\n"
            "  - keep: leave the edge as-is.\n"
            "  - retag: change the edge.kind to one of: causal, "
            "    decision_rule, governance, definitional. Use:\n"
            "      * causal — physical/behavioural mechanism A → B.\n"
            "      * decision_rule — policy or allocation (e.g. budget, "
            "        staffing rules).\n"
            "      * governance — accountability, ownership, oversight.\n"
            "      * definitional — identity / mathematical relation "
            "        (e.g. Output = Hours × Rate; Total / Average).\n"
            "  - remove: detach the edge entirely. Only choose this when "
            "    no kind tag fits — the edge is not a real relation, or "
            "    is wholly subsumed by another edge.\n\n"
            "For every action, give a one- or two-sentence rationale that "
            "names the relation (e.g. 'budget allocation, not mechanism'). "
            "Add a confidence: high / medium / low — your own confidence "
            "in the call. Default medium when unsure.\n\n"
            "ALSO produce a one-paragraph `summary` of the worst "
            "misclassifications you found and what changing them would "
            "do to the model's feedback-loop story. The summary is shown "
            "as critique prose alongside the per-edge actions.\n\n"
            "Hard rules:\n"
            "- Do NOT propose actions for edges that are already correctly "
            "  typed; mark those keep.\n"
            "- Do NOT change edge.kind to one of the v2+ kinds "
            "  (informational, flow, support, logical, association, "
            "  temporal, decomposition, conditional). Confine retags to "
            "  causal / decision_rule / governance / definitional.\n"
            "- Do NOT remove an edge as a stand-in for a polarity flip. "
            "  Polarity is a separate concern.\n"
        ),
        output_hint=(
            "An EdgeReclassifyProposal with per-edge actions (keep/retag/"
            "remove with rationale + confidence) plus a summary of the "
            "headline misclassifications."
        ),
        scope=PromptScope.model,
        intent=PromptIntent.action,
    ),
    "CompletenessGate": PromptSpec(
        name="CompletenessGate",
        title="Completeness gate",
        description=(
            "Run before Interpret* to identify variables required to answer "
            "the modelling question that are missing from the model. Reports "
            "are persisted at views/{model_type}/completeness-report.yaml so "
            "human overrides survive subsequent runs."
        ),
        inputs=CompletenessGateInputs,
        template=(
            "You are checking whether a {model_type} model has the variables "
            "needed to answer its modelling question, BEFORE interpretation "
            "prose is generated. The user has supplied claims the upcoming "
            "Interpret* will produce; identify variables required to support "
            "those claims that are missing from the entity set.\n\n"
            "For each missing variable produce a MissingVariableProposal "
            "with:\n"
            "  - name: short, human-readable label.\n"
            "  - rationale: one or two sentences on why the variable is "
            "    necessary to answer the question.\n"
            "  - required_for: list of claim strings (verbatim) or "
            "    open-question topics that depend on the variable.\n"
            "  - severity: required (the question cannot be answered without "
            "    this variable), recommended (the answer is materially "
            "    weaker without it), or optional (the variable is "
            "    nice-to-have).\n"
            "  - confidence: high/medium/low — your own confidence in the "
            "    call. Missing-variable detection is judgement-heavy; use "
            "    this honestly. Default to medium when unsure.\n\n"
            "Hard rules:\n"
            "- Do NOT re-propose variables the user has already excluded "
            "  (they appear under 'Prior excluded missing variables' in the "
            "  context). Excluded variables stay excluded.\n"
            "- Do NOT re-propose variables already represented as entities "
            "  in the model. Match case-insensitively on label.\n"
            "- Do NOT speculate beyond what the modelling question, claims, "
            "  and substrate support. If you cannot articulate a concrete "
            "  required_for chain, omit the proposal.\n\n"
            "Return a CompletenessGateResult with `entries` (the missing-"
            "variable proposals). The `coverage_ratio` field is populated "
            "by the application from the substrate — leave it at its "
            "default; do not attempt to compute it yourself."
        ),
        output_hint=(
            "A list of missing-variable records (name, rationale, "
            "required_for, severity, confidence). coverage_ratio is "
            "computed deterministically by the application."
        ),
        scope=PromptScope.model,
        intent=PromptIntent.action,
    ),
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
    # Story (Communicate phase) — public-register beat prose
    "StoryBeatProse": _proposals.InterpretProseResult,
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
    return {
        name: replace(
            spec,
            response_model=_RESPONSE_MODELS[name],
            temperature=_OP_TEMPERATURE.get(name),
        )
        for name, spec in raw.items()
    }


PROMPT_LIBRARY: dict[str, PromptSpec] = _wire(_RAW_LIBRARY)


# ---------- Per-field AI guidance ----------

FIELD_GUIDANCE: dict[tuple[str, str], str] = {
    # (target_kind, field_path) → short instruction snippet appended to the
    # FillProvenanceField user message. Keep entries concise — the helper
    # below falls back to a default for unmapped fields.
    ("project", "background"): (
        "Write 2-4 sentences capturing the broader situation: who this model "
        "is for, what decision it informs, the operational/policy setting, "
        "and any prior work or constraints worth respecting."
    ),
    ("project", "boundary"): (
        "List what is in and out of scope. Prefer concrete bounds (variables, "
        "spatial/temporal extent) over abstractions."
    ),
    ("project", "exclusions"): (
        "List things deliberately not modelled, with one-line reasons."
    ),
    ("project", "predictions"): (
        "List the model's expected outputs or forecast values, in plain "
        "language, with the readership in mind."
    ),
    ("entity", "description"): (
        "1-2 sentences: what this node represents mechanistically. Focus on "
        "the lever/quantity, not meta-description ('this is a node about X')."
    ),
    ("edge", "description"): (
        "1-2 sentences: how the source affects the target — mechanism, sign, "
        "and any conditions."
    ),
    ("citation", "attribute"): (
        "Which part of the cited work supports this claim — page/section/"
        "figure where applicable, or 'overall thesis' if work-level."
    ),
    ("citation", "notes"): (
        "1-2 sentences linking the cited work to the specific claim it "
        "supports here."
    ),
    ("assumption", "rationale"): (
        "1-2 sentences: why this assumption is needed for the model to make "
        "sense, and what would happen if it were violated."
    ),
    ("challenge", "argument"): (
        "Argue against the claim/element. Focus on mechanism, confounding, "
        "directionality, or scope. Be specific."
    ),
    ("challenge", "resolution_rationale"): (
        "1-2 sentences: how the challenge was resolved, accepted, or "
        "deferred, and why."
    ),
    ("decision", "rationale"): (
        "Why this decision was made — the tradeoff being managed, "
        "alternatives considered, and the reason this option was chosen."
    ),
    ("question", "question"): (
        "1 sentence: a specific open question about this element. Avoid "
        "rhetorical or yes/no framings."
    ),
}


def field_guidance(target_kind: str, field_path: str) -> str:
    """Return a guidance snippet for a (target_kind, field_path), or a default."""
    if (target_kind, field_path) in FIELD_GUIDANCE:
        return FIELD_GUIDANCE[(target_kind, field_path)]
    # Fall back: try last segment of dotted path against any kind
    last = field_path.rsplit(".", 1)[-1]
    for (_kind, path), guidance in FIELD_GUIDANCE.items():
        if path == last:
            return guidance
    return (
        "Write a concise, evidence-aware value for this field, consistent "
        "with the project context above."
    )


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
