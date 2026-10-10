"""Built-in model type activations — executed at import time.

Registers the operation-side behaviours (validators, attribute
coercers) for the stable model types (CLD, DAG, FCM). The model type
specs themselves live in ``schema/model_types.py``.
"""

from __future__ import annotations

from typing import get_args

from latris.operations.activation import activate_model_type
from latris.schema import (
    FloatEntry,
    FloatSet,
    Polarity,
    PolarityEntry,
    PolaritySet,
    Substrate,
)

# ---------------------------------------------------------------------------
# Projection validators
# ---------------------------------------------------------------------------


def _check_dag_acyclicity(substrate: Substrate, edge_ids: list[str], paths) -> None:
    """Raise ValueError if the edges form a cycle.

    Filters to causal edges — non-causal kinds (decision_rule, governance,
    flow, ...) are not part of the DAG mechanism and don't count toward
    cycles.
    """
    from latris.operations._graph_checks import find_cycle
    from latris.operations.graph_analysis import causal_edges

    edges_in_view = causal_edges(e for e in substrate.edges if e.id in edge_ids)
    has_cycle, _ = find_cycle(edges_in_view)
    if has_cycle:
        raise ValueError("DAG view contains a cycle. Remove or redirect edges to make the graph acyclic.")


# ---------------------------------------------------------------------------
# Attribute coercion and entry factories
# ---------------------------------------------------------------------------


def _coerce_polarity(raw: str) -> str:
    if raw not in get_args(Polarity):
        raise ValueError(f"polarity must be '+', '-', or '~' (ambiguous), got {raw!r}")
    return raw


def _polarity_entry(target_id: str, value: str) -> PolarityEntry:
    return PolarityEntry(target_id=target_id, value=value)


def _coerce_fcm_weight(raw: str) -> float:
    try:
        val = float(raw)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"FCM weight must be a number, got {raw!r}") from exc
    if not (-1.0 <= val <= 1.0):
        raise ValueError(f"FCM weight must be in [-1, +1], got {val}")
    return val


def _fcm_weight_entry(target_id: str, value: float) -> FloatEntry:
    return FloatEntry(target_id=target_id, attribute="weight", value=value)


# ---------------------------------------------------------------------------
# Activate v1 stable model types
# ---------------------------------------------------------------------------

activate_model_type(
    "cld",
    attr_set_models={"polarity": PolaritySet},
    attr_coerce={"polarity": _coerce_polarity},
    attr_entry_factory={"polarity": _polarity_entry},
)

activate_model_type(
    "dag",
    projection_validators={"acyclicity": _check_dag_acyclicity},
)

activate_model_type(
    "fcm",
    attr_set_models={"weight": FloatSet},
    attr_coerce={"weight": _coerce_fcm_weight},
    attr_entry_factory={"weight": _fcm_weight_entry},
)
