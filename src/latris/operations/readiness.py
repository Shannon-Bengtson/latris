"""Readiness assessment — per-model-type readiness scores and gap analysis.

Uses the model type registry to compute readiness for each formal view.
Hard-block: ``can_switch`` is True only when score == 100 AND the registry
spec's ``availability == "stable"``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Ensure activations are loaded so ATTR_SET_MODELS is populated.
import latris.operations._activations  # noqa: F401
from latris.operations.activation import ATTR_SET_MODELS
from latris.repo.project import require_project
from latris.repo.yaml_io import load_model
from latris.schema import Substrate
from latris.schema.model_types import (
    ModelTypeSpec,
    get_model_type,
    list_model_types,
)
from latris.schema.roles import RoleSet


@dataclass
class ReadinessGap:
    element_id: str
    element_label: str
    gap_type: str
    message: str


@dataclass
class ModelTypeReadiness:
    model_type_id: str
    display_name: str
    short_name: str
    description: str
    availability: str  # "stable" | "planned" — registry switchability
    score: int
    can_switch: bool
    gaps: list[ReadinessGap] = field(default_factory=list)
    summary: str = ""


@dataclass(frozen=True)
class ValidationContext:
    """Everything a structural validator or readiness checker needs.

    Introduced so that future validators (algebraic-loop-free for SD,
    row-stochastic for Markov, etc.) can access roles, parameters, and
    settings without changing every call site.  Existing validators
    simply ignore the fields they don't need.
    """

    substrate: Substrate
    view_entity_ids: list[str]
    view_edge_ids: list[str]
    spec: ModelTypeSpec
    roles: RoleSet
    paths: object  # ProjectPaths (untyped to avoid circular import)


# ---------------------------------------------------------------------------
# Structural validators
# ---------------------------------------------------------------------------


def _check_acyclicity(ctx: ValidationContext) -> list[ReadinessGap]:
    """Check for cycles in the given edges. Returns gaps if cycles exist.

    Filters to causal edges — non-causal kinds (decision_rule, governance,
    flow, ...) are not mechanism and don't count toward DAG acyclicity.
    """
    from latris.operations._graph_checks import find_cycle
    from latris.operations.graph_analysis import causal_edges

    edges_in_view = causal_edges(e for e in ctx.substrate.edges if e.id in ctx.view_edge_ids)
    has_cycle, node_id = find_cycle(edges_in_view)
    if has_cycle:
        labels = {e.id: e.label for e in ctx.substrate.entities}
        return [
            ReadinessGap(
                element_id=node_id,
                element_label=labels.get(node_id, node_id),
                gap_type="cycle_detected",
                message="Graph contains a cycle. Remove or redirect edges to make it acyclic.",
            )
        ]
    return []


def _check_loops_present(ctx: ValidationContext) -> list[ReadinessGap]:
    """Check that ≥1 feedback loop exists. Required for CLDs — loops are the
    defining feature of a Causal Loop Diagram, so an acyclic CLD is treated as
    incomplete.

    Filters to causal edges — a "loop" composed of decision_rule or
    governance edges is policy structure, not feedback mechanism, and
    does not satisfy the CLD readiness gate.
    """
    from latris.operations.graph_analysis import causal_edges, find_all_loops

    edges_in_view = causal_edges(e for e in ctx.substrate.edges if e.id in ctx.view_edge_ids)
    loops = find_all_loops(edges_in_view)
    if not loops:
        return [
            ReadinessGap(
                element_id="",
                element_label="(model)",
                gap_type="no_loops",
                message=(
                    "CLD has no feedback loops. Loops are the defining feature "
                    "of CLDs — propose at least one reinforcing or balancing "
                    "loop, or reconsider whether DAG is the appropriate model "
                    "type."
                ),
            )
        ]
    return []


def _bn_parent_map(ctx: ValidationContext) -> tuple[set[str], dict[str, list[str]]]:
    """BN node set + ordered parents, from the causal-edge projection.

    A BN node is any entity touched by a causal edge in the view. Parents are
    deduplicated while preserving first-seen edge order (defines CPT column
    order). Non-causal edge kinds (governance, flow, ...) are not mechanism and
    are excluded — matching how the DAG/CLD validators treat the substrate.
    """
    from latris.operations.graph_analysis import causal_edges

    edge_set = set(ctx.view_edge_ids)
    edges = list(causal_edges(e for e in ctx.substrate.edges if e.id in edge_set))
    nodes: set[str] = set()
    parents: dict[str, list[str]] = {}
    for e in edges:
        nodes.add(e.from_id)
        nodes.add(e.to_id)
        parents.setdefault(e.to_id, []).append(e.from_id)
    # Dedupe parents, preserve order.
    parents = {nid: list(dict.fromkeys(ps)) for nid, ps in parents.items()}
    return nodes, parents


def _check_state_space_defined(ctx: ValidationContext) -> list[ReadinessGap]:
    """Every chance node in the BN must declare a discrete state space."""
    from latris.schema.bn import StateSpaceSet

    ss_path = ctx.paths.view_attribute_path(ctx.spec.id, "state_space")
    store = load_model(StateSpaceSet, ss_path) if ss_path.exists() else StateSpaceSet()
    have = {e.target_id for e in store.entries}

    nodes, _ = _bn_parent_map(ctx)
    labels = {e.id: e.label for e in ctx.substrate.entities}
    gaps: list[ReadinessGap] = []
    for nid in sorted(nodes):
        if nid not in have:
            gaps.append(
                ReadinessGap(
                    element_id=nid,
                    element_label=labels.get(nid, nid),
                    gap_type="missing_state_space",
                    message="Node has no state space. Define its discrete states (e.g. 'low,high').",
                )
            )
    return gaps


def _check_cpt_complete(ctx: ValidationContext) -> list[ReadinessGap]:
    """Every BN node needs a CPT covering all parent-state combinations,
    with each conditional distribution normalised to 1 (±1e-6).

    State-space gaps are reported by ``_check_state_space_defined``; nodes
    still missing a state space here are skipped to avoid duplicate noise.
    """
    import itertools

    from latris.operations._bn_canonical import expand_noisy_or
    from latris.schema.bn import CPTSet, NoisyOrSet, StateSpaceSet

    ss_path = ctx.paths.view_attribute_path(ctx.spec.id, "state_space")
    cpt_path = ctx.paths.view_attribute_path(ctx.spec.id, "cpt")
    noisy_path = ctx.paths.view_attribute_path(ctx.spec.id, "noisy_or")
    ss = load_model(StateSpaceSet, ss_path) if ss_path.exists() else StateSpaceSet()
    cpts = load_model(CPTSet, cpt_path) if cpt_path.exists() else CPTSet()
    noisy = load_model(NoisyOrSet, noisy_path) if noisy_path.exists() else NoisyOrSet()
    ss_map = {e.target_id: e.states for e in ss.entries}
    cpt_map = {e.target_id: e for e in cpts.entries}

    # Expand canonical (Noisy-OR) specs into the effective CPT map. A node with
    # a valid spec counts as having a complete, normalised CPT.
    canonical_problems: dict[str, str] = {}
    for ne in noisy.entries:
        if ne.target_id in cpt_map:
            canonical_problems[ne.target_id] = (
                "Node has both a tabular CPT and a Noisy-OR spec; keep only one."
            )
            continue
        try:
            cpt_map[ne.target_id] = expand_noisy_or(ne, ss_map)
        except Exception as exc:  # malformed spec — surface as a readiness gap
            canonical_problems[ne.target_id] = f"Invalid Noisy-OR spec: {exc}"

    nodes, parent_map = _bn_parent_map(ctx)
    labels = {e.id: e.label for e in ctx.substrate.entities}
    gaps: list[ReadinessGap] = []

    for nid in sorted(nodes):
        if nid in canonical_problems:
            gaps.append(
                ReadinessGap(
                    element_id=nid,
                    element_label=labels.get(nid, nid),
                    gap_type="cpt_conflict",
                    message=canonical_problems[nid],
                )
            )
            continue
        cpt = cpt_map.get(nid)
        if cpt is None:
            gaps.append(
                ReadinessGap(
                    element_id=nid,
                    element_label=labels.get(nid, nid),
                    gap_type="missing_cpt",
                    message="Node has no conditional probability table.",
                )
            )
            continue

        parents = parent_map.get(nid, [])
        if nid not in ss_map or any(p not in ss_map for p in parents):
            continue  # state-space gap already reported; can't judge completeness

        expected = set(itertools.product(*[ss_map[p] for p in parents])) if parents else {()}
        seen: set[tuple[str, ...]] = set()
        unnormalised = False
        for row in cpt.rows:
            try:
                key = tuple(row.parent_states[p] for p in parents)
            except KeyError:
                continue  # row doesn't match this node's parents; counts as missing combo
            seen.add(key)
            if abs(sum(row.p) - 1.0) > 1e-6:
                unnormalised = True

        missing = expected - seen
        if missing:
            gaps.append(
                ReadinessGap(
                    element_id=nid,
                    element_label=labels.get(nid, nid),
                    gap_type="cpt_incomplete",
                    message=f"CPT is missing {len(missing)} of {len(expected)} parent-state combination(s).",
                )
            )
        if unnormalised:
            gaps.append(
                ReadinessGap(
                    element_id=nid,
                    element_label=labels.get(nid, nid),
                    gap_type="cpt_unnormalised",
                    message="A CPT row for this node does not sum to 1.0.",
                )
            )
    return gaps


# ── System Dynamics ──────────────────────────────────────────────────
#
# One analysis (operations/sd_inference.analyse) produces every SD problem,
# tagged by category; each validator below reports one category. That keeps a
# single definition of "well-formed SD model" shared by readiness, `sd check`,
# and the simulator, which refuses to compile while any problem remains.


def _sd_problems(ctx: ValidationContext, categories: frozenset[str]) -> list[ReadinessGap]:
    from latris.operations import sd_inference
    from latris.schema.sd import SDConstantSet, SDEquationSet, SDStockSet, SDTableSet

    def _load(cls, attribute: str):
        path = ctx.paths.view_attribute_path(ctx.spec.id, attribute)
        return load_model(cls, path) if path.exists() else cls()

    _, problems = sd_inference.analyse(
        ctx.substrate,
        ctx.roles,
        _load(SDEquationSet, "equations"),
        _load(SDStockSet, "initial_value"),
        _load(SDConstantSet, "constant"),
        _load(SDTableSet, "table"),
        entity_ids=ctx.view_entity_ids,
        edge_ids=ctx.view_edge_ids,
    )
    labels = {e.id: e.label for e in ctx.substrate.entities}
    labels.update(
        {e.id: f"{labels.get(e.from_id, e.from_id)} → {labels.get(e.to_id, e.to_id)}" for e in ctx.substrate.edges}
    )
    return [
        ReadinessGap(
            element_id=p.target_id,
            element_label=labels.get(p.target_id, p.target_id or "(model)"),
            gap_type=p.gap_type,
            message=p.message,
        )
        for p in problems
        if p.gap_type in categories
    ]


def _check_sd_classification_complete(ctx: ValidationContext) -> list[ReadinessGap]:
    """The model has a stock, and every entity on a flow edge or feeding the model has an SD role."""
    from latris.operations.sd_inference import CLASSIFICATION_GAPS

    return _sd_problems(ctx, CLASSIFICATION_GAPS)


def _check_sd_flow_connects_stock(ctx: ValidationContext) -> list[ReadinessGap]:
    """Flows fill or drain a stock; flow edges run stock/cloud ↔ flow; stocks take no causal input."""
    from latris.operations.sd_inference import FLOW_GAPS

    return _sd_problems(ctx, FLOW_GAPS)


def _check_sd_no_algebraic_loops(ctx: ValidationContext) -> list[ReadinessGap]:
    """No dependency cycle among flows/auxiliaries — only stocks may close a loop."""
    from latris.operations.sd_inference import LOOP_GAPS

    return _sd_problems(ctx, LOOP_GAPS)


def _check_sd_equations_complete(ctx: ValidationContext) -> list[ReadinessGap]:
    """Every flow/auxiliary has a parseable equation whose references match the diagram's links."""
    from latris.operations.sd_inference import EQUATION_GAPS

    return _sd_problems(ctx, EQUATION_GAPS)


