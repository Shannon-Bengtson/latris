"""The substrate — the model-agnostic lingua franca (Layer 2).

Entities and edges here carry no formalism-specific meaning; views (CLD, DAG,
…) project roles and attributes onto them. ``causal_edges()`` in
``operations/graph_analysis.py`` consumes the mechanism-bearing edge kinds.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from latris.schema.common import ProvenanceOrigin, ProvenanceVerification
from latris.schema.maturity import Maturity

EntityKind = Literal[
    "concept",
    "variable",
    "event",
    "actor",
    "state",
    "decision",
    "hazard",
]
# Formalism-specific classifications (stock, chance, goal, gate, etc.)
# live in the view role layer — see schema/roles.py.

EdgeKind = Literal[
    "causal",
    "temporal",
    "decomposition",
    "conditional",
    # -- non-mechanism edges; excluded from loop / centrality analysis --
    # Decision rules, governance dependencies, and definitional
    # identities look like causal arrows in prose but represent
    # policy / accountability / identity links, not physical
    # mechanism. Including them in feedback-loop counts is the
    # capability-run inflation bug Phase 1 of the AI interrogation
    # layer is built to fix — analysis callers must filter via
    # `causal_edges()` in operations/graph_analysis.py.
    "decision_rule",  # policy / decision rule (e.g. budget allocation)
    "governance",  # ownership / accountability / oversight
    "definitional",  # identity / definitional relation (e.g. Output / Hours)
    # -- v2+ kinds for planned model types --
    "informational",  # non-causal information availability (Influence Diagram)
    "flow",  # material/information flow (System Dynamics, Flowchart)
    "support",  # evidence supporting claim/goal (Argument Map, GSN)
    "logical",  # AND/OR gate input (Fault Tree, Event Tree)
    "association",  # undirected/bidirectional (Concept Map, FCM)
]

# Canonical value sets, derived from the Literals so they never drift.
_ENTITY_KINDS: frozenset[str] = frozenset(EntityKind.__args__)  # type: ignore[attr-defined]
_EDGE_KINDS: frozenset[str] = frozenset(EdgeKind.__args__)  # type: ignore[attr-defined]

# Formalism role words an LLM or user may emit where a substrate *kind* is
# expected. Roles are not substrate kinds (they live in schema/roles.py); the
# 7 EntityKinds are canonical, so we map role words onto them rather than
# extend EntityKind. Keys are lower-cased.
_ROLE_TO_ENTITY_KIND: dict[str, EntityKind] = {
    "driver": "variable",
    "lever": "variable",
    "outcome": "variable",
    "stock": "variable",
    "auxiliary": "variable",
    "rate": "variable",
    "flow": "variable",
    "indicator": "variable",
    "metric": "variable",
    "source": "variable",
    "sink": "variable",
    "factor": "concept",
    "theme": "concept",
    "goal": "concept",
    "objective": "concept",
}


def coerce_entity_kind(value: str | None) -> tuple[EntityKind, bool]:
    """Map an arbitrary ``kind`` string onto a valid :data:`EntityKind`.

    Returns ``(kind, changed)`` where ``changed`` is True when the input was
    not already a canonical substrate kind. Valid kinds pass through; known
    formalism role words map to their substrate kind; anything else falls back
    to ``"concept"``. Case-insensitive.
    """
    if value in _ENTITY_KINDS:
        return value, False  # type: ignore[return-value]
    key = (value or "").strip().lower()
    if key in _ENTITY_KINDS:
        return key, True  # type: ignore[return-value]
    mapped = _ROLE_TO_ENTITY_KIND.get(key)
    if mapped is not None:
        return mapped, True
    return "concept", True


def coerce_edge_kind(value: str | None) -> tuple[EdgeKind, bool]:
    """Map an arbitrary ``kind`` string onto a valid :data:`EdgeKind`.

    Returns ``(kind, changed)``. Valid kinds pass through (case-insensitive);
    anything unrecognised falls back to ``"causal"``.
    """
    if value in _EDGE_KINDS:
        return value, False  # type: ignore[return-value]
    key = (value or "").strip().lower()
    if key in _EDGE_KINDS:
        return key, True  # type: ignore[return-value]
    return "causal", True


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Entity(_Base):
    id: str
    kind: EntityKind
    label: str
    maturity: Maturity = "proposed"
    origin: ProvenanceOrigin = "human-direct"
    verification: ProvenanceVerification = "unverified"
    source_id: str | None = None


class Edge(_Base):
    id: str
    from_id: str
    to_id: str
    kind: EdgeKind = "causal"
    maturity: Maturity = "proposed"
    origin: ProvenanceOrigin = "human-direct"
    verification: ProvenanceVerification = "unverified"
    source_id: str | None = None


class Substrate(_Base):
    """Layer 2 (lingua franca): entities + edges, formalism-free."""

    entities: list[Entity] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)


class Mapping(_Base):
    """Explicit link between a Layer-2 entity/edge and a Layer-3 view projection.

    Provenance lives in ``origin`` (``ai-proposed`` / ``human-direct`` / etc.);
    the workflow gate lives in ``maturity``. ``maturity == "approved"`` means
    a human has blessed the mapping — see docs/design/MATURITY_LADDER.md.
    """

    l2_id: str
    l3_view: str
    l3_id: str
    origin: ProvenanceOrigin = "human-direct"
    maturity: Maturity = "proposed"

    @field_validator("l3_view")
    @classmethod
    def _l3_view_must_be_registered(cls, value: str) -> str:
        from latris.schema.model_types import MODEL_TYPE_REGISTRY

        if value not in MODEL_TYPE_REGISTRY:
            known = sorted(MODEL_TYPE_REGISTRY)
            raise ValueError(f"Unknown view kind: {value!r}. Known: {known}")
        return value


class MappingRegistry(_Base):
    entries: list[Mapping] = Field(default_factory=list)
