"""The most likely explanation (MAP / MPE): the single likeliest combination of states.

"Given the flood, what's the likeliest combination of causes?" Marginal
posteriors answer one node at a time; the most probable *joint* assignment can
differ from the per-node favourites, which is why it's its own question. With
no ``over`` this is the most probable explanation (MPE) of every node not
observed; with ``over`` it's MAP over just those nodes.

Alongside the assignment it reports how sure it is: the assignment's posterior
probability, and for each node how many times likelier its state is than the
runner-up with everything else held — so a reader sees which parts of the
explanation are decisive and which are near coin-flips.
"""

from __future__ import annotations

from typing import Any

from latris.operations import _bn_engine
from latris.operations.bn_inference import applied_likelihood, bn_infer
from latris.schema.bn import CPTEntry

MAX_CELLS = 4096


def explain(
    state_spaces: dict[str, list[str]],
    cpts: dict[str, CPTEntry],
    *,
    over: list[str] | None = None,
    evidence: dict[str, str] | None = None,
    soft: dict[str, dict[str, float]] | None = None,
    likelihood: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    evidence = dict(evidence or {})
    # bn_infer validates the evidence and gives the per-node marginals to compare against.
    marg = bn_infer(state_spaces, cpts, query=over, evidence=evidence, soft=soft, likelihood=likelihood)
    variables = [n for n in (over or list(cpts)) if n not in evidence]
    if not variables:
        raise ValueError("every node is observed; there is nothing left to explain")

    network = _bn_engine.build_network(state_spaces, cpts)
    soft_done = {k: dict(v) for k, v in (soft or {}).items()}
    applied = applied_likelihood(network, state_spaces, evidence, soft_done, dict(likelihood or {}))
    best = _bn_engine.map_assignment(network, variables, evidence, likelihood=applied or None)
    joint = _bn_engine.joint_posterior(network, variables, evidence, likelihood=applied or None, max_cells=MAX_CELLS)

    rows = []
    probability = None
    if joint is not None:
        key = tuple(best[v] for v in variables)
        probability = joint.get(key, 0.0)
    for i, v in enumerate(variables):
        state = best[v]
        own = marg.marginals.get(v, {})
        favourite = max(own, key=own.get) if own else state  # type: ignore[arg-type]
        margin = None
        runner = None
        certain = False
        if joint is not None and probability:
            alternatives = []
            for s in state_spaces[v]:
                if s == state:
                    continue
                alt = list(key)
                alt[i] = s
                alternatives.append((joint.get(tuple(alt), 0.0), s))
            if alternatives:
                p_alt, runner = max(alternatives)
                margin = probability / p_alt if p_alt > 0 else None
                certain = p_alt <= 0
        rows.append(
            {
                "node": v,
                "state": state,
                "marginal": own.get(state),
                "favourite": favourite,
                # A tie isn't a difference: only when the node's own favourite is strictly likelier.
                "differs_from_marginal": own.get(favourite, 0.0) > own.get(state, 0.0) + 1e-9,
                "runner_up": runner,
                "times_likelier": margin,  # None when not computed, or when the alternatives are impossible
                "alternatives_impossible": certain,
            }
        )

    return {
        "over": variables,
        "kind": "MPE" if over is None else "MAP",
        "assignment": best,
        "probability": probability,
        "rows": rows,
        "evidence": evidence,
        "soft": soft_done,
        "likelihood": dict(likelihood or {}),
        "note": None
        if joint is not None
        else (f"too many combinations to give the explanation's probability (over {MAX_CELLS}); narrow it with --over"),
        "method": marg.method,
    }