def _check_sd_values_complete(ctx: ValidationContext) -> list[ReadinessGap]:
    """Every stock has an initial value and every constant a value."""
    from latris.operations.sd_inference import VALUE_GAPS

    return _sd_problems(ctx, VALUE_GAPS)


def _check_sd_tables_well_formed(ctx: ValidationContext) -> list[ReadinessGap]:
    """TABLE() calls and table definitions match one-to-one."""
    from latris.operations.sd_inference import TABLE_GAPS

    return _sd_problems(ctx, TABLE_GAPS)


def _check_sd_dimensional_consistency(ctx: ValidationContext) -> list[ReadinessGap]:
    """Units parse, flows match their stocks per time unit, and every equation evaluates in its declared units."""
    from latris.operations.sd_inference import UNIT_GAPS

    return _sd_problems(ctx, UNIT_GAPS)


SD_VALIDATORS: tuple[str, ...] = (
    "sd_classification_complete",
    "sd_flow_connects_stock",
    "sd_no_algebraic_loops",
    "sd_equations_complete",
    "sd_values_complete",
    "sd_tables_well_formed",
    "sd_dimensional_consistency",
)


_STRUCTURAL_VALIDATORS: dict[str, object] = {
    "acyclicity": _check_acyclicity,
    "loops_present": _check_loops_present,
    "state_space_defined": _check_state_space_defined,
    "cpt_complete": _check_cpt_complete,
    "sd_classification_complete": _check_sd_classification_complete,
    "sd_flow_connects_stock": _check_sd_flow_connects_stock,
    "sd_no_algebraic_loops": _check_sd_no_algebraic_loops,
    "sd_equations_complete": _check_sd_equations_complete,
    "sd_values_complete": _check_sd_values_complete,
    "sd_tables_well_formed": _check_sd_tables_well_formed,
    "sd_dimensional_consistency": _check_sd_dimensional_consistency,
    # Future: "bipartite", etc.
}


