"""Bayesian Network operations — set state spaces + CPTs, check, infer.

These are dedicated operations (not routed through the generic scalar
``view_attributes`` dispatch) because a CPT is structured data, not a single
coercible value. Each mutation upserts the relevant Set, dumps it, and
auto-commits — returning ``(model, commit_sha)`` per the operations convention.

Storage:
- ``views/parameters/bn-state_space.yaml`` — :class:`StateSpaceSet`
- ``views/parameters/bn-cpt.yaml``          — :class:`CPTSet`
"""

from __future__ import annotations

import dataclasses
import itertools
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from latris.operations._bn_canonical import effective_cpt_map
from latris.operations._resolve import resolve_target
from latris.operations.bn_inference import BNInferenceResult, bn_infer
from latris.operations.commit import auto_commit
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_model, load_model, load_model_or_default
from latris.schema import Substrate
from latris.schema.bn import (
    CPTEntry,
    CPTRow,
    CPTSet,
    NoisyOrEntry,
    NoisyOrLink,
    NoisyOrSet,
    StateSpaceEntry,
    StateSpaceSet,
)
from latris.schema.common import ProvenanceOrigin

_MODEL_TYPE = "bn"


# ── storage helpers ──────────────────────────────────────────────────


def _state_space_path(paths):
    return paths.view_attribute_path(_MODEL_TYPE, "state_space")


def _cpt_path(paths):
    return paths.view_attribute_path(_MODEL_TYPE, "cpt")


def _noisy_or_path(paths):
    return paths.view_attribute_path(_MODEL_TYPE, "noisy_or")


def _load_state_spaces(paths) -> StateSpaceSet:
    p = _state_space_path(paths)
    return load_model_or_default(StateSpaceSet, p)


def _load_cpts(paths) -> CPTSet:
    p = _cpt_path(paths)
    return load_model_or_default(CPTSet, p)


def _load_noisy_or(paths) -> NoisyOrSet:
    p = _noisy_or_path(paths)
    return load_model_or_default(NoisyOrSet, p)


def bn_structure(substrate: Substrate) -> tuple[set[str], dict[str, list[str]]]:
    """BN node set + ordered parents from the causal-edge projection.

    A BN node is any entity touched by a causal edge; parents preserve
    first-seen edge order (CPT column order). Mirrors the readiness layer's
    ``_bn_parent_map`` for use outside a ValidationContext (learning,
    sensitivity)."""
    from latris.operations.graph_analysis import causal_edges

    nodes: set[str] = set()
    parents: dict[str, list[str]] = {}
    for e in causal_edges(substrate.edges):
        nodes.add(e.from_id)
        nodes.add(e.to_id)
        parents.setdefault(e.to_id, []).append(e.from_id)
    parents = {nid: list(dict.fromkeys(ps)) for nid, ps in parents.items()}
    return nodes, parents


def _effective_cpt_map(paths) -> dict[str, CPTEntry]:
    """The node→CPT map the engine computes on: tabular CPTs plus expanded
    canonical (Noisy-OR) specs. Single source of truth for inference,
    readiness, listing and sensitivity."""
    ss_map = {e.target_id: e.states for e in _load_state_spaces(paths).entries}
    return effective_cpt_map(_load_cpts(paths), _load_noisy_or(paths), ss_map)



# ── mutations ────────────────────────────────────────────────────────


def set_state_space(
    node: str,
    states: list[str],
    *,
    ordered: bool = False,
    root: Path | None = None,
) -> tuple[StateSpaceEntry, str]:
    """Set (or replace) the discrete state space of a node."""
    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    node_id = resolve_target(node, substrate)

    entry = StateSpaceEntry(target_id=node_id, states=states, ordered=ordered)
    store = _load_state_spaces(paths)
    store.entries = [e for e in store.entries if e.target_id != node_id]
    store.entries.append(entry)

    path = _state_space_path(paths)
    dump_model(store, path)
    sha = auto_commit(
        paths.root,
        subject=f"Set BN state space on {node_id[:15]}…: {', '.join(states)}",
        body=f"target: {node_id}\nstates: {states}\nordered: {ordered}",
        paths=[path],
    )
    return entry, sha


