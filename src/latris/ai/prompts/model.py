"""Prompts that draft, extend, challenge and review the model and its elements."""

from __future__ import annotations

from latris.ai.prompts._guidance import (
    _EDGE_MECHANISM_GUIDANCE,
    _EDGE_POLARITY_GUIDANCE,
    _ENTITY_PROVENANCE_GUIDANCE,
    _EXISTENCE_ATTRIBUTE_CONVENTIONS,
    _LOOP_CLOSURE_GUIDANCE,
    _MECHANISTIC_GRANULARITY_GUIDANCE,
    _NO_FABRICATION_GUIDANCE,
    _NODE_FEWSHOT,
    _NODE_KIND_RUBRIC,
    _SCOPE_CONTRACT_GUIDANCE,
)
from latris.ai.prompts._spec import PromptIntent, PromptScope, PromptSpec
from latris.ai.prompts.inputs import (
    AttackThisModelInputs,
    ChallengeThisConnectionInputs,
    DraftConceptualModelInputs,
    ExplainThisElementInputs,
    FindCounterPathwayInputs,
    FindNewConnectionsInputs,
    GeneratePackInputs,
    IdentifyResearchGapsInputs,
    ProjectToFormalViewInputs,
    RunElicitationInterviewInputs,
    ScopeCheckInputs,
    SteelmanOpposingViewInputs,
    SuggestCitationsInputs,
    SyntheticPeerReviewInputs,
)

PROMPTS: dict[str, PromptSpec] = {
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
}
