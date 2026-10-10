"""Canonical-model expansion — Noisy-OR → full CPT.

Pure functions (no I/O): expand a stored canonical spec into the same
:class:`CPTEntry` the inference engine and readiness layer already consume,
and merge the tabular + canonical stores into one effective CPT map. The spec
stays the source of truth; this expansion is derived at compute time.
"""

from __future__ import annotations

import itertools

from latris.schema.bn import (
    CPTEntry,
    CPTRow,
    CPTSet,
    NoisyOrEntry,
    NoisyOrSet,
)


def expand_noisy_or(entry: NoisyOrEntry, state_spaces: dict[str, list[str]]) -> CPTEntry:
    """Expand a Noisy-OR spec into a full CPT.

    For each parent-state combination with active set S (parents whose state
    equals their link's ``active_state``):
    ``P(active) = 1 - (1 - leak) · ∏_{i∈S} (1 - prob_i)``.
    The expanded rows inherit the spec's table-level provenance, so downstream
    readers (inference, sensitivity) see where the canonical numbers came from.
    """
    if entry.target_id not in state_spaces:
        raise ValueError(f"Noisy-OR node {entry.target_id!r} has no state space")
    node_states = state_spaces[entry.target_id]
    if list(node_states) != list(entry.states):
        raise ValueError(
            f"Noisy-OR states {entry.states!r} for {entry.target_id!r} disagree with the "
            f"declared state space {node_states!r}"
        )
    if len(node_states) != 2:
        raise ValueError(f"Noisy-OR node {entry.target_id!r} must be binary")

    link_by_parent = {link.parent_id: link for link in entry.links}
    for p in entry.parents:
        if p not in state_spaces:
            raise ValueError(f"parent {p!r} of Noisy-OR node {entry.target_id!r} has no state space")
        if len(state_spaces[p]) != 2:
            raise ValueError(f"Noisy-OR parent {p!r} must be binary")
        if link_by_parent[p].active_state not in state_spaces[p]:
            raise ValueError(
                f"active_state {link_by_parent[p].active_state!r} is not a state of parent {p!r} "
                f"(states: {state_spaces[p]})"
            )

    combos = (
        list(itertools.product(*[state_spaces[p] for p in entry.parents]))
        if entry.parents
        else [()]
    )
    rows: list[CPTRow] = []
    for combo in combos:
        inactive_product = 1.0 - entry.leak
        for p, state in zip(entry.parents, combo, strict=True):
            if state == link_by_parent[p].active_state:
                inactive_product *= 1.0 - link_by_parent[p].prob
        p_active = 1.0 - inactive_product
        rows.append(
            CPTRow(
                parent_states={p: s for p, s in zip(entry.parents, combo, strict=True)},
                p=[p_active, 1.0 - p_active],  # states[0] is the active outcome
                origin=entry.origin,
                verification=entry.verification,
                source_id=entry.source_id,
            )
        )
    return CPTEntry(
        target_id=entry.target_id,
        parents=list(entry.parents),
        states=list(entry.states),
        rows=rows,
        origin=entry.origin,
        verification=entry.verification,
        source_id=entry.source_id,
    )


def effective_cpt_map(
    cpts: CPTSet,
    noisy_or: NoisyOrSet,
    state_spaces: dict[str, list[str]],
) -> dict[str, CPTEntry]:
    """Merge tabular CPTs with expanded Noisy-OR specs into one node→CPT map.

    Raises if a node carries both a tabular CPT and a canonical spec.
    """
    out: dict[str, CPTEntry] = {e.target_id: e for e in cpts.entries}
    for ne in noisy_or.entries:
        if ne.target_id in out:
            raise ValueError(
                f"node {ne.target_id!r} has both a tabular CPT and a Noisy-OR spec; "
                f"keep only one"
            )
        out[ne.target_id] = expand_noisy_or(ne, state_spaces)
    return out