def set_cpt(
    node: str,
    parents: list[str],
    probs: list[float],
    *,
    origin: ProvenanceOrigin = "human-direct",
    source_id: str | None = None,
    root: Path | None = None,
) -> tuple[CPTEntry, str]:
    """Set (or replace) a node's CPT from a flat, row-major probability list.

    ``probs`` is read as one block of ``len(node states)`` per parent-state
    combination, with combinations enumerated so the FIRST parent varies
    slowest (matching the inference engine's column order). Each block should
    sum to 1. The given ``origin``/``source_id`` are stamped on every row.
    """
    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    node_id = resolve_target(node, substrate)
    parent_ids = [resolve_target(p, substrate) for p in parents]

    ss_map = {e.target_id: e.states for e in _load_state_spaces(paths).entries}
    if node_id not in ss_map:
        raise ValueError(f"set the state space for {node!r} before its CPT")
    for raw, pid in zip(parents, parent_ids, strict=True):
        if pid not in ss_map:
            raise ValueError(f"set the state space for parent {raw!r} before this CPT")

    node_states = ss_map[node_id]
    card = len(node_states)
    combos = list(itertools.product(*[ss_map[p] for p in parent_ids])) if parent_ids else [()]
    expected = len(combos) * card
    if len(probs) != expected:
        raise ValueError(
            f"expected {expected} probabilities ({len(combos)} parent-state combination(s) "
            f"× {card} state(s)), got {len(probs)}"
        )

    rows = []
    for i, combo in enumerate(combos):
        block = probs[i * card : (i + 1) * card]
        parent_states = {pid: combo[j] for j, pid in enumerate(parent_ids)}
        rows.append(CPTRow(parent_states=parent_states, p=block, origin=origin, source_id=source_id))

    cpt = CPTEntry(target_id=node_id, parents=parent_ids, states=node_states, rows=rows)
    store = _load_cpts(paths)
    store.entries = [e for e in store.entries if e.target_id != node_id]
    store.entries.append(cpt)

    path = _cpt_path(paths)
    dump_model(store, path)
    sha = auto_commit(
        paths.root,
        subject=f"Set BN CPT on {node_id[:15]}… ({len(rows)} row(s))",
        body=f"target: {node_id}\nparents: {parent_ids}\norigin: {origin}\nsource_id: {source_id}",
        paths=[path],
    )
    return cpt, sha


def weighted_table(
    states: list[str],
    base: list[float],
    weights: list[dict[str, float]],
    parent_states: list[list[str]],
    *,
    toward_first: bool = True,
) -> list[float]:
    """A full table from a base distribution and a weight per parent state (an ordinal logistic model).

    Each parent combination's score is the sum of its states' weights (logits; 0 = no effect, ±1 a
    moderate push, ±3 a strong one). The score shifts the base distribution's cumulative logits toward
    the first state (or the last, ``toward_first=False``): with every weight 0 each row is ``base``. A
    two-state node is plain logistic regression. Rows come first-parent-slowest, like ``set_cpt``.
    """
    if len(base) != len(states):
        raise ValueError(f"base needs one probability per state ({len(states)}), got {len(base)}")
    if any(b < 0 for b in base) or abs(sum(base) - 1.0) > 1e-6:
        raise ValueError("base must be probabilities that sum to 1")
    order = list(range(len(states))) if toward_first else list(reversed(range(len(states))))
    ordered = [base[i] for i in order]
    eps = 1e-12
    cum, logits = 0.0, []
    for b in ordered[:-1]:
        cum += b
        c = min(max(cum, eps), 1 - eps)
        logits.append(math.log(c / (1 - c)))
    out: list[float] = []
    for combo in itertools.product(*parent_states) if parent_states else [()]:
        score = sum(w.get(s, 0.0) for w, s in zip(weights, combo, strict=True))
        cdf = [1 / (1 + math.exp(-(lg + score))) for lg in logits] + [1.0]
        probs_ordered = [cdf[0]] + [cdf[i] - cdf[i - 1] for i in range(1, len(cdf))]
        row = [0.0] * len(states)
        for pos, i in enumerate(order):
            row[i] = max(probs_ordered[pos], 0.0)
        total = sum(row)
        out.extend(round(p / total, 10) for p in row)
    return out


def set_weighted_table(
    node: str,
    base: list[float],
    weights: dict[str, dict[str, float]],
    *,
    toward: str | None = None,
    origin: ProvenanceOrigin = "human-elicited",
    source_id: str | None = None,
    root: Path | None = None,
) -> tuple[CPTEntry, str]:
    """Set a node's table from a base distribution and weights per parent state (``weighted_table``).

    ``weights`` maps each parent (label or id) to {state: weight}; states left out weigh 0. ``toward`` is
    the state positive weights push toward — the node's first or last state (default: the first).
    """
    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    node_id = resolve_target(node, substrate)
    ss_map = {e.target_id: e.states for e in _load_state_spaces(paths).entries}
    if node_id not in ss_map:
        raise ValueError(f"set the state space for {node!r} before its table")
    states = ss_map[node_id]
    if toward is not None and toward not in (states[0], states[-1]):
        raise ValueError(f"toward must be the first or last state ({states[0]!r} or {states[-1]!r})")
    parents = list(weights)
    parent_ids = [resolve_target(p, substrate) for p in parents]
    for raw, pid in zip(parents, parent_ids, strict=True):
        if pid not in ss_map:
            raise ValueError(f"set the state space for parent {raw!r} before this table")
        bad = sorted(set(weights[raw]) - set(ss_map[pid]))
        if bad:
            raise ValueError(f"{raw!r} has no state(s) {', '.join(bad)} (states: {', '.join(ss_map[pid])})")
    probs = weighted_table(states, base, [weights[p] for p in parents], [ss_map[p] for p in parent_ids],
                           toward_first=toward is None or toward == states[0])
    return set_cpt(node, parents, probs, origin=origin, source_id=source_id, root=paths.root)