# ---------------------------------------------------------------------------
# Attribute checkers
# ---------------------------------------------------------------------------


def _check_model_attributes(
    spec: ModelTypeSpec,
    paths,
    edge_ids: set[str],
    entity_ids: set[str],
    substrate: Substrate,
    *,
    attribute_names: tuple[str, ...] | None = None,
) -> tuple[int, int, list[ReadinessGap]]:
    """Check model-specific attributes. Returns (met, total, gaps).

    When *attribute_names* is ``None`` (default) the check uses
    ``spec.required_model_attributes`` (Build→Analyse gate).  Callers
    that need a stricter check (e.g. Analyse→Interpret) pass
    ``spec.model_attributes`` explicitly.
    """
    attrs_to_check = attribute_names if attribute_names is not None else spec.required_model_attributes
    if not attrs_to_check:
        return 0, 0, []

    labels = {e.id: e.label for e in substrate.entities}
    labels.update({e.id: f"{e.from_id[:8]}→{e.to_id[:8]}" for e in substrate.edges})

    total = 0
    met = 0
    gaps: list[ReadinessGap] = []

    for attr_name in attrs_to_check:
        model_cls = ATTR_SET_MODELS.get(attr_name)
        if model_cls is None:
            continue

        file_path = paths.view_attribute_path(spec.id, attr_name)
        store = model_cls() if not file_path.exists() else load_model(model_cls, file_path)
        has_attr = {e.target_id for e in store.entries if e.attribute == attr_name}

        # All current model attributes (polarity, weight) apply to edges.
        target_ids = edge_ids
        for tid in target_ids:
            total += 1
            if tid in has_attr:
                met += 1
            else:
                gaps.append(
                    ReadinessGap(
                        element_id=tid,
                        element_label=labels.get(tid, tid),
                        gap_type=f"missing_{attr_name}",
                        message=f"Missing {attr_name} attribute.",
                    )
                )

    return met, total, gaps


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def assess_readiness(
    model_type_id: str,
    *,
    root: Path | None = None,
) -> ModelTypeReadiness:
    """Compute readiness for a single model type."""
    spec = get_model_type(model_type_id)

    if spec.availability == "planned":
        return ModelTypeReadiness(
            model_type_id=spec.id,
            display_name=spec.display_name,
            short_name=spec.short_name,
            description=spec.description,
            availability=spec.availability,
            score=0,
            can_switch=False,
            summary="Planned for a future release.",
        )

    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)

    entity_ids = {e.id for e in substrate.entities}
    edge_ids = {e.id for e in substrate.edges}
    all_edge_ids = list(edge_ids)

    # Load roles for this model type (empty if file doesn't exist yet).
    role_path = paths.role_path(spec.id)
    roles = load_model(RoleSet, role_path) if role_path.exists() else RoleSet()

    ctx = ValidationContext(
        substrate=substrate,
        view_entity_ids=list(entity_ids),
        view_edge_ids=all_edge_ids,
        spec=spec,
        roles=roles,
        paths=paths,
    )

    gaps: list[ReadinessGap] = []

    # 1. Structural validators
    structural_ok = True
    for validator_name in spec.structural_validators:
        validator_fn = _STRUCTURAL_VALIDATORS.get(validator_name)
        if validator_fn is None:
            continue
        validator_gaps = validator_fn(ctx)
        if validator_gaps:
            structural_ok = False
            gaps.extend(validator_gaps)

    # 2. Model-specific attributes
    attr_met, attr_total, attr_gaps = _check_model_attributes(
        spec,
        paths,
        edge_ids,
        entity_ids,
        substrate,
    )
    gaps.extend(attr_gaps)

    # Score calculation
    if attr_total == 0 and structural_ok:
        score = 100
    elif attr_total == 0 and not structural_ok:
        score = 0
    elif not structural_ok:
        score = 0  # structural failure = 0 regardless of attributes
    else:
        score = int(100 * attr_met / attr_total)

    can_switch = score == 100 and spec.availability == "stable"

    # Summary
    if can_switch:
        summary = f"Ready to switch to {spec.display_name}."
    else:
        parts = []
        if not structural_ok:
            parts.append("structural constraint violation")
        if attr_gaps:
            parts.append(f"{len(attr_gaps)} element(s) missing required attributes")
        summary = f"Not ready: {'; '.join(parts)}." if parts else "Not ready."

    return ModelTypeReadiness(
        model_type_id=spec.id,
        display_name=spec.display_name,
        short_name=spec.short_name,
        description=spec.description,
        availability=spec.availability,
        score=score,
        can_switch=can_switch,
        gaps=gaps,
        summary=summary,
    )


