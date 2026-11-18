"""Which factors and links belong to each model type — one rule for every reader.

A project is one map (the substrate) that can be several model types at once: a
causal loop diagram, a system dynamics simulation and a Bayesian network can
share it. Readiness, result staleness, interpretation claims, the handover
check and the report's diagrams all ask the same question — *what is this model
type made of?* — and they must get the same answer, or a loop-map edit ages a
simulation result and the loop map's feedback loops count as cycles in the
network.

The rule:

- Explicit view mappings (``mappings.yaml``) win when a model type has any.
- A **system dynamics** model is the factors with an SD role, plus anything a
  flow edge touches, and the links among them.
- A **Bayesian network** is the factors with states or a probability table
  (and those tables' parents), and the links among them.
- The qualitative types (CLD, DAG, FCM) are the whole map.

So a factor joins the simulation when it gets an SD role and the network when
it gets states; everything else stays in the loop map.

:func:`members` is what a model type *computes on*. :func:`check_scope` is what
its readiness checks look at: the same set when the model shares its map with a
qualitative type, but the whole map when the model is only that type — in a
model that is only a network, a factor without states is a gap to fill, not a
loop-map factor to leave alone.
"""

from __future__ import annotations

from dataclasses import dataclass

from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model

QUANTIFIED = ("sd", "bn")
QUALITATIVE = ("cld", "dag", "fcm")
WHOLE_MAP = "system_map"


@dataclass(frozen=True)
class Members:
    entity_ids: frozenset[str]
    edge_ids: frozenset[str]

    @property
    def ids(self) -> frozenset[str]:
        return self.entity_ids | self.edge_ids


def _substrate(paths: ProjectPaths):
    from latris.schema import Substrate

    return load_model(Substrate, paths.conceptual_yaml)


def _mapped(paths: ProjectPaths, model_type: str) -> set[str]:
    from latris.schema import MappingRegistry

    if not paths.mappings_yaml.exists():
        return set()
    registry = load_model(MappingRegistry, paths.mappings_yaml)
    return {m.l2_id for m in registry.entries if m.l3_view == model_type}


def parameterised_nodes(paths: ProjectPaths, model_type: str) -> set[str]:
    """The factors a quantified model type computes on (empty for the qualitative types)."""
    from latris.operations import formalisms

    plugin = formalisms.get(model_type)
    return plugin.parameterised_nodes(paths) if plugin and plugin.parameterised_nodes else set()


def _with_links(paths: ProjectPaths, nodes: set[str]) -> Members:
    substrate = _substrate(paths)
    known = {e.id for e in substrate.entities}
    nodes = nodes & known
    edges = {e.id for e in substrate.edges if e.from_id in nodes and e.to_id in nodes}
    return Members(frozenset(nodes), frozenset(edges))


def shares_map(paths: ProjectPaths, model_type: str) -> bool:
    """True when ``model_type`` shares the project's map with a qualitative model type (a loop map, DAG or FCM)."""
    from latris.schema import ProjectFoundation

    if model_type not in QUANTIFIED or not paths.project_yaml.exists():
        return False
    selected = load_model(ProjectFoundation, paths.project_yaml).selected_model_types
    return any(t in QUALITATIVE for t in selected)


def members(paths: ProjectPaths, model_type: str | None) -> Members | None:
    """What ``model_type`` computes on, or ``None`` for the whole map.

    A quantified type with no parameters yet is empty when it shares the map with a qualitative
    type (nothing has joined it yet) and the whole map otherwise.
    """
    if not model_type or model_type == WHOLE_MAP:
        return None
    mapped = _mapped(paths, model_type)
    if model_type in QUANTIFIED:
        # Mappings can add to what a simulation or network computes on, never take away from it.
        substrate = _substrate(paths)
        nodes = parameterised_nodes(paths, model_type) | {e.id for e in substrate.entities if e.id in mapped}
        if nodes or shares_map(paths, model_type):
            found = _with_links(paths, nodes)
            extra = {e.id for e in substrate.edges if e.id in mapped}
            return Members(found.entity_ids, found.edge_ids | extra)
        return None
    if mapped:
        substrate = _substrate(paths)
        nodes = {e.id for e in substrate.entities if e.id in mapped}
        edges = {e.id for e in substrate.edges if e.id in mapped}
        return Members(frozenset(nodes), frozenset(edges))
    return None


def check_scope(paths: ProjectPaths, model_type: str) -> Members | None:
    """What ``model_type``'s readiness checks look at (``None``: the whole map). See the module docstring."""
    if model_type in QUANTIFIED:
        return members(paths, model_type) if shares_map(paths, model_type) else None
    return members(paths, model_type)


def outside_links(paths: ProjectPaths, model_type: str) -> list[tuple[str, str, str]]:
    """Causal links from outside a quantified model into it: ``(edge id, from label, to label)``.

    They stay in the loop map; the simulation or network doesn't use them. Reported as advisories.
    """
    scope = members(paths, model_type)
    if scope is None:
        return []
    substrate = _substrate(paths)
    labels = {e.id: e.label for e in substrate.entities}
    return [
        (e.id, labels.get(e.from_id, e.from_id), labels.get(e.to_id, e.to_id))
        for e in substrate.edges
        if e.to_id in scope.entity_ids and e.from_id not in scope.entity_ids and e.kind != "flow"
    ]
