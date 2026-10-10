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


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

MODEL_TYPE_REGISTRY: dict[str, ModelTypeSpec] = {}


def register_model_type(spec: ModelTypeSpec) -> None:
    """Add *spec* to the global registry. Raises on duplicate ID."""
    if spec.id in MODEL_TYPE_REGISTRY:
        raise ValueError(f"Duplicate model type ID: {spec.id!r}")
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
        availability="stable",
        model_attributes=("polarity",),
        structural_validators=("loops_present",),
    )
)

register_model_type(
    ModelTypeSpec(
        id="dag",
        display_name="Directed Acyclic Graph",
        short_name="DAG",
        description="Directed graph that must be acyclic; directionality mandatory.",
        availability="stable",
        structural_validators=("acyclicity",),
    )
)

register_model_type(
    ModelTypeSpec(
        id="bn",
        display_name="Bayesian Network",
        short_name="BN",
        description="DAG with state spaces and conditional probability tables.",
        availability="stable",
        structural_validators=("acyclicity", "state_space_defined", "cpt_complete"),
    )
)

# -- v2+ planned (visible in readiness panel but not switchable) -----------

register_model_type(
    ModelTypeSpec(
        id="sd",
        display_name="System Dynamics",
        short_name="SD",
        description="Stocks, flows, and feedback loops with ODE equations (v2).",
        availability="planned",
    )
)

register_model_type(
    ModelTypeSpec(
        id="causal_dag",
        display_name="Causal DAG",
        short_name="CDAG",
        description="DAG with observed/unobserved classification and adjustment sets (v2).",
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
            "Doubles as the quantification of causal/DAG edges (v2)."
        ),
        availability="planned",
        structural_validators=("acyclicity",),
    )
)

register_model_type(
    ModelTypeSpec(
        id="gsn",
        display_name="Goal Structuring Notation",
        short_name="GSN",
        description="Safety-case argumentation: goals, strategies, solutions, context (v3+).",
        availability="planned",
    )
)

register_model_type(
    ModelTypeSpec(
        id="bow_tie",
        display_name="Bow-Tie Diagram",
        short_name="BT",
        description="Threat\u2013barrier\u2013consequence topology for risk analysis (v3+).",
        availability="planned",
    )
)

register_model_type(
    ModelTypeSpec(
        id="fault_tree",
        display_name="Fault Tree",
        short_name="FT",
        description="Top-down failure decomposition with AND/OR logic gates (v3+).",
        availability="planned",
        structural_validators=("acyclicity",),
    )
)

register_model_type(
    ModelTypeSpec(
        id="petri_net",
        display_name="Petri Net",
        short_name="PN",
        description="Bipartite graph of places and transitions for concurrent systems (v3+).",
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
        description="State-transition graph with transition probabilities and optional rewards (v2+).",
        availability="planned",
    )
)

register_model_type(
    ModelTypeSpec(
        id="influence_diagram",
        display_name="Influence Diagram",
        short_name="ID",
        description="Extension of Bayesian network with decision and utility nodes for decision analysis (v3+).",
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
        description="Sequential decision model with chance and decision nodes branching to outcomes (v3+).",
        availability="planned",
        structural_validators=("acyclicity",),
    )
)

register_model_type(
    ModelTypeSpec(
        id="event_tree",
        display_name="Event Tree",
        short_name="ET",
        description="Forward-logic tree from initiating event through barriers to outcomes for safety analysis (v3+).",
        availability="planned",
        structural_validators=("acyclicity",),
    )
)

register_model_type(
    ModelTypeSpec(
        id="fishbone",
        display_name="Ishikawa / Fishbone Diagram",
        short_name="FB",
        description="Root cause analysis diagram with categorised cause branches converging on an effect (v3+).",
        availability="planned",
        structural_validators=("acyclicity",),
    )
)

register_model_type(
    ModelTypeSpec(
        id="theory_of_change",
        display_name="Theory of Change",
        short_name="ToC",
        description="Logic model linking activities through outputs and outcomes to long-term goals (v3+).",
        availability="planned",
        structural_validators=("acyclicity",),
    )
)

# -- Tier 2: systems thinking, process, and state-based formalisms ---------

register_model_type(
    ModelTypeSpec(
        id="argument_map",
        display_name="Argument Map",
        short_name="AM",
        description="Toulmin/IBIS-style argumentation: claims, warrants, evidence, rebuttals (v3+).",
        availability="planned",
    )
)

register_model_type(
    ModelTypeSpec(
        id="fcm",
        display_name="Fuzzy Cognitive Map",
        short_name="FCM",
        description="Weighted directed graph with edge strengths in [\u22121, +1]; cycles allowed.",
        availability="stable",
        model_attributes=("weight",),
    )
)

register_model_type(
    ModelTypeSpec(
        id="flowchart",
        display_name="Process Map / Flowchart",
        short_name="FC",
        description="Activity-decision-outcome flow for process modelling (v3+).",
        availability="planned",
    )
)

register_model_type(
    ModelTypeSpec(
        id="state_machine",
        display_name="State Machine / Statechart",
        short_name="FSM",
        description="States and transitions with guards and actions for reactive system modelling (v3+).",
        availability="planned",
    )
)