_EVENT_STATES = {"yes", "true", "present", "occurs", "occurred", "on", "1", "high", "y"}


def set_noisy_or(
    node: str,
    leak: float,
    causes: list[tuple[str, str, float]],
    *,
    active: str | None = None,
    origin: ProvenanceOrigin = "human-elicited",
    source_id: str | None = None,
    root: Path | None = None,
) -> tuple[NoisyOrEntry, str]:
    """Set (or replace) a node's Noisy-OR parameterisation.

    ``active`` is the node's state the causes push toward (the effect happening).
    It must be given unless the first state plainly is that (yes, true, present,
    occurs, on, 1, high) — a Noisy-OR with states [no, yes] and no ``active``
    would otherwise silently compute P(no) as the effect.

    ``causes`` is a list of ``(parent, active_state, prob)``. The node and all
    parents must be binary and already have state spaces. The node must not also
    carry a tabular CPT. Stored as a compact spec and expanded to a full CPT at
    compute time; ``origin``/``source_id`` stamp the spec.
    """
    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    node_id = resolve_target(node, substrate)

    ss_map = {e.target_id: e.states for e in _load_state_spaces(paths).entries}
    if node_id not in ss_map:
        raise ValueError(f"set the state space for {node!r} before its Noisy-OR")
    if len(ss_map[node_id]) != 2:
        raise ValueError(f"Noisy-OR requires a binary node; {node!r} has states {ss_map[node_id]}")
    if node_id in {e.target_id for e in _load_cpts(paths).entries}:
        raise ValueError(f"{node!r} already has a tabular CPT; remove it before setting a Noisy-OR")
    states = ss_map[node_id]
    if active is None:
        if states[0].strip().lower() not in _EVENT_STATES:
            raise ValueError(
                f"say which state of {node!r} is the effect happening (states {states}), "
                f"e.g. --active {states[1] if states[1].strip().lower() in _EVENT_STATES else states[0]}"
            )
        active = states[0]
    elif active not in states:
        raise ValueError(f"{active!r} is not a state of {node!r} (states {states})")

    links: list[NoisyOrLink] = []
    parent_ids: list[str] = []
    for raw_parent, active_state, prob in causes:
        pid = resolve_target(raw_parent, substrate)
        if pid not in ss_map:
            raise ValueError(f"set the state space for parent {raw_parent!r} before this Noisy-OR")
        if len(ss_map[pid]) != 2:
            raise ValueError(f"Noisy-OR parent {raw_parent!r} must be binary (states {ss_map[pid]})")
        if active_state not in ss_map[pid]:
            raise ValueError(
                f"active state {active_state!r} is not a state of {raw_parent!r} (states {ss_map[pid]})"
            )
        parent_ids.append(pid)
        links.append(
            NoisyOrLink(
                parent_id=pid, active_state=active_state, prob=prob,
                origin=origin, source_id=source_id,
            )
        )

    entry = NoisyOrEntry(
        target_id=node_id, parents=parent_ids, states=ss_map[node_id], leak=leak,
        links=links, origin=origin, source_id=source_id, active=active,
    )
    store = _load_noisy_or(paths)
    store.entries = [e for e in store.entries if e.target_id != node_id]
    store.entries.append(entry)

    path = _noisy_or_path(paths)
    dump_model(store, path)
    sha = auto_commit(
        paths.root,
        subject=f"Set BN Noisy-OR on {node_id[:15]}… ({len(links)} cause(s), leak {leak})",
        body=f"target: {node_id}\nparents: {parent_ids}\nleak: {leak}\norigin: {origin}",
        paths=[path],
    )
    return entry, sha


# ── reads ────────────────────────────────────────────────────────────


def remove_states(node: str, *, root: Path | None = None) -> tuple[str, int, str]:
    """Take a factor out of the network: drop its states, its table and the table's uncertainty. The
    factor, its links and citations stay (in the loop map). Refused while another table uses it as a
    parent. Returns ``(entity_id, rows_removed, commit_sha)``.
    """
    from latris.operations._cascade import cascade_model_type

    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    node_id = resolve_target(node, substrate)
    labels = {e.id: e.label for e in substrate.entities}
    if node_id not in {e.target_id for e in _load_state_spaces(paths).entries}:
        raise ValueError(f"{labels.get(node_id, node)!r} has no states")
    children = sorted(labels.get(t, t) for t, cpt in _effective_cpt_map(paths).items()
                      if node_id in cpt.parents and t != node_id)
    if children:
        raise ValueError(f"{labels.get(node_id, node)!r} is a parent in the table of {', '.join(children)}; "
                         "set those tables without it first")
    changed, removed = cascade_model_type(paths, _MODEL_TYPE, [node_id])
    sha = auto_commit(
        paths.root,
        subject=f"BN: take {labels.get(node_id, node_id)} out of the network",
        body=f"target: {node_id}\nrows removed: {removed}",
        paths=changed,
    )
    return node_id, removed, sha


def get_state_spaces(*, root: Path | None = None) -> StateSpaceSet:
    return _load_state_spaces(require_project(root))