def assess_all_readiness(
    *,
    root: Path | None = None,
    include_planned: bool = True,
) -> list[ModelTypeReadiness]:
    """Compute readiness for all registered model types."""
    specs = list_model_types(include_planned=include_planned)
    return [assess_readiness(spec.id, root=root) for spec in specs]


@dataclass
class BuildPhaseReadiness:
    """Readiness assessment for the Build→Model transition.

    Contains per-selected-model-type readiness and a composite score.
    """

    selected_model_types: list[str]
    model_scores: dict[str, ModelTypeReadiness]
    composite_score: int  # 0-100; average of selected model scores, -1 if none selected
    summary: str


@dataclass
class InterpretReadiness:
    """Readiness assessment for the Model→Interpret transition.

    Requires at least one selected model type to be fully ready
    (can_switch = True) — meaning the model is structurally complete
    enough for interpretation.
    """

    can_enter: bool
    score: int  # 0-100
    summary: str
    missing: list[str] = field(default_factory=list)


@dataclass
class TransitionStatus:
    """Traffic-light state for a single phase transition."""

    from_phase: str
    to_phase: str
    light: str  # "red" | "yellow" | "green"
    summary: str
    details: list[str] = field(default_factory=list)


@dataclass
class TransitionReadiness:
    """All phase-transition states (home→build … interpret→communicate)."""

    transitions: list[TransitionStatus]


