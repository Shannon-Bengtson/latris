"""Model type registry — declarative specs for each formal model type.

Each ``ModelTypeSpec`` describes the requirements and constraints for a
particular modelling formalism (CLD, DAG, BN, etc.).  The registry is
populated at import time with all known types.  Operations and the GUI
use the registry to gate view switching and compute readiness.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ModelTypeAvailability = Literal["stable", "planned"]

# Where a type sits on the product roadmap. Separate from ``availability``:
# every registered type passes the inspectability test, but only some are
# being worked towards. ``built`` ⇔ stable; ``roadmap`` = committed next;
# ``parked`` = coherent but deferred; ``not_planned`` = registered, not on
# the roadmap (not rejected — revisited if a user needs it).
RoadmapStatus = Literal["built", "roadmap", "parked", "not_planned"]


@dataclass(frozen=True)
class ModelFamily:
    """A group of model types a picker shows together, by the kind of question they answer."""

    id: str
    label: str
    description: str


# In the order a picker shows them.
MODEL_FAMILIES: tuple[ModelFamily, ...] = (
    ModelFamily("causal", "Causal & Systems Thinking",
                "Map causal structure, feedback, and accumulation over time; lay out programme logic."),
    ModelFamily("risk", "Risk & Safety",
                "Quantify uncertainty, analyse failures and barriers, and build assurance cases."),
    ModelFamily("decisions", "Decisions & Evidence",
                "Choose between options, weigh competing explanations, and value decisions over time."),
)


@dataclass(frozen=True)
class ModelTypeSpec:
    """Declarative specification for a model type (formal view).

    Uses ``availability`` rather than ``status`` so the word ``status``
    stays reserved for the unified Maturity ladder. See
    docs/design/MATURITY_LADDER.md.
    """

    id: str
    display_name: str
    short_name: str
    description: str
    availability: ModelTypeAvailability

    # Model-specific attributes stored in views/parameters/{id}-{attr}.yaml.
    # These are the attributes that *can* be set for this model type.
    model_attributes: tuple[str, ...] = ()

    # Subset of model_attributes that are *required* for readiness = 100%.
    # Optional attributes (e.g. CLD polarity) are settable but not required.
    required_model_attributes: tuple[str, ...] = ()

    # Structural constraint validator names (looked up in a validator dict).
    structural_validators: tuple[str, ...] = ()

    # View role constraints (formalism-specific entity classifications).
    required_roles: tuple[str, ...] = ()
    allowed_roles: tuple[str, ...] = ()

    # Edge kind constraints (substrate-level relationship types).
    required_edge_kinds: tuple[str, ...] = ()
    allowed_edge_kinds: tuple[str, ...] = ()

    roadmap: RoadmapStatus = "not_planned"

    # How a surface presents the type to someone choosing one (the app's model picker, help, the site):
    # a paragraph on what it is, the question it answers, what it's best for and what it offers.
    family: str = ""  # a MODEL_FAMILIES id
    summary: str = ""
    answers: str = ""
    best_for: str = ""
    key_features: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

MODEL_TYPE_REGISTRY: dict[str, ModelTypeSpec] = {}


def register_model_type(spec: ModelTypeSpec) -> None:
    """Add *spec* to the global registry. Raises on duplicate ID."""
    if spec.id in MODEL_TYPE_REGISTRY:
        raise ValueError(f"Duplicate model type ID: {spec.id!r}")
    if (spec.availability == "stable") != (spec.roadmap == "built"):
        raise ValueError(f"Model type {spec.id!r}: roadmap 'built' must go with availability 'stable'")
    MODEL_TYPE_REGISTRY[spec.id] = spec


def get_model_type(model_type_id: str) -> ModelTypeSpec:
    """Return the spec for *model_type_id*, or raise ``ValueError``."""
    try:
        return MODEL_TYPE_REGISTRY[model_type_id]
    except KeyError:
        known = sorted(MODEL_TYPE_REGISTRY)
        raise ValueError(f"Unknown model type: {model_type_id!r}. Known: {known}") from None


def list_model_types(*, include_planned: bool = False) -> list[ModelTypeSpec]:
    """Return registered specs, optionally filtering out ``planned`` types."""
    specs = list(MODEL_TYPE_REGISTRY.values())
    if not include_planned:
        specs = [s for s in specs if s.availability == "stable"]
    return specs


# ---------------------------------------------------------------------------
# Built-in model type definitions
# ---------------------------------------------------------------------------

# -- v1 stable (switchable) ------------------------------------------------

register_model_type(
    ModelTypeSpec(
        id="cld",
        display_name="Causal Loop Diagram",
        short_name="CLD",
        description="Directed graph with polarity (+/\u2212) on edges; cycles allowed.",
        family="causal",
        summary=(
            "A directed graph where every edge carries polarity (+/−) indicating whether the source reinforces or"
            " counteracts the target. Cycles are allowed and represent feedback loops."
        ),
        answers="How does this work — what feeds back on what?",
        best_for=(
            "Mapping feedback dynamics, understanding system behaviour over time, and identifying "
            "reinforcing/balancing loops."
        ),
        key_features=(
            "Polarity (+/−) required on every edge",
            "Cycles allowed (feedback loops)",
            "Start here by default — the cheapest honest answer; every other formalism builds on it",
        ),
        roadmap="built",
        availability="stable",
        model_attributes=("polarity",),
        allowed_roles=("outcome",),
        structural_validators=("loops_present",),
    )
)

register_model_type(
    ModelTypeSpec(
        id="dag",
        display_name="Directed Acyclic Graph",
        short_name="DAG",
        description="Directed graph that must be acyclic; directionality mandatory.",
        family="causal",
        summary=(
            "A directed graph that enforces acyclicity — no node can reach itself by following edges. Used when "
            "causal direction matters and feedback loops are not part of the model."
        ),
        answers="Can this effect actually be estimated, and from what data?",
        best_for=(
            "Causal inference, dependency analysis, and workflow or process modelling where cycles would be "
            "contradictory."
        ),
        key_features=(
            "Acyclic: no feedback loops",
            "Identification: adjustment sets and d-separation",
            "Effect estimates from data, adjusting for what the DAG requires",
        ),
        roadmap="built",
        availability="stable",
        allowed_roles=("outcome",),
        structural_validators=("acyclicity",),
    )
)

register_model_type(
    ModelTypeSpec(
        id="bn",
        display_name="Bayesian Network",
        short_name="BN",
        description="DAG with state spaces and conditional probability tables.",
        family="risk",
        summary=(
            "A DAG augmented with state spaces and conditional probability tables (CPTs). Each node has a "
            "discrete or continuous probability distribution conditioned on its parents."
        ),
        answers="How likely is each outcome, and what would change my mind?",
        best_for=(
            "Probabilistic reasoning, risk quantification, diagnostic inference, and decision support under "
            "uncertainty."
        ),
        key_features=(
            "States and probability tables per factor; Noisy-OR and weighted tables",
            "Queries with evidence, uncertain evidence and interventions; most likely explanation",
            "How sure a probability is (Monte Carlo over the tables); learning tables from data",
        ),
        roadmap="built",
        availability="stable",
        structural_validators=("acyclicity", "state_space_defined", "cpt_complete"),
    )
)

# -- System Dynamics (stable; registered after the first four) ---------------

register_model_type(
    ModelTypeSpec(
        id="sd",
        display_name="System Dynamics",
        short_name="SD",
        description=(
            "Stocks, flows, and feedback loops with unit-checked equations, simulated over time, with "
            "scenarios, Monte Carlo uncertainty bands, sensitivity, and loop dominance."
        ),
        family="causal",
        summary=(
            "Extends causal loop diagrams with stocks (accumulators), flows (rates of change), and auxiliary "
            "variables. Behaviour is simulated via ordinary differential equations."
        ),
        answers="How will it behave over time if we intervene?",
        best_for=(
            "Simulating system behaviour over time, policy analysis, and understanding accumulation and depletion"
            " dynamics."
        ),
        key_features=(
            "Stocks, flows and auxiliaries with unit-checked equations",
            "Scenarios, Monte Carlo bands, options compared on the same draws, sensitivity",
            "Loop dominance: which feedback loop drives the behaviour, and when",
        ),
        roadmap="built",
        availability="stable",
        structural_validators=(
            "sd_classification_complete",
            "sd_flow_connects_stock",
            "sd_no_algebraic_loops",
            "sd_equations_complete",
            "sd_values_complete",
            "sd_tables_well_formed",
            "sd_dimensional_consistency",
        ),
        allowed_roles=("stock", "flow", "auxiliary", "constant", "source_sink"),
        # Declarative only, as for influence_diagram: enforcement lives in the
        # sd_* structural validators above, not in a generic roles check.
        required_roles=("stock", "flow"),
        required_edge_kinds=("flow",),
    )
)

# -- planned (registered, not switchable). See each entry's ``roadmap``. ---

register_model_type(
    ModelTypeSpec(
        id="causal_dag",
        display_name="Causal DAG",
        short_name="CDAG",
        description=(
            "DAG with observed/unobserved classification and adjustment sets. Being folded into the "
            "DAG view as identification analyses rather than a separate model type."
        ),
        family="causal",
        summary=(
            "A DAG where nodes are classified as observed or unobserved (latent). Supports identification of "
            "adjustment sets, instrumental variables, and front-door/back-door criteria for causal effect "
            "estimation."
        ),
        answers="Can this effect be estimated from observational data?",
        best_for="Causal effect estimation from observational data, confounding analysis, and study design.",
        key_features=(
            "Observed/unobserved node classification",
            "Adjustment set identification",
            "d-separation and conditional independence testing",
        ),
        roadmap="not_planned",
        availability="planned",
        structural_validators=("acyclicity",),
    )
)

register_model_type(
    ModelTypeSpec(
        id="regression",
        display_name="Regression",
        short_name="REG",
        description=(
            "DAG with fitted/elicited edge coefficients — linear/logistic/GLM. "
            "Doubles as the quantification of causal/DAG edges."
        ),
        family="causal",
        summary="A statistical model of one outcome on several predictors, fitted to data.",
        answers="How much does each factor move the outcome, in the data?",
        best_for="Quantifying associations in a dataset.",
        key_features=("Fitted coefficients with uncertainty", "Needs a dataset", "Not yet built",),
        roadmap="not_planned",
        availability="planned",
        structural_validators=("acyclicity",),
    )
)

register_model_type(
    ModelTypeSpec(
        id="gsn",
        display_name="Goal Structuring Notation",
        short_name="GSN",
        description="Safety-case argumentation: goals, strategies, solutions, context.",
        family="risk",
        summary=(
            "A structured argumentation framework used in safety cases. Links top-level safety goals to "
            "strategies, sub-goals, solutions (evidence), context, and assumptions."
        ),
        answers="How do we argue that this goal is met?",
        best_for="Safety assurance, regulatory compliance, and structured argumentation for critical systems.",
        key_features=(
            "Goals, strategies, solutions, context, assumptions",
            "Hierarchical argument structure",
            "Widely used in aerospace, defence, and automotive",
        ),
        roadmap="roadmap",
        availability="planned",
    )
)

register_model_type(
    ModelTypeSpec(
        id="bow_tie",
        display_name="Bow-Tie Diagram",
        short_name="BT",
        description=(
            "Threats and consequences of one top event and the barriers between them: lines that rest on one "
            "barrier or none, shared barriers, uncontrolled escalation factors, and layer-of-protection "
            "frequencies with each value's provenance."
        ),
        family="risk",
        summary=(
            "A risk analysis diagram centred on a hazardous event. The left side maps threats and preventive "
            "barriers; the right side maps consequences and mitigating barriers."
        ),
        answers="What could cause this hazard — and what follows if it does?",
        best_for="Operational risk analysis, barrier management, and visualising threat–consequence pathways.",
        key_features=(
            "Threats and consequences either side of one top event",
            "Preventive and mitigating barriers, with their effectiveness",
            "Line frequencies and Monte Carlo over the uncertainty",
        ),
        roadmap="built",
        availability="stable",
        structural_validators=("bt_elements_classified", "bt_links_valid", "bt_lines_complete"),
        # One per element; the top event is the outcome of interest, so there is no separate "outcome" role.
        allowed_roles=("hazard", "top_event", "threat", "consequence", "barrier", "escalation_factor"),
        required_roles=("top_event", "threat", "consequence"),
    )
)

register_model_type(
    ModelTypeSpec(
        id="fault_tree",
        display_name="Fault Tree",
        short_name="FT",
        description=(
            "Top-down failure decomposition with AND, OR and k-out-of-n gates: minimal cut sets, single points "
            "of failure, exact top-event probability and importance, with each probability's provenance."
        ),
        family="risk",
        summary=(
            "A top-down decomposition of a system failure into contributing causes using AND/OR logic gates. Used"
            " for reliability and safety analysis."
        ),
        answers="How could this system fail, and how likely is each path?",
        best_for=(
            "Reliability engineering, failure mode analysis, and quantifying the probability of system-level "
            "failures."
        ),
        key_features=(
            "Top event decomposed through AND, OR and vote gates",
            "Minimal cut sets, top-event probability and importance",
            "Monte Carlo over the basic events' uncertainty",
        ),
        roadmap="built",
        availability="stable",
        # Acyclicity is checked within the tree (ft_tree_connected), not over the whole shared substrate.
        structural_validators=("ft_events_classified", "ft_gates_complete", "ft_tree_connected"),
        # One per event; the top event is the outcome of interest, so there is no separate "outcome" role.
        allowed_roles=("top_event", "intermediate_event", "basic_event", "undeveloped_event"),
        required_roles=("top_event", "basic_event"),
    )
)

register_model_type(
    ModelTypeSpec(
        id="petri_net",
        display_name="Petri Net",
        short_name="PN",
        description="Bipartite graph of places and transitions for concurrent systems.",
        family="risk",
        summary=(
            "A bipartite graph of places (states) and transitions (events). Tokens flow through the network, "
            "modelling concurrency, synchronisation, and resource contention."
        ),
        answers="How do concurrent processes synchronise and contend for resources?",
        best_for="Modelling concurrent systems, workflows, protocols, and resource allocation problems.",
        key_features=(
            "Bipartite graph (places + transitions)",
            "Token-based state representation",
            "Formal concurrency semantics",
        ),
        roadmap="not_planned",
        availability="planned",
        structural_validators=("bipartite",),
    )
)

# -- Tier 1: decision-making, risk, and communication formalisms -----------

register_model_type(
    ModelTypeSpec(
        id="markov",
        display_name="Markov Cohort Model",
        short_name="MC",
        description=(
            "A cohort moving between states each cycle: the trace, discounted costs and outcomes per strategy, "
            "and incremental cost-effectiveness (ICERs, dominance, net benefit at a willingness to pay)."
        ),
        family="decisions",
        summary=(
            "A state-transition graph where edges carry transition probabilities. Optionally includes decision "
            "(action) nodes and reward/cost values for Markov Decision Processes."
        ),
        answers="What happens next, and what is each state worth over time?",
        best_for=(
            "Health-economic modelling, queueing theory, reliability analysis, and sequential decision-making "
            "under uncertainty."
        ),
        key_features=(
            "States, transitions per cycle and a starting cohort",
            "Costs and outcomes (e.g. QALYs) per state",
            "Cost-effectiveness across strategies, with ICERs",
        ),
        roadmap="built",
        availability="stable",
        structural_validators=("mk_states", "mk_transitions"),
        allowed_roles=("state", "strategy"),
        required_roles=("state",),
    )
)

register_model_type(
    ModelTypeSpec(
        id="influence_diagram",
        display_name="Influence Diagram",
        short_name="ID",
        description="Extension of Bayesian network with decision and utility nodes for decision analysis.",
        family="decisions",
        summary=(
            "An extension of Bayesian networks that adds decision nodes and utility nodes. Informational arcs "
            "show what is known when each decision is made."
        ),
        answers="Which decision maximises expected value under uncertainty?",
        best_for="Normative decision analysis, policy evaluation, and multi-stage decision problems under uncertainty.",
        key_features=(
            "Decision, chance, and utility node types",
            "Informational arcs (non-causal)",
            "Extends Bayesian network structure",
        ),
        roadmap="roadmap",
        availability="planned",
        structural_validators=("acyclicity",),
        required_roles=("chance", "utility"),
        required_edge_kinds=("causal", "informational"),
    )
)

register_model_type(
    ModelTypeSpec(
        id="decision_tree",
        display_name="Decision Tree",
        short_name="DT",
        description=(
            "Decision, chance and terminal nodes: the optimal strategy by expected value, what perfect information "
            "on each uncertainty is worth (EVPI), and the probabilities at which the best choice changes."
        ),
        family="decisions",
        summary=(
            "A sequential tree of decision and chance nodes branching to terminal outcome nodes. Each branch "
            "carries a probability (chance) or is a deliberate choice (decision)."
        ),
        answers="Which sequence of choices and chances pays off best?",
        best_for=(
            "Clinical decision analysis, cost-effectiveness analysis, and explicit enumeration of decision "
            "pathways."
        ),
        key_features=(
            "Decisions, chance events and payoffs",
            "The best strategy by expected value",
            "The value of perfect information, and probability thresholds",
        ),
        roadmap="built",
        availability="stable",
        structural_validators=("dt_structure", "dt_nodes_complete", "dt_probabilities_complete"),
        allowed_roles=("decision", "chance", "terminal"),
        required_roles=("decision", "terminal"),
    )
)

register_model_type(
    ModelTypeSpec(
        id="event_tree",
        display_name="Event Tree",
        short_name="ET",
        description=(
            "Forward from one initiating event through yes/no headings to end states: a complete-tree check, "
            "sequence and end-state probabilities and frequencies, with each value's provenance."
        ),
        family="risk",
        summary=(
            "A forward-logic tree starting from an initiating event. Each branching point represents a safety "
            "barrier that either holds or fails, leading to different consequence scenarios."
        ),
        answers="What unfolds after this initiating event?",
        best_for="Accident sequence analysis, safety-barrier assessment, and probabilistic risk analysis.",
        key_features=(
            "An initiating event through ordered safety functions",
            "Each sequence's end state and frequency",
            "Conditional probabilities and Monte Carlo over the uncertainty",
        ),
        roadmap="built",
        availability="stable",
        # The tree is stored as data (heading order and sequences), not as substrate links.
        structural_validators=("et_elements_classified", "et_headings_ordered", "et_sequences_complete"),
        allowed_roles=("initiating_event", "functional_event", "end_state"),
        required_roles=("initiating_event", "functional_event", "end_state"),
    )
)

register_model_type(
    ModelTypeSpec(
        id="fishbone",
        display_name="Ishikawa / Fishbone Diagram",
        short_name="FB",
        description="Root cause analysis diagram with categorised cause branches converging on an effect.",
        family="risk",
        summary=(
            "A root cause analysis diagram where categorised cause branches (e.g. People, Process, Equipment) "
            "converge on a central effect. Used in quality management and incident investigation."
        ),
        answers="What are the root causes of this effect?",
        best_for="Root cause analysis, quality improvement, manufacturing defect investigation, and incident debriefs.",
        key_features=(
            "Categorised cause branches (6M, 4P, etc.)",
            "Central effect node",
            "Structured brainstorming tool",
        ),
        roadmap="not_planned",
        availability="planned",
        structural_validators=("acyclicity",),
    )
)

register_model_type(
    ModelTypeSpec(
        id="theory_of_change",
        display_name="Theory of Change",
        short_name="ToC",
        description=(
            "Results chain from activities through outputs and outcomes to impact, with the evidence and "
            "assumptions behind each step laid out pathway by pathway."
        ),
        family="causal",
        summary=(
            "A logic model that maps the causal pathway from activities and inputs through outputs and "
            "intermediate outcomes to long-term goals. Assumptions and external factors are made explicit."
        ),
        answers="How do our activities add up to the intended impact?",
        best_for=(
            "Programme evaluation, policy design, grant proposals, and impact assessment in development/social "
            "sectors."
        ),
        key_features=(
            "Activities → outputs → outcomes → impact",
            "Process tracing: each link's evidence tests and confidence",
            "Impact from data: interrupted time series or difference-in-differences",
        ),
        roadmap="built",
        availability="stable",
        structural_validators=("acyclicity", "toc_levels_complete", "toc_links_forward", "toc_pathways_complete"),
        # Logic-model levels (W.K. Kellogg Foundation 2004). One per factor; the
        # outcome of interest is the impact, so there is no separate "outcome" role.
        allowed_roles=("input", "activity", "output", "short_term_outcome", "long_term_outcome", "impact"),
        required_roles=("activity", "impact"),
    )
)

register_model_type(
    ModelTypeSpec(
        id="mcda",
        display_name="Multi-Criteria Decision Analysis",
        short_name="MCDA",
        description=(
            "Options scored against weighted criteria: the ranking, each criterion's contribution, dominated "
            "options, and how far each weight would have to move to change the choice."
        ),
        family="decisions",
        summary=(
            "Options scored against weighted criteria. Each criterion has a direction, a scale and a swing "
            "weight; the options' weighted scores rank them, and a sensitivity analysis says how far each weight "
            "can move before the ranking changes."
        ),
        answers="Which option is best on the criteria that matter, and how robust is that?",
        best_for="Choosing between a few options on several criteria: site selection, procurement, policy options.",
        key_features=(
            "Options × criteria score matrix",
            "Swing weights, with each weight's source",
            "How far a weight can move before the top choice changes",
        ),
        roadmap="built",
        availability="stable",
        structural_validators=("mcda_elements_present", "mcda_criteria_complete", "mcda_scores_complete"),
        allowed_roles=("option", "criterion"),
        required_roles=("option", "criterion"),
    )
)

register_model_type(
    ModelTypeSpec(
        id="ach",
        display_name="Analysis of Competing Hypotheses",
        short_name="ACH",
        description=(
            "Hypotheses against the evidence: which one the evidence fails to rule out, which items don't "
            "discriminate, and which linchpins the conclusion turns on."
        ),
        family="decisions",
        summary=(
            "Competing hypotheses rated against each item of evidence (consistent, neutral or inconsistent), "
            "weighted by how credible and relevant the evidence is. Evidence can't prove a hypothesis, but it can"
            " rule one out: hypotheses rank by weighted inconsistency."
        ),
        answers="Which explanation does the evidence fail to rule out?",
        best_for="Diagnosis and intelligence-style questions: why did this happen, which explanation holds up.",
        key_features=(
            "Hypotheses × evidence consistency matrix",
            "Credibility and relevance weighting",
            "Ranked by inconsistency, with the linchpin evidence named",
        ),
        roadmap="built",
        availability="stable",
        structural_validators=("ach_elements_present", "ach_matrix_complete"),
        allowed_roles=("hypothesis", "evidence_item"),
        required_roles=("hypothesis", "evidence_item"),
    )
)

# -- Tier 2: systems thinking, process, and state-based formalisms ---------

register_model_type(
    ModelTypeSpec(
        id="argument_map",
        display_name="Argument Map",
        short_name="AM",
        description=(
            "An argument laid out as claims, the reasons for and objections against them, and the answers to "
            "those: whether the conclusion stands, what it rests on, and which objection is still unanswered."
        ),
        family="decisions",
        summary=(
            "A conclusion and the claims offered for and against it (Toulmin, IBIS). A premise supports or "
            "attacks a claim; premises in one reason work only together; each link can state its warrant. "
            "The map is evaluated by grounded labelling: each claim stands, is defeated, or is undecided."
        ),
        answers="Does the conclusion stand, and what does it rest on?",
        best_for=(
            "A case argued to a board, client or reviewer: a policy or business case, a recommendation, a "
            "structured evidence review, and the objections it has to answer."
        ),
        key_features=(
            "Supporting reasons (linked or independent) and objections",
            "Each claim's grounds from its checked sources; challenges as objections to an inference",
            "Whether the conclusion stands, its linchpins, and unanswered objections",
        ),
        roadmap="built",
        availability="stable",
        structural_validators=("am_structure", "am_conclusion_argued"),
        allowed_roles=("conclusion", "claim", "question"),
        required_roles=("conclusion", "claim"),
    )
)

register_model_type(
    ModelTypeSpec(
        id="fcm",
        display_name="Fuzzy Cognitive Map",
        short_name="FCM",
        description="Weighted directed graph with edge strengths in [\u22121, +1]; cycles allowed.",
        family="causal",
        summary=(
            "A weighted directed graph where each edge carries a causal strength in the range [−1, +1]. Supports "
            "simulation by iterating activation levels through a transfer function. Cycles are allowed."
        ),
        answers="Which forces dominate, roughly?",
        best_for="Participatory modelling, expert-driven scenario analysis, and semi-quantitative causal reasoning.",
        key_features=(
            "Link weights in [−1, +1]",
            "Steady state under a scenario (factors held at a value)",
            "An extension of the causal loop diagram",
        ),
        roadmap="built",
        availability="stable",
        model_attributes=("weight",),
        allowed_roles=("outcome",),
    )
)

register_model_type(
    ModelTypeSpec(
        id="flowchart",
        display_name="Process Map / Flowchart",
        short_name="FC",
        description="Activity-decision-outcome flow for process modelling.",
        family="causal",
        summary=(
            "A process flow diagram with activity, decision, and start/end nodes connected by directional flow "
            "edges. Supports swimlanes for role/department assignment."
        ),
        answers="What happens, in what order, and who does it?",
        best_for=(
            "Business process modelling, standard operating procedures, workflow documentation, and process "
            "improvement."
        ),
        key_features=(
            "Activity, decision, and terminal nodes",
            "Directional flow edges",
            "Optional swimlane grouping",
        ),
        roadmap="not_planned",
        availability="planned",
    )
)

register_model_type(
    ModelTypeSpec(
        id="state_machine",
        display_name="State Machine / Statechart",
        short_name="FSM",
        description="States and transitions with guards and actions for reactive system modelling.",
        family="causal",
        summary=(
            "States connected by transitions with guards and actions. Models the reactive behaviour of a system —"
            " what events cause which state changes. Supports hierarchical (Harel) statecharts."
        ),
        answers="What states can the system be in, and what changes them?",
        best_for="Protocol specification, embedded system design, user-interface flow, and reactive system modelling.",
        key_features=(
            "States and guarded transitions",
            "Event-driven state changes",
            "Supports hierarchical (nested) states",
        ),
        roadmap="not_planned",
        availability="planned",
    )
)