def get_cpts(*, root: Path | None = None) -> CPTSet:
    return _load_cpts(require_project(root))


def get_noisy_or(*, root: Path | None = None) -> NoisyOrSet:
    return _load_noisy_or(require_project(root))


def effective_cpts(*, root: Path | None = None) -> dict[str, CPTEntry]:
    """Public reader: node→CPT map with canonical specs expanded."""
    return _effective_cpt_map(require_project(root))


# ── readiness check ──────────────────────────────────────────────────


def check(*, root: Path | None = None):
    """Run the BN readiness validators directly and return the gaps.

    Bypasses ``assess_readiness`` (which short-circuits while BN is "planned").
    """
    from latris.operations.membership import check_scope
    from latris.operations.readiness import (
        ValidationContext,
        _check_acyclicity,
        _check_cpt_complete,
        _check_state_space_defined,
    )
    from latris.schema.model_types import get_model_type
    from latris.schema.roles import RoleSet

    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    scope = check_scope(paths, _MODEL_TYPE)  # in a model sharing its map: only the factors with states
    ctx = ValidationContext(
        substrate=substrate,
        view_entity_ids=[e.id for e in substrate.entities] if scope is None else list(scope.entity_ids),
        view_edge_ids=[e.id for e in substrate.edges] if scope is None else list(scope.edge_ids),
        spec=get_model_type(_MODEL_TYPE),
        roles=RoleSet(),
        paths=paths,
    )
    gaps = []
    gaps.extend(_check_acyclicity(ctx))
    gaps.extend(_check_state_space_defined(ctx))
    gaps.extend(_check_cpt_complete(ctx))
    return gaps


@dataclass(frozen=True)
class BNProblem:
    """One structural problem of the BN view (a readiness gap, without the label)."""

    target_id: str | None
    gap_type: str
    message: str


def structure_problems(*, root: Path | None = None) -> list[BNProblem]:
    """The BN view's structural problems: cycles, missing state spaces, incomplete CPTs.

    Readiness reports them through the formalism plugin's validators; the
    interpretation's claims quote them. A model with no BN nodes yet reports
    one problem — an empty network is not a complete one.
    """
    problems = [
        BNProblem(target_id=g.element_id or None, gap_type=g.gap_type, message=g.message)
        for g in check(root=root)
    ]
    from latris.operations.membership import check_scope

    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    scope = check_scope(paths, _MODEL_TYPE)
    if scope is not None and not scope.entity_ids:
        problems.append(BNProblem(
            target_id=None,
            gap_type="bn_no_nodes",
            message="No factor is in the Bayesian network yet — a factor joins it when it gets states; "
            "the rest of the map stays in the loop map.",
        ))
    elif not any(e.kind == "causal" for e in substrate.edges):
        problems.append(BNProblem(
            target_id=None,
            gap_type="bn_no_nodes",
            message="No Bayesian-network nodes yet — a BN node is a factor on a causal link; "
            "add factors, link them, then give each a state space.",
        ))
    return problems


# ── inference ────────────────────────────────────────────────────────


def intervene(cpt_map: dict[str, CPTEntry], ss_map: dict[str, list[str]],
              interventions: dict[str, str]) -> dict[str, CPTEntry]:
    """The network after SETTING factors to a state (Pearl's do-operator): each set factor's table is
    replaced by certainty in its state, cutting the links from its causes. Downstream factors respond;
    the set factor's causes don't (setting it says nothing about why it would have been that way)."""
    out = dict(cpt_map)
    for node, state in interventions.items():
        states = ss_map.get(node)
        if not states or state not in states:
            raise ValueError(f"state {state!r} is not a valid state for node {node!r} (allowed: {states or []})")
        out[node] = CPTEntry(target_id=node, parents=[], states=list(states),
                             rows=[CPTRow(p=[1.0 if s == state else 0.0 for s in states])])
    return out


@dataclasses.dataclass(frozen=True)
class ScenarioApplied:
    """A scenario applied to the network: the tables to compute on and the combined evidence."""

    name: str | None
    tables: dict[str, CPTEntry]
    evidence: dict[str, str]
    soft: dict[str, dict[str, float]]
    likelihood: dict[str, dict[str, float]]
    interventions: dict[str, str]
    fixed_rows: dict[str, set[int]]
    changes: list[str]
    overrides: list = dataclasses.field(default_factory=list)  # the scenario's BNTableOverrides
    extends: str | None = None


