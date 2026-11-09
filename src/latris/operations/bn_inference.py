"""Discrete Bayesian Network inference — exact posterior marginals, with hard and soft evidence.

Pure function — no file I/O, no commits. Callers load state spaces + CPTs and
pass them in. The pgmpy backend is confined to ``_bn_engine`` (the only module
that imports pgmpy); this module stays dependency-light and returns plain dicts.

Evidence comes in three forms:

- **hard**: ``{node: state}`` — the node is observed in that state;
- **soft** (certainty): ``{node: {state: probability}}`` — after the update the
  node's distribution *is* this ("I'm 80% sure it's wet"). This is Jeffrey's
  rule; it's fitted on top of likelihood evidence by :func:`fit_soft_evidence`;
- **likelihood**: ``{node: {state: weight}}`` — how much the observation favours
  each state ("4 times likelier if wet"); passed to pgmpy as virtual evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from latris.operations import _bn_engine
from latris.schema.bn import CPTEntry
from latris.schema.settings import BNSettings

_TOL = 1e-9
_MAX_ROUNDS = 50


@dataclass(frozen=True)
class BNInferenceResult:
    """Result of exact BN inference."""

    marginals: dict[str, dict[str, float]]
    """Posterior per queried node: node_id → {state: probability}."""

    evidence: dict[str, str]
    """The hard evidence the query was conditioned on (echoed back)."""

    method: str
    """Inference algorithm used."""

    soft: dict[str, dict[str, float]] = field(default_factory=dict)
    """Soft (certainty) evidence: node_id → the distribution it was set to."""

    likelihood: dict[str, dict[str, float]] = field(default_factory=dict)
    """Likelihood evidence as given: node_id → {state: weight}."""

    fitted_likelihood: dict[str, dict[str, float]] = field(default_factory=dict)
    """The likelihood weights actually applied (soft evidence fitted, then given likelihoods)."""


def _check_distribution(node: str, dist: dict[str, float], states: list[str], what: str) -> None:
    unknown = [s for s in dist if s not in states]
    if unknown:
        raise ValueError(f"{what} on {node!r} names unknown state(s) {unknown} (allowed: {states})")
    if any(v < 0 for v in dist.values()):
        raise ValueError(f"{what} on {node!r} has a negative value")


def complete_soft(dist: dict[str, float], states: list[str], prior: dict[str, float]) -> dict[str, float]:
    """Fill in a partially given certainty: the rest is shared by the other states in proportion to their prior.

    ``{"yes": 0.8}`` on a yes/no node → ``{"yes": 0.8, "no": 0.2}``. That's the smallest change
    to the other states that makes the distribution sum to 1.
    """
    given = sum(dist.values())
    if given > 1 + 1e-9:
        raise ValueError(f"soft evidence adds up to {given:g}; probabilities must total 1")
    rest = [s for s in states if s not in dist]
    if not rest:
        if abs(given - 1) > 1e-6:
            raise ValueError(f"soft evidence adds up to {given:g}; probabilities must total 1")
        return {s: dist[s] / given for s in states}
    remaining = max(0.0, 1.0 - given)
    weight = sum(prior.get(s, 0.0) for s in rest)
    out = dict(dist)
    for s in rest:
        out[s] = remaining * (prior.get(s, 0.0) / weight if weight > 0 else 1 / len(rest))
    return {s: out[s] for s in states}


def fit_soft_evidence(
    network,
    soft: dict[str, dict[str, float]],
    evidence: dict[str, str],
    likelihood: dict[str, dict[str, float]] | None = None,
) -> dict[str, dict[str, float]]:
    """Likelihood weights that make each soft node's posterior equal its target (Jeffrey's rule).

    For one soft node a single step is exact: weight each state by target / current
    probability. With several, they interact; iterate (each node refitted with the
    others' current weights) until every target is met. Raises if a target puts
    probability on a state the rest of the evidence makes impossible.
    """
    weights: dict[str, dict[str, float]] = {n: dict.fromkeys(d, 1.0) for n, d in soft.items()}
    fixed = dict(likelihood or {})

    def combined(skip: str | None = None) -> dict[str, dict[str, float]]:
        out = {k: dict(v) for k, v in fixed.items()}
        for n, w in weights.items():
            if n == skip:
                continue
            if n in out:
                out[n] = {s: out[n].get(s, 0.0) * w.get(s, 0.0) for s in set(out[n]) | set(w)}
            else:
                out[n] = dict(w)
        return out

    for _ in range(_MAX_ROUNDS):
        worst = 0.0
        for node, target in soft.items():
            others = combined(skip=node)
            if node in fixed:
                others[node] = fixed[node]
            (current,) = _bn_engine.query_marginals(network, [node], evidence, likelihood=others or None).values()
            new = {}
            for state, q in target.items():
                p = current.get(state, 0.0)
                if q > 0 and p <= 0:
                    raise ValueError(
                        f"soft evidence puts {q:.0%} on {node} = {state}, which the other evidence makes impossible"
                    )
                new[state] = q / p if q > 0 else 0.0
            weights[node] = new
        for node, target in soft.items():
            (post,) = _bn_engine.query_marginals(network, [node], evidence, likelihood=combined() or None).values()
            worst = max(worst, max(abs(post.get(s, 0.0) - q) for s, q in target.items()))
        if worst < _TOL:
            break
    else:
        raise ValueError("the soft evidence can't all be met at once (the targets conflict)")
    return combined()


def bn_infer(
    state_spaces: dict[str, list[str]],
    cpts: dict[str, CPTEntry],
    *,
    query: list[str] | None = None,
    evidence: dict[str, str] | None = None,
    soft: dict[str, dict[str, float]] | None = None,
    likelihood: dict[str, dict[str, float]] | None = None,
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
        is not pinned by hard evidence.
    evidence
        node_id → observed state. Posteriors are conditioned on this.
    soft
        node_id → {state: probability}: certainty (Jeffrey) evidence. States left
        out share the remainder in proportion to their prior.
    likelihood
        node_id → {state: weight}: likelihood (virtual) evidence.
    settings
        BN settings. Only exact ``variable_elimination`` is currently
        supported (the engine hardcodes it); the field exists for forward
        compatibility. Uses defaults if not provided.

    Raises
    ------
    ValueError
        On malformed input (missing/invalid state spaces or CPTs, unknown
        evidence node or state, a query for an unknown node, or soft evidence
        that can't be met).
    """
    if settings is None:
        settings = BNSettings()
    evidence = dict(evidence or {})
    soft = {k: dict(v) for k, v in (soft or {}).items()}
    likelihood = {k: dict(v) for k, v in (likelihood or {}).items()}

    # Validate evidence against the declared state spaces before touching pgmpy,
    # so the error message points at our model, not the backend internals.
    for node, state in evidence.items():
        if node not in cpts:
            raise ValueError(f"evidence node {node!r} is not in the network")
        if node not in state_spaces or state not in state_spaces[node]:
            allowed = state_spaces.get(node, [])
            raise ValueError(f"state {state!r} is not a valid state for node {node!r} (allowed: {allowed})")
    for what, block in (("soft evidence", soft), ("likelihood evidence", likelihood)):
        for node, dist in block.items():
            if node not in cpts:
                raise ValueError(f"{what} node {node!r} is not in the network")
            if node in evidence:
                raise ValueError(f"{node!r} has both hard and {what}; give one")
            _check_distribution(node, dist, state_spaces.get(node, []), what)

    if query is None:
        targets = [nid for nid in cpts if nid not in evidence]
    else:
        unknown = [n for n in query if n not in cpts]
        if unknown:
            raise ValueError(f"query node(s) not in the network: {unknown}")
        targets = [n for n in query if n not in evidence]

    if not targets:
        return BNInferenceResult(marginals={}, evidence=evidence, method=settings.inference_algorithm,
                                 soft=soft, likelihood=likelihood)

    network = _bn_engine.build_network(state_spaces, cpts)
    applied = applied_likelihood(network, state_spaces, evidence, soft, likelihood)
    marginals = _bn_engine.query_marginals(network, targets, evidence, likelihood=applied or None)
    return BNInferenceResult(
        marginals=marginals,
        evidence=evidence,
        method=settings.inference_algorithm,
        soft={n: d for n, d in soft.items()},
        likelihood=likelihood,
        fitted_likelihood=applied,
    )


def applied_likelihood(
    network,
    state_spaces: dict[str, list[str]],
    evidence: dict[str, str],
    soft: dict[str, dict[str, float]],
    likelihood: dict[str, dict[str, float]],
) -> dict[str, dict[str, float]]:
    """The likelihood weights to give the engine: soft evidence completed and fitted, plus given likelihoods.

    ``soft`` is completed in place (states left out get their share of the remainder).
    """
    if soft:
        priors = _bn_engine.query_marginals(network, list(soft), evidence, likelihood=likelihood or None)
        for node in list(soft):
            soft[node] = complete_soft(soft[node], state_spaces[node], priors[node])
        return fit_soft_evidence(network, soft, evidence, likelihood)
    return {k: dict(v) for k, v in likelihood.items()}