def assess_interpret_readiness(
    *,
    root: Path | None = None,
) -> InterpretReadiness:
    """Compute whether the project is ready to enter the Interpret phase.

    Gate: at least one selected model type must have can_switch = True,
    meaning the model is structurally complete for that formalism.
    For CLD this means polarity is set; for DAG, acyclicity holds; etc.
    """
    from latris.schema import ProjectFoundation

    paths = require_project(root)
    foundation = load_model(ProjectFoundation, paths.project_yaml)
    selected = foundation.selected_model_types

    if not selected:
        return InterpretReadiness(
            can_enter=False,
            score=0,
            summary="No model types selected.",
            missing=["Select at least one model type."],
        )

    # Check model readiness for each selected type
    ready_types: list[str] = []
    not_ready_types: list[str] = []
    for model_type_id in selected:
        readiness = assess_readiness(model_type_id, root=root)
        if readiness.can_switch:
            ready_types.append(readiness.display_name)
        else:
            not_ready_types.append(readiness.display_name)

    can_enter = len(ready_types) > 0

    if can_enter:
        score = 100
        summary = f"Ready for interpretation ({', '.join(ready_types)})."
    else:
        score = 0
        summary = "No model types are ready yet."

    missing: list[str] = []
    if not can_enter:
        missing.append("Complete at least one model type (e.g. set polarity on all CLD edges).")

    return InterpretReadiness(
        can_enter=can_enter,
        score=score,
        summary=summary,
        missing=missing,
    )