def with_scenario(
    name: str | None,
    paths,  # noqa: ANN001
    cpt_map: dict[str, CPTEntry],
    *,
    evidence: dict[str, str] | None = None,
    soft: dict[str, dict[str, float]] | None = None,
    likelihood: dict[str, dict[str, float]] | None = None,
    interventions: dict[str, str] | None = None,
    labels: dict[str, str] | None = None,
) -> ScenarioApplied:
    """Apply a saved BN scenario (by name; None for none) under evidence given in the call (resolved ids).

    What the call says about a factor replaces what the scenario says about it, whichever kind."""
    from latris.operations import bn_scenarios

    call: dict[str, dict[str, Any]] = {
        "evidence": dict(evidence or {}), "soft": dict(soft or {}), "likelihood": dict(likelihood or {}),
        "interventions": dict(interventions or {}),
    }
    if not name:
        return ScenarioApplied(None, cpt_map, call["evidence"], call["soft"], call["likelihood"],
                               call["interventions"], {}, [])
    sc = bn_scenarios.get(name, paths)
    named = {n for block in call.values() for n in block}
    merged = {b: {k: v for k, v in getattr(sc, b).items() if k not in named} | call[b] for b in call}
    tables, fixed = bn_scenarios.apply_tables(cpt_map, sc.tables, labels)
    return ScenarioApplied(sc.name, tables, merged["evidence"], merged["soft"], merged["likelihood"],
                           merged["interventions"], fixed, bn_scenarios.describe_changes(sc, labels or {}),
                           overrides=list(sc.tables), extends=sc.extends)


def _set_factors(applied: ScenarioApplied, ss_map: dict[str, list[str]]) -> dict[str, CPTEntry]:
    """The tables to compute on once the factors a call or its scenario SETS are set — refusing a set factor
    that isn't in the network (a scenario saved before it was removed) or that is also observed."""
    do = applied.interventions
    if not do:
        return applied.tables
    for node in do:
        if node not in applied.tables:
            raise ValueError(f"{node!r} is not in the network, so it can't be set")
    overlap = set(do) & (set(applied.evidence) | set(applied.soft) | set(applied.likelihood))
    if overlap:
        raise ValueError("a factor can be set or observed, not both: " + ", ".join(sorted(overlap)))
    return intervene(applied.tables, ss_map, do)


def infer(
    *,
    query: list[str] | None = None,
    evidence: dict[str, str] | None = None,
    soft: dict[str, dict[str, float]] | None = None,
    likelihood: dict[str, dict[str, float]] | None = None,
    interventions: dict[str, str] | None = None,
    scenario: str | None = None,
    root: Path | None = None,
) -> BNInferenceResult:
    """Load the BN and compute exact posterior marginals.

    ``query`` and the keys of ``evidence``, ``soft`` and ``likelihood`` accept
    node IDs, ID prefixes, or labels; they are resolved to IDs before inference.
    The result is keyed by node ID. ``scenario`` applies a saved BN scenario (its
    observations, settings and table overrides); evidence given here about a
    factor replaces the scenario's.
    """
    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)

    ss_map = {e.target_id: e.states for e in _load_state_spaces(paths).entries}
    cpt_map = _effective_cpt_map(paths)

    def ids(block):  # noqa: ANN001, ANN202
        return {resolve_target(k, substrate): v for k, v in block.items()} if block else None

    query_ids = [resolve_target(q, substrate) for q in query] if query else None
    applied = with_scenario(scenario, paths, cpt_map, evidence=ids(evidence), soft=ids(soft),
                            likelihood=ids(likelihood), interventions=ids(interventions),
                            labels={e.id: e.label for e in substrate.entities})
    cpt_map = applied.tables
    evidence, soft, likelihood = applied.evidence, applied.soft, applied.likelihood
    do = applied.interventions
    cpt_map = _set_factors(applied, ss_map)
    result = bn_infer(
        ss_map, cpt_map, query=query_ids, evidence=evidence or None, soft=soft or None, likelihood=likelihood or None
    )
    result = dataclasses.replace(result, interventions=do) if do else result
    if applied.name:
        result = dataclasses.replace(result, scenario=applied.name, scenario_changes=applied.changes)
    return result


def parse_distribution(text: str) -> tuple[str, dict[str, float]]:
    """``"Wet=yes:0.8"`` or ``"Wet=yes:0.6,no:0.4"`` → ("Wet", {"yes": 0.8, ...})."""
    if "=" not in text:
        raise ValueError(f"expected 'Node=state:value[,state:value]', got {text!r}")
    node, rest = text.rsplit("=", 1)
    out: dict[str, float] = {}
    for part in rest.split(","):
        if ":" not in part:
            raise ValueError(f"expected 'state:value' in {text!r}, got {part!r}")
        state, value = part.rsplit(":", 1)
        try:
            out[state.strip()] = float(value)
        except ValueError as exc:
            raise ValueError(f"{value.strip()!r} in {text!r} is not a number") from exc
    return node.strip(), out


