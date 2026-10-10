"""Discrete Bayesian Network inference — exact posterior marginals.

Pure function — no file I/O, no commits. Callers load state spaces + CPTs and
pass them in. The pgmpy backend is confined to ``_bn_engine`` (the only module
that imports pgmpy); this module stays dependency-light and returns plain dicts.
"""

from __future__ import annotations

from dataclasses import dataclass

from latris.operations import _bn_engine
from latris.schema.bn import CPTEntry
from latris.schema.settings import BNSettings


@dataclass(frozen=True)
class BNInferenceResult:
    """Result of exact BN inference."""

    marginals: dict[str, dict[str, float]]
    """Posterior per queried node: node_id → {state: probability}."""

    evidence: dict[str, str]
    """The evidence the query was conditioned on (echoed back)."""

    method: str
    """Inference algorithm used."""


def bn_infer(
    state_spaces: dict[str, list[str]],
    cpts: dict[str, CPTEntry],
    *,
    query: list[str] | None = None,
    evidence: dict[str, str] | None = None,
    settings: BNSettings | None = None,
) -> BNInferenceResult:
    """Compute exact posterior marginals for a discrete BN.

    Parameters
    ----------
    state_spaces
        node_id → ordered list of discrete states.
    cpts
        node_id → :class:`CPTEntry` (defines structure via its parents).
    query
        Nodes to compute marginals for. Defaults to every node with a CPT that
        is not pinned by evidence.
    evidence
        node_id → observed state. Posteriors are conditioned on this.
    settings
        BN settings. Only exact ``variable_elimination`` is currently
        supported (the engine hardcodes it); the field exists for forward
        compatibility. Uses defaults if not provided.

    Returns
    -------
    BNInferenceResult

    Raises
    ------
    ValueError
        On malformed input (missing/invalid state spaces or CPTs, unknown
        evidence node or state, or a query for an unknown node).
    """
    if settings is None:
        settings = BNSettings()
    evidence = dict(evidence or {})

    # Validate evidence against the declared state spaces before touching pgmpy,
    # so the error message points at our model, not the backend internals.
    for node, state in evidence.items():
        if node not in cpts:
            raise ValueError(f"evidence node {node!r} is not in the network")
        if node not in state_spaces or state not in state_spaces[node]:
            allowed = state_spaces.get(node, [])
            raise ValueError(f"state {state!r} is not a valid state for node {node!r} (allowed: {allowed})")

    if query is None:
        targets = [nid for nid in cpts if nid not in evidence]
    else:
        unknown = [n for n in query if n not in cpts]
        if unknown:
            raise ValueError(f"query node(s) not in the network: {unknown}")
        targets = [n for n in query if n not in evidence]

    if not targets:
        return BNInferenceResult(marginals={}, evidence=evidence, method=settings.inference_algorithm)

    network = _bn_engine.build_network(state_spaces, cpts)
    marginals = _bn_engine.query_marginals(network, targets, evidence)
    return BNInferenceResult(
        marginals=marginals,
        evidence=evidence,
        method=settings.inference_algorithm,
    )