def assess_build_readiness(
    *,
    root: Path | None = None,
) -> BuildPhaseReadiness:
    """Compute Build-phase readiness based on the project's selected model types."""
    from latris.schema import ProjectFoundation

    paths = require_project(root)
    foundation = load_model(ProjectFoundation, paths.project_yaml)
    selected = foundation.selected_model_types

    if not selected:
        return BuildPhaseReadiness(
            selected_model_types=[],
            model_scores={},
            composite_score=-1,
            summary="No model types selected.",
        )

    scores: dict[str, ModelTypeReadiness] = {}
    for mid in selected:
        scores[mid] = assess_readiness(mid, root=root)

    total = sum(r.score for r in scores.values())
    composite = int(total / len(scores))

    ready = [r for r in scores.values() if r.can_switch]
    not_ready = [r for r in scores.values() if not r.can_switch]
    parts = []
    if ready:
        parts.append(f"{len(ready)} model(s) ready")
    if not_ready:
        parts.append(f"{len(not_ready)} model(s) pending")
    summary = "; ".join(parts) or "No model types selected."

    return BuildPhaseReadiness(
        selected_model_types=selected,
        model_scores=scores,
        composite_score=composite,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Phase-transition readiness (traffic-light system)
# ---------------------------------------------------------------------------


def _assess_home_to_build(paths) -> TransitionStatus:
    """Home → Build: a modelling question must be defined.

    Build is the first phase; its only precondition is that the project
    has a modelling question (set on the home/overview screen). Evidence
    is now an always-on resource, not a gate.
    """
    from latris.schema import ProjectFoundation

    foundation = load_model(ProjectFoundation, paths.project_yaml)
    has_question = bool(foundation.statement and foundation.statement.strip())

    if not has_question:
        return TransitionStatus(
            from_phase="home",
            to_phase="build",
            light="red",
            summary="Define a modelling question to begin.",
            details=["Set the modelling question on the project home screen."],
        )
    return TransitionStatus(
        from_phase="home",
        to_phase="build",
        light="green",
        summary="Ready to build.",
    )


_MIN_NODES_FOR_FORMALISE = 3


def _assess_build_to_formalise(paths) -> TransitionStatus:
    """Build → Formalise: a minimal, fully-connected structure.

    Requires at least ``_MIN_NODES_FOR_FORMALISE`` nodes and a single
    weakly-connected network — no orphan nodes and no disjoint sub-graphs.
    """
    from latris.operations.graph_analysis import weakly_connected_components

    substrate = load_model(Substrate, paths.conceptual_yaml)
    entities = substrate.entities
    edges = substrate.edges
    n_nodes = len(entities)

    if n_nodes < _MIN_NODES_FOR_FORMALISE:
        return TransitionStatus(
            from_phase="build",
            to_phase="formalise",
            light="red",
            summary="Build a minimal causal structure before formalising.",
            details=[f"Add at least {_MIN_NODES_FOR_FORMALISE} nodes (currently {n_nodes})."],
        )

    node_ids = [e.id for e in entities]
    label_by_id = {e.id: e.label for e in entities}
    components = weakly_connected_components(node_ids, edges)

    if len(components) > 1:
        if all(len(c) == 1 for c in components):
            return TransitionStatus(
                from_phase="build",
                to_phase="formalise",
                light="red",
                summary="Connect your nodes into a single network before formalising.",
                details=["Add edges — no nodes are connected yet."],
            )
        _main, *rest = sorted(components, key=len, reverse=True)
        orphan_ids = [nid for comp in rest for nid in comp]
        names = [label_by_id.get(nid, nid) for nid in orphan_ids]
        return TransitionStatus(
            from_phase="build",
            to_phase="formalise",
            light="red",
            summary="Connect all nodes into a single network before formalising.",
            details=[f"Not connected to the main network: {', '.join(names)}"],
        )

    return TransitionStatus(
        from_phase="build",
        to_phase="formalise",
        light="green",
        summary="Structure is connected — ready to formalise.",
    )


def _assess_formalise_to_analyse(paths) -> TransitionStatus:
    """Formalise → Analyse: at least one selected model type is fully
    parameterised — structural validators pass AND every model_attribute
    is populated (e.g. polarity on every CLD causal edge).

    Formalise is where parameterisation happens, so the gate out of it
    requires a complete formal model that Analyse can interrogate.
    """
    from latris.schema import ProjectFoundation

    foundation = load_model(ProjectFoundation, paths.project_yaml)
    selected = foundation.selected_model_types

    if not selected:
        return TransitionStatus(
            from_phase="formalise",
            to_phase="analyse",
            light="red",
            summary="Select and parameterise at least one model type.",
            details=["No model types selected."],
        )

    substrate = load_model(Substrate, paths.conceptual_yaml)
    entity_ids = {e.id for e in substrate.entities}
    edge_ids = {e.id for e in substrate.edges}

    ready: list[str] = []
    not_ready: list[str] = []
    details: list[str] = []

    for mid in selected:
        spec = get_model_type(mid)
        if spec.availability == "planned":
            continue

        roles_path = paths.role_path(spec.id)
        roles = load_model(RoleSet, roles_path) if roles_path.exists() else RoleSet()
        ctx = ValidationContext(
            substrate=substrate,
            view_entity_ids=list(entity_ids),
            view_edge_ids=list(edge_ids),
            spec=spec,
            roles=roles,
            paths=paths,
        )
        structural_ok = True
        for vname in spec.structural_validators:
            vfn = _STRUCTURAL_VALIDATORS.get(vname)
            if vfn and vfn(ctx):
                structural_ok = False
                break

        attr_met, attr_total, _gaps = _check_model_attributes(
            spec,
            paths,
            edge_ids,
            entity_ids,
            substrate,
            attribute_names=spec.model_attributes,
        )

        model_complete = structural_ok and (attr_total == 0 or attr_met == attr_total)

        if model_complete:
            ready.append(spec.short_name)
        else:
            not_ready.append(spec.short_name)
            if not structural_ok:
                details.append(f"{spec.short_name}: structural constraint violation.")
            if attr_total > 0 and attr_met < attr_total:
                details.append(f"{spec.short_name}: {attr_total - attr_met} edge(s) missing attributes.")

    if not ready:
        return TransitionStatus(
            from_phase="formalise",
            to_phase="analyse",
            light="red",
            summary="Parameterise a model before analysing.",
            details=details or ["No model types are fully parameterised."],
        )

    if not_ready:
        return TransitionStatus(
            from_phase="formalise",
            to_phase="analyse",
            light="yellow",
            summary=f"Ready ({', '.join(ready)}); gaps in {', '.join(not_ready)}.",
            details=details,
        )

    return TransitionStatus(
        from_phase="formalise",
        to_phase="analyse",
        light="green",
        summary="Model fully parameterised — ready to analyse.",
        details=details,
    )


def _assess_analyse_to_interpret(paths) -> TransitionStatus:
    """Analyse → Interpret: soft pass-through.

    Full structural + model-attribute validation now happens at the
    Formalise → Analyse gate, so reaching Analyse already implies a
    complete, parameterised model that Interpret can consume. There is no
    separately persisted analysis artefact to require here.

    TODO: nudge to yellow once the findings system exposes a
    recorded-findings count we can gate on.
    """
    return TransitionStatus(
        from_phase="analyse",
        to_phase="interpret",
        light="green",
        summary="Ready to interpret.",
    )


def _assess_interpret_to_communicate(paths) -> TransitionStatus:
    """Interpret → Communicate: structural summary must have claims."""
    from latris.operations.interpret import load_interpretation

    store = load_interpretation(root=paths.root)
    sections = store.sections

    populated_states = {"claims_only", "generated", "edited"}

    # Check structural_summary
    structural_done = any(s.section_type == "structural_summary" and s.generation_state in populated_states for s in sections)  # noqa: E501

    if not structural_done:
        return TransitionStatus(
            from_phase="interpret",
            to_phase="communicate",
            light="red",
            summary="Generate a structural summary before communicating.",
            details=["No structural summary with claims found."],
        )

    # Check stakeholder sections
    stakeholder_types = {"answer_to_question", "implications"}
    stakeholder_done = any(s.section_type in stakeholder_types and s.generation_state in populated_states for s in sections)  # noqa: E501

    if not stakeholder_done:
        missing = []
        if not any(s.section_type == "answer_to_question" and s.generation_state in populated_states for s in sections):
            missing.append("Answer to Modelling Question")
        if not any(s.section_type == "implications" and s.generation_state in populated_states for s in sections):
            missing.append("Implications & Interventions")
        return TransitionStatus(
            from_phase="interpret",
            to_phase="communicate",
            light="yellow",
            summary="Structural summary done; consider stakeholder sections.",
            details=[f"Not yet populated: {', '.join(missing)}."],
        )

    # Soft nudge: each selected formalism should carry a recorded selection
    # rationale — it feeds the report's "Modelling Approach" section. Never a
    # red block; auditability is enforced at the published artefact, not here.
    from latris.operations.project import current_model_choices
    from latris.schema import ProjectFoundation

    foundation = load_model(ProjectFoundation, paths.project_yaml)
    selected = foundation.selected_model_types or []
    choices = current_model_choices(root=paths.root)
    missing_rationale = [m for m in selected if not (choices.get(m) and choices[m].rationale.strip())]
    if missing_rationale:
        return TransitionStatus(
            from_phase="interpret",
            to_phase="communicate",
            light="yellow",
            summary="Ready to communicate; record why each formalism was chosen.",
            details=[f"No selection rationale recorded for: {', '.join(missing_rationale)}."],
        )

    return TransitionStatus(
        from_phase="interpret",
        to_phase="communicate",
        light="green",
        summary="Ready to communicate.",
    )


def assess_transition_readiness(
    *,
    root: Path | None = None,
) -> TransitionReadiness:
    """Compute traffic-light readiness for all phase transitions.

    Cascading: if any transition is red, all subsequent transitions
    are forced red regardless of their own criteria.
    """
    paths = require_project(root)
    assessors = [
        _assess_home_to_build,
        _assess_build_to_formalise,
        _assess_formalise_to_analyse,
        _assess_analyse_to_interpret,
        _assess_interpret_to_communicate,
    ]

    phase_labels = [
        ("home", "build"),
        ("build", "formalise"),
        ("formalise", "analyse"),
        ("analyse", "interpret"),
        ("interpret", "communicate"),
    ]

    transitions: list[TransitionStatus] = []
    blocked = False
    for assessor, (from_phase, to_phase) in zip(assessors, phase_labels, strict=True):
        if blocked:
            transitions.append(
                TransitionStatus(
                    from_phase=from_phase,
                    to_phase=to_phase,
                    light="red",
                    summary="Blocked by an earlier phase.",
                    details=["Complete earlier phases first."],
                )
            )
        else:
            status = assessor(paths)
            transitions.append(status)
            if status.light == "red":
                blocked = True

    return TransitionReadiness(transitions=transitions)