def record_query(result: BNInferenceResult, *, root: Path | None = None) -> tuple[str, str]:
    """Record a query's posteriors (with the no-evidence priors) as a result reports show.

    Returns (commit_sha, run_id). Reports show the latest run per (query, evidence).
    """
    import pgmpy

    from latris.operations.analysis_results import record_result

    paths = require_project(root)
    labels = {e.id: e.label for e in load_model(Substrate, paths.conceptual_yaml).entities}
    nodes = sorted(result.marginals)
    conditioned = bool(result.evidence or result.soft or result.likelihood or result.interventions)
    priors = infer(query=nodes, root=paths.root).marginals if conditioned else result.marginals
    evidence_text = evidence_description(result.evidence, result.soft, result.likelihood, labels)
    if result.interventions:
        set_text = "set " + ", ".join(f"{labels.get(k, k)} = {v}" for k, v in sorted(result.interventions.items()))
        evidence_text = f"{set_text}; {evidence_text}" if evidence_text else set_text
    if result.scenario:
        evidence_text = f"scenario {result.scenario}" + (f"; {evidence_text}" if evidence_text else "")

    def top(node: str) -> str:
        dist = result.marginals[node]
        state = max(dist, key=dist.get)  # type: ignore[arg-type]
        return f"{labels.get(node, node)}: {state} {dist[state]:.0%}"

    sha, run = record_result(
        kind="bn-query",
        key="bn-query|" + ",".join(nodes) + "|" + evidence_key(result.evidence, result.soft, result.likelihood)
        + ("|do:" + ",".join(f"{k}={v}" for k, v in sorted(result.interventions.items()))
           if result.interventions else "")
        + (f"|scenario:{result.scenario}" if result.scenario else ""),
        payload={
            "evidence": result.evidence, "soft": result.soft, "likelihood": result.likelihood,
            "interventions": result.interventions,
            **({"scenario": result.scenario, "scenario_changes": result.scenario_changes} if result.scenario else {}),
            "posteriors": result.marginals, "priors": priors,
            "labels": {n: labels.get(n, n) for n in {*nodes, *result.evidence, *result.soft, *result.likelihood,
                                                       *result.interventions}},
            "method": result.method,
        },
        purpose="inference",
        algorithm=result.method,
        library_version=f"pgmpy {pgmpy.__version__}",
        summary=f"P(· | {evidence_text or 'no evidence'}): " + "; ".join(top(n) for n in nodes[:8]),
        model_type=_MODEL_TYPE,
        hyperparameters={"query": nodes, "evidence": result.evidence, "soft": result.soft,
                         "likelihood": result.likelihood, "interventions": result.interventions,
                         **({"scenario": result.scenario} if result.scenario else {})},
        scenarios=[result.scenario] if result.scenario else None,
        affected_target_ids=nodes,
        commit_subject=f"BN query: {len(nodes)} node(s) given {evidence_text or 'no evidence'}"[:120],
        root=paths.root,
    )
    return sha, run.id


# ── evidence descriptions (shared by queries, explanations and Monte Carlo) ──


def evidence_key(evidence: dict, soft: dict | None = None, likelihood: dict | None = None) -> str:
    """A stable text key for a combination of hard, soft and likelihood evidence."""
    parts = [f"{k}={v}" for k, v in sorted(evidence.items())]
    for tag, block in (("~", soft or {}), ("*", likelihood or {})):
        for k, dist in sorted(block.items()):
            parts.append(f"{k}{tag}" + "/".join(f"{st}:{q:.6g}" for st, q in dist.items()))
    return ",".join(parts)


def evidence_description(
    evidence: dict, soft: dict | None, likelihood: dict | None, labels: dict[str, str]
) -> str:
    """'Wet = yes, Rain = heavy (80% sure)' — for summaries, reports and claims."""
    parts = [f"{labels.get(k, k)} = {v}" for k, v in sorted(evidence.items())]
    for k, dist in sorted((soft or {}).items()):
        state = max(dist, key=dist.get)  # type: ignore[arg-type]
        parts.append(f"{labels.get(k, k)} = {state} ({dist[state]:.0%} sure)")
    for k, w in sorted((likelihood or {}).items()):
        parts.append(f"{labels.get(k, k)}: an observation weighing " + " : ".join(f"{st} {v:g}" for st, v in w.items()))
    return ", ".join(parts)


def _do_key(interventions: dict | None) -> str:
    """The part of a result's key that says what was set (empty when nothing was, so older keys still match)."""
    return "|do:" + ",".join(f"{k}={v}" for k, v in sorted(interventions.items())) if interventions else ""


def _resolve_block(block, substrate):  # noqa: ANN001, ANN202
    return {resolve_target(k, substrate): v for k, v in block.items()} if block else {}


# ── most likely explanation ──────────────────────────────────────────


def explain(
    *,
    over: list[str] | None = None,
    evidence: dict[str, str] | None = None,
    soft: dict[str, dict[str, float]] | None = None,
    likelihood: dict[str, dict[str, float]] | None = None,
    interventions: dict[str, str] | None = None,
    root: Path | None = None,
) -> dict:
    """The most likely joint explanation (MPE, or MAP over ``over``) given the evidence, in the network with
    the ``interventions`` factors set (do-operator); labels accepted."""
    from latris.operations import bn_explain

    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    ss_map = {e.target_id: e.states for e in _load_state_spaces(paths).entries}
    out = bn_explain.explain(
        ss_map, _effective_cpt_map(paths),
        over=[resolve_target(n, substrate) for n in over] if over else None,
        evidence=_resolve_block(evidence, substrate), soft=_resolve_block(soft, substrate),
        likelihood=_resolve_block(likelihood, substrate), interventions=_resolve_block(interventions, substrate),
    )
    labels = {e.id: e.label for e in substrate.entities}
    out["labels"] = {n: labels.get(n, n) for n in
                     {*out["over"], *out["evidence"], *out["soft"], *out["likelihood"], *out["interventions"]}}
    return out


