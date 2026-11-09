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

import itertools
from pathlib import Path

from latris.operations._bn_canonical import effective_cpt_map
from latris.operations._resolve import resolve_target
from latris.operations.bn_inference import BNInferenceResult, bn_infer
from latris.operations.commit import auto_commit
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_model, load_model
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
    return load_model(StateSpaceSet, p) if p.exists() else StateSpaceSet()


def _load_cpts(paths) -> CPTSet:
    p = _cpt_path(paths)
    return load_model(CPTSet, p) if p.exists() else CPTSet()


def _load_noisy_or(paths) -> NoisyOrSet:
    p = _noisy_or_path(paths)
    return load_model(NoisyOrSet, p) if p.exists() else NoisyOrSet()


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


def _dump(path: Path, store) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    dump_model(store, path)


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
    _dump(path, store)
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
    _dump(path, store)
    sha = auto_commit(
        paths.root,
        subject=f"Set BN CPT on {node_id[:15]}… ({len(rows)} row(s))",
        body=f"target: {node_id}\nparents: {parent_ids}\norigin: {origin}\nsource_id: {source_id}",
        paths=[path],
    )
    return cpt, sha


def set_noisy_or(
    node: str,
    leak: float,
    causes: list[tuple[str, str, float]],
    *,
    origin: ProvenanceOrigin = "human-elicited",
    source_id: str | None = None,
    root: Path | None = None,
) -> tuple[NoisyOrEntry, str]:
    """Set (or replace) a node's Noisy-OR parameterisation.

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
        links=links, origin=origin, source_id=source_id,
    )
    store = _load_noisy_or(paths)
    store.entries = [e for e in store.entries if e.target_id != node_id]
    store.entries.append(entry)

    path = _noisy_or_path(paths)
    _dump(path, store)
    sha = auto_commit(
        paths.root,
        subject=f"Set BN Noisy-OR on {node_id[:15]}… ({len(links)} cause(s), leak {leak})",
        body=f"target: {node_id}\nparents: {parent_ids}\nleak: {leak}\norigin: {origin}",
        paths=[path],
    )
    return entry, sha


# ── reads ────────────────────────────────────────────────────────────


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
    ctx = ValidationContext(
        substrate=substrate,
        view_entity_ids=[e.id for e in substrate.entities],
        view_edge_ids=[e.id for e in substrate.edges],
        spec=get_model_type(_MODEL_TYPE),
        roles=RoleSet(),
        paths=paths,
    )
    gaps = []
    gaps.extend(_check_acyclicity(ctx))
    gaps.extend(_check_state_space_defined(ctx))
    gaps.extend(_check_cpt_complete(ctx))
    return gaps


# ── inference ────────────────────────────────────────────────────────


def infer(
    *,
    query: list[str] | None = None,
    evidence: dict[str, str] | None = None,
    soft: dict[str, dict[str, float]] | None = None,
    likelihood: dict[str, dict[str, float]] | None = None,
    root: Path | None = None,
) -> BNInferenceResult:
    """Load the BN and compute exact posterior marginals.

    ``query`` and the keys of ``evidence``, ``soft`` and ``likelihood`` accept
    node IDs, ID prefixes, or labels; they are resolved to IDs before inference.
    The result is keyed by node ID.
    """
    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)

    ss_map = {e.target_id: e.states for e in _load_state_spaces(paths).entries}
    cpt_map = _effective_cpt_map(paths)

    def ids(block):  # noqa: ANN001, ANN202
        return {resolve_target(k, substrate): v for k, v in block.items()} if block else None

    query_ids = [resolve_target(q, substrate) for q in query] if query else None
    return bn_infer(
        ss_map, cpt_map, query=query_ids, evidence=ids(evidence), soft=ids(soft), likelihood=ids(likelihood)
    )


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
    conditioned = bool(result.evidence or result.soft or result.likelihood)
    priors = infer(query=nodes, root=paths.root).marginals if conditioned else result.marginals
    evidence_text = evidence_description(result.evidence, result.soft, result.likelihood, labels)

    def top(node: str) -> str:
        dist = result.marginals[node]
        state = max(dist, key=dist.get)  # type: ignore[arg-type]
        return f"{labels.get(node, node)}: {state} {dist[state]:.0%}"

    sha, run = record_result(
        kind="bn-query",
        key="bn-query|" + ",".join(nodes) + "|" + evidence_key(result.evidence, result.soft, result.likelihood),
        payload={
            "evidence": result.evidence, "soft": result.soft, "likelihood": result.likelihood,
            "posteriors": result.marginals, "priors": priors,
            "labels": {n: labels.get(n, n) for n in {*nodes, *result.evidence, *result.soft, *result.likelihood}},
            "method": result.method,
        },
        purpose="inference",
        algorithm=result.method,
        library_version=f"pgmpy {pgmpy.__version__}",
        summary=f"P(· | {evidence_text or 'no evidence'}): " + "; ".join(top(n) for n in nodes[:8]),
        model_type=_MODEL_TYPE,
        hyperparameters={"query": nodes, "evidence": result.evidence, "soft": result.soft,
                         "likelihood": result.likelihood},
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


def _resolve_block(block, substrate):  # noqa: ANN001, ANN202
    return {resolve_target(k, substrate): v for k, v in block.items()} if block else {}


# ── most likely explanation ──────────────────────────────────────────


def explain(
    *,
    over: list[str] | None = None,
    evidence: dict[str, str] | None = None,
    soft: dict[str, dict[str, float]] | None = None,
    likelihood: dict[str, dict[str, float]] | None = None,
    root: Path | None = None,
) -> dict:
    """The most likely joint explanation (MPE, or MAP over ``over``) given the evidence; labels accepted."""
    from latris.operations import bn_explain

    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    ss_map = {e.target_id: e.states for e in _load_state_spaces(paths).entries}
    out = bn_explain.explain(
        ss_map, _effective_cpt_map(paths),
        over=[resolve_target(n, substrate) for n in over] if over else None,
        evidence=_resolve_block(evidence, substrate), soft=_resolve_block(soft, substrate),
        likelihood=_resolve_block(likelihood, substrate),
    )
    labels = {e.id: e.label for e in substrate.entities}
    out["labels"] = {n: labels.get(n, n) for n in {*out["over"], *out["evidence"], *out["soft"], *out["likelihood"]}}
    return out


def describe_explanation(p: dict) -> str:
    labels = p["labels"]
    cond = evidence_description(p["evidence"], p["soft"], p["likelihood"], labels) or "no evidence"
    states = ", ".join(f"{labels.get(n, n)} = {p['assignment'][n]}" for n in p["over"])
    prob = f" (P = {p['probability']:.0%})" if p.get("probability") is not None else ""
    return f"Given {cond}, the most likely explanation is {states}{prob}"


def record_explanation(payload: dict, *, root: Path | None = None) -> tuple[str, str]:
    import pgmpy

    from latris.operations.analysis_results import record_result

    sha, run = record_result(
        kind="bn-explanation",
        key="bn-explanation|" + ",".join(sorted(payload["over"])) + "|"
            + evidence_key(payload["evidence"], payload["soft"], payload["likelihood"]),
        payload=payload,
        purpose="inference",
        algorithm=f"{payload['kind']}; {payload['method']}",
        library_version=f"pgmpy {pgmpy.__version__}",
        summary=describe_explanation(payload),
        model_type=_MODEL_TYPE,
        hyperparameters={"over": payload["over"] if payload["kind"] == "MAP" else None,
                         "evidence": payload["evidence"], "soft": payload["soft"], "likelihood": payload["likelihood"]},
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
    runs: int = 500,
    seed: int = 1234,
    max_seconds: float = 60.0,
    root: Path | None = None,
) -> dict:
    """Re-ask P(target | evidence) under draws of every table that has an uncertainty ("worth n")."""
    from latris.operations import bn_montecarlo, uncertainty

    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    ss_map = {e.target_id: e.states for e in _load_state_spaces(paths).entries}
    labels = {e.id: e.label for e in substrate.entities}
    noisy = {e.target_id: e for e in _load_noisy_or(paths).entries}
    return bn_montecarlo.monte_carlo(
        ss_map, _effective_cpt_map(paths), noisy, uncertainty.bn_specs(paths), resolve_target(target, substrate),
        state=state, evidence=_resolve_block(evidence, substrate), soft=_resolve_block(soft, substrate),
        likelihood=_resolve_block(likelihood, substrate), runs=runs, seed=seed, max_seconds=max_seconds,
        labels=labels,
    )


def record_monte_carlo(payload: dict, *, root: Path | None = None) -> tuple[str, str]:
    import pgmpy

    from latris.operations.analysis_results import record_result
    from latris.operations.bn_montecarlo import describe

    sha, run = record_result(
        kind="bn-monte-carlo",
        key=f"bn-monte-carlo|{payload['target']}={payload['focus_state']}|"
            + evidence_key(payload["evidence"], payload["soft"], payload["likelihood"]),
        payload=payload,
        purpose="sensitivity-analysis",
        algorithm="monte-carlo[dirichlet]; variable_elimination",
        library_version=f"pgmpy {pgmpy.__version__}",
        summary=describe(payload),
        model_type=_MODEL_TYPE,
        hyperparameters={"target": payload["target"], "state": payload["focus_state"],
                         "evidence": payload["evidence"], "soft": payload["soft"],
                         "likelihood": payload["likelihood"], "runs": payload["runs"]},
        uncertainty=True,
        seed=payload["seed"],
        metrics={"runs": payload["runs"], "seconds": payload["seconds"]},
        affected_target_ids=[payload["target"]],
        duration_seconds=payload["seconds"],
        commit_subject=f"BN Monte Carlo: {payload['runs']} draws"[:120],
        root=root,
    )
    return sha, run.id
