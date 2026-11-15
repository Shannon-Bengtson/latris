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
        roadmap="not_planned",
        availability="planned",
        structural_validators=("bipartite",),
    )
)

# -- Tier 1: decision-making, risk, and communication formalisms -----------

register_model_type(
    ModelTypeSpec(
        id="markov",
        display_name="Markov Chain / MDP",
        short_name="MC",
        description="State-transition graph with transition probabilities and optional rewards.",
        roadmap="parked",
        availability="planned",
    )
)

register_model_type(
    ModelTypeSpec(
        id="influence_diagram",
        display_name="Influence Diagram",
        short_name="ID",
        description="Extension of Bayesian network with decision and utility nodes for decision analysis.",
        roadmap="parked",
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
        description="Sequential decision model with chance and decision nodes branching to outcomes.",
        roadmap="parked",
        availability="planned",
        structural_validators=("acyclicity",),
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
        roadmap="built",
        availability="stable",
        structural_validators=("acyclicity", "toc_levels_complete", "toc_links_forward", "toc_pathways_complete"),
        # Logic-model levels (W.K. Kellogg Foundation 2004). One per factor; the
        # outcome of interest is the impact, so there is no separate "outcome" role.
        allowed_roles=("input", "activity", "output", "short_term_outcome", "long_term_outcome", "impact"),
        required_roles=("activity", "impact"),
    )
)

# -- Tier 2: systems thinking, process, and state-based formalisms ---------

register_model_type(
    ModelTypeSpec(
        id="argument_map",
        display_name="Argument Map",
        short_name="AM",
        description="Toulmin/IBIS-style argumentation: claims, warrants, evidence, rebuttals.",
        roadmap="not_planned",
        availability="planned",
    )
)

register_model_type(
    ModelTypeSpec(
        id="fcm",
        display_name="Fuzzy Cognitive Map",
        short_name="FCM",
        description="Weighted directed graph with edge strengths in [\u22121, +1]; cycles allowed.",
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
        roadmap="not_planned",
        availability="planned",
    )
)