def set_description(interventions: dict[str, str] | None, labels: dict[str, str]) -> str:
    """'Sprinkler set to off' — what a what-if sets, for summaries and reports."""
    return ", ".join(f"{labels.get(k, k)} set to {v}" for k, v in sorted((interventions or {}).items()))


def condition_description(evidence: dict, soft: dict | None, likelihood: dict | None,
                          interventions: dict | None, labels: dict[str, str]) -> str:
    """Everything a result was conditioned on — what was observed, then what was set — or ''."""
    parts = [evidence_description(evidence, soft, likelihood, labels), set_description(interventions, labels)]
    return "; ".join(p for p in parts if p)


def describe_explanation(p: dict) -> str:
    labels = p["labels"]
    cond = condition_description(p["evidence"], p["soft"], p["likelihood"], p.get("interventions"), labels) \
        or "no evidence"
    states = ", ".join(f"{labels.get(n, n)} = {p['assignment'][n]}" for n in p["over"])
    prob = f" (P = {p['probability']:.0%})" if p.get("probability") is not None else ""
    return f"Given {cond}, the most likely explanation is {states}{prob}"


def record_explanation(payload: dict, *, root: Path | None = None) -> tuple[str, str]:
    import pgmpy

    from latris.operations.analysis_results import record_result

    sha, run = record_result(
        kind="bn-explanation",
        key="bn-explanation|" + ",".join(sorted(payload["over"])) + "|"
            + evidence_key(payload["evidence"], payload["soft"], payload["likelihood"])
            + _do_key(payload.get("interventions")),
        payload=payload,
        purpose="inference",
        algorithm=f"{payload['kind']}; {payload['method']}",
        library_version=f"pgmpy {pgmpy.__version__}",
        summary=describe_explanation(payload),
        model_type=_MODEL_TYPE,
        hyperparameters={"over": payload["over"] if payload["kind"] == "MAP" else None,
                         "evidence": payload["evidence"], "soft": payload["soft"], "likelihood": payload["likelihood"],
                         "interventions": payload.get("interventions") or {}},
        affected_target_ids=list(payload["over"]),
        commit_subject=f"BN most likely explanation ({payload['kind']}, {len(payload['over'])} node(s))",
        root=root,
    )
    return sha, run.id


# ── probabilistic sensitivity (Monte Carlo over the tables) ──────────


def run_monte_carlo(
    target: str,
    *,
    state: str | None = None,
    evidence: dict[str, str] | None = None,
    soft: dict[str, dict[str, float]] | None = None,
    likelihood: dict[str, dict[str, float]] | None = None,
    interventions: dict[str, str] | None = None,
    runs: int = 500,
    seed: int = 1234,
    max_seconds: float = 60.0,
    scenario: str | None = None,
    root: Path | None = None,
) -> dict:
    """Re-ask P(target | evidence) under draws of every table that has an uncertainty ("worth n").

    ``scenario`` applies a saved BN scenario: its overridden rows and the factors it sets are held at the
    scenario's values (they carry no sampled uncertainty of their own)."""
    from latris.operations import bn_montecarlo, uncertainty

    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    ss_map = {e.target_id: e.states for e in _load_state_spaces(paths).entries}
    labels = {e.id: e.label for e in substrate.entities}
    noisy = {e.target_id: e for e in _load_noisy_or(paths).entries}
    applied = with_scenario(scenario, paths, _effective_cpt_map(paths), evidence=_resolve_block(evidence, substrate),
                            soft=_resolve_block(soft, substrate), likelihood=_resolve_block(likelihood, substrate),
                            interventions=_resolve_block(interventions, substrate), labels=labels)
    tables = _set_factors(applied, ss_map)
    if resolve_target(target, substrate) in applied.interventions:
        raise ValueError(f"{target!r} is set, so it has no uncertainty to show; ask about a factor that isn't set")
    out = bn_montecarlo.monte_carlo(
        ss_map, tables, noisy, uncertainty.bn_specs(paths), resolve_target(target, substrate),
        state=state, evidence=applied.evidence, soft=applied.soft, likelihood=applied.likelihood, runs=runs,
        seed=seed, max_seconds=max_seconds, labels=labels, fixed_rows=applied.fixed_rows,
        held=set(applied.interventions),
    )
    if applied.interventions:
        out["interventions"] = applied.interventions
    if applied.name:
        out.update(scenario=applied.name, scenario_changes=applied.changes)
    return out


def record_monte_carlo(payload: dict, *, root: Path | None = None) -> tuple[str, str]:
    import pgmpy

    from latris.operations.analysis_results import record_result
    from latris.operations.bn_montecarlo import describe

    sha, run = record_result(
        kind="bn-monte-carlo",
        key=f"bn-monte-carlo|{payload['target']}={payload['focus_state']}|"
            + evidence_key(payload["evidence"], payload["soft"], payload["likelihood"])
            + ("" if payload.get("scenario") else _do_key(payload.get("interventions")))
            + (f"|scenario:{payload['scenario']}" if payload.get("scenario") else ""),
        payload=payload,
        purpose="sensitivity-analysis",
        algorithm="monte-carlo[dirichlet]; variable_elimination",
        library_version=f"pgmpy {pgmpy.__version__}",
        summary=describe(payload),
        model_type=_MODEL_TYPE,
        hyperparameters={"target": payload["target"], "state": payload["focus_state"],
                         "evidence": payload["evidence"], "soft": payload["soft"],
                         "likelihood": payload["likelihood"], "runs": payload["runs"],
                         **({"interventions": payload["interventions"]} if payload.get("interventions") else {}),
                         **({"scenario": payload["scenario"]} if payload.get("scenario") else {})},
        scenarios=[payload["scenario"]] if payload.get("scenario") else None,
        uncertainty=True,
        seed=payload["seed"],
        metrics={"runs": payload["runs"], "seconds": payload["seconds"]},
        affected_target_ids=[payload["target"]],
        duration_seconds=payload["seconds"],
        commit_subject=f"BN Monte Carlo: {payload['runs']} draws"[:120],
        root=root,
    )
    return sha, run.id


# ── comparing options (scenarios) on the same draws ──────────────────


def run_compare(
    target: str,
    scenarios: list[str],
    *,
    state: str | None = None,
    evidence: dict[str, str] | None = None,
    soft: dict[str, dict[str, float]] | None = None,
    likelihood: dict[str, dict[str, float]] | None = None,
    reference: str | None = None,
    runs: int = 500,
    seed: int = 1234,
    max_seconds: float = 60.0,
    root: Path | None = None,
) -> dict:
    """P(target = state) under the baseline network and each saved BN scenario, on the same table draws.

    ``evidence``/``soft``/``likelihood`` hold for every option, the baseline included (a scenario's own
    say about a factor gives way to it). ``reference``: 'baseline' or a compared scenario every option
    is measured against; left out, an option extending a compared scenario is measured against it.
    ``runs=0`` (or no table uncertainty) compares point probabilities only."""
    from latris.operations import bn_compare, uncertainty

    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    ss_map = {e.target_id: e.states for e in _load_state_spaces(paths).entries}
    labels = {e.id: e.label for e in substrate.entities}
    cpt_map = _effective_cpt_map(paths)
    given = {"evidence": _resolve_block(evidence, substrate), "soft": _resolve_block(soft, substrate),
             "likelihood": _resolve_block(likelihood, substrate)}
    names = list(dict.fromkeys(scenarios))
    arms = [with_scenario(n, paths, cpt_map, labels=labels, **given) for n in [None, *names]]
    noisy = {e.target_id: e for e in _load_noisy_or(paths).entries}
    return bn_compare.compare_options(
        ss_map, cpt_map, noisy, uncertainty.bn_specs(paths), arms, resolve_target(target, substrate),
        state=state, runs=runs, seed=seed, reference=reference, max_seconds=max_seconds, labels=labels,
        intervene=lambda tables, do: intervene(tables, ss_map, do),
    )


def record_compare(payload: dict, *, root: Path | None = None) -> tuple[str, str]:
    import json

    import pgmpy

    from latris.operations.analysis_results import record_result
    from latris.operations.bn_compare import describe_option

    summary = (f"Options compared on P({payload['label']} = {payload['focus_state']})"
               + (f", {payload['runs']} paired draws of the tables" if payload["runs"] else "") + ": "
               + "; ".join(describe_option(payload, r) for r in payload["options"]))
    sha, run = record_result(
        kind="bn-options",
        key=f"bn-options|{payload['target']}={payload['focus_state']}|" + json.dumps(sorted(payload["scenarios"]))
            + (f"|ref:{payload['reference']}" if payload.get("reference") else "") + "|"
            + evidence_key(payload["evidence"], payload["soft"], payload["likelihood"]),
        payload=payload,
        purpose="inference",
        algorithm=("paired monte-carlo[dirichlet]; " if payload["runs"] else "") + "variable_elimination",
        library_version=f"pgmpy {pgmpy.__version__}",
        summary=summary[:2000],
        model_type=_MODEL_TYPE,
        hyperparameters={"target": payload["target"], "state": payload["focus_state"],
                         "scenarios": payload["scenarios"], "evidence": payload["evidence"],
                         "soft": payload["soft"], "likelihood": payload["likelihood"], "runs": payload["runs"],
                         **({"reference": payload["reference"]} if payload.get("reference") else {})},
        scenarios=payload["scenarios"],
        uncertainty=bool(payload["runs"]),
        seed=payload["seed"] if payload["runs"] else None,
        metrics={"runs": payload["runs"], "seconds": payload["seconds"]},
        affected_target_ids=[payload["target"]],
        duration_seconds=payload["seconds"],
        commit_subject=f"BN options compared: {', '.join(payload['scenarios'])}"[:120],
        root=root,
    )
    return sha, run.id
