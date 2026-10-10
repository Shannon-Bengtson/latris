"""pgmpy adapter — the ONLY module in the package that imports pgmpy.

Builds a pgmpy ``DiscreteBayesianNetwork`` from our schema and runs exact
inference, mapping results back to plain dicts. pgmpy types never escape this
module; everything else speaks our schema + plain Python.

pgmpy is imported lazily (inside the functions) so that importing
``latris`` does not require the optional ``quant`` extra — only actually
running inference does. The network structure is taken from each CPT's declared
``parents`` (not from substrate edges), so the built network always matches the
quantification it carries.

pgmpy ``TabularCPD`` column convention (pinned via tests/operations/test_bn_spike
and a probe): columns enumerate the parents' state combinations with the FIRST
parent varying slowest and the LAST fastest — i.e. ``itertools.product`` over
parents in ``evidence`` order.
"""

from __future__ import annotations

import itertools

from latris.schema.bn import CPTEntry


def _import_pgmpy():
    try:
        from pgmpy.factors.discrete import TabularCPD
        from pgmpy.inference import VariableElimination
        from pgmpy.models import DiscreteBayesianNetwork
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise RuntimeError(
            "Bayesian Network inference requires the 'quant' extra. "
            "Install it with: pip install 'latris[quant]'"
        ) from exc
    return DiscreteBayesianNetwork, TabularCPD, VariableElimination


def build_network(state_spaces: dict[str, list[str]], cpts: dict[str, CPTEntry]):
    """Construct and validate a pgmpy network from state spaces + CPTs.

    Raises ``ValueError`` on any malformed input (missing state space, a CPT row
    that doesn't match the node's parents, a missing parent-state combination,
    or a distribution that doesn't normalise). This is independent of the
    readiness layer — defence in depth at the compute boundary.
    """
    DiscreteBayesianNetwork, TabularCPD, _ = _import_pgmpy()

    # Structure derives from each CPT's declared parents.
    edges = [(parent, nid) for nid, cpt in cpts.items() for parent in cpt.parents]
    network = DiscreteBayesianNetwork()
    network.add_nodes_from(list(cpts.keys()))
    network.add_edges_from(edges)

    tabular_cpds = []
    for nid, cpt in cpts.items():
        if nid not in state_spaces:
            raise ValueError(f"node {nid!r} has a CPT but no state space")
        states = state_spaces[nid]
        card = len(states)
        parents = list(cpt.parents)
        for parent in parents:
            if parent not in state_spaces:
                raise ValueError(f"parent {parent!r} of node {nid!r} has no state space")

        # Column order pgmpy expects: product over parents' states, first slowest.
        combos = list(itertools.product(*[state_spaces[p] for p in parents])) if parents else [()]

        row_by_combo: dict[tuple[str, ...], list[float]] = {}
        for row in cpt.rows:
            try:
                key = tuple(row.parent_states[p] for p in parents)
            except KeyError as exc:
                raise ValueError(
                    f"CPT row for node {nid!r} is missing parent assignment for {exc.args[0]!r}"
                ) from exc
            row_by_combo[key] = row.p

        values = [[0.0] * len(combos) for _ in range(card)]
        for col, combo in enumerate(combos):
            probs = row_by_combo.get(combo)
            if probs is None:
                raise ValueError(
                    f"CPT for node {nid!r} is missing the row for parent states {combo}"
                )
            for i in range(card):
                values[i][col] = probs[i]

        state_names = {nid: states}
        for p in parents:
            state_names[p] = state_spaces[p]

        kwargs = {"state_names": state_names}
        if parents:
            kwargs["evidence"] = parents
            kwargs["evidence_card"] = [len(state_spaces[p]) for p in parents]
        tabular_cpds.append(TabularCPD(nid, card, values, **kwargs))

    network.add_cpds(*tabular_cpds)
    try:
        network.check_model()
    except Exception as exc:  # pgmpy raises ValueError-ish on bad/unnormalised CPDs
        raise ValueError(f"invalid Bayesian Network: {exc}") from exc
    return network


def query_marginals(
    network,
    targets: list[str],
    evidence: dict[str, str],
) -> dict[str, dict[str, float]]:
    """Exact posterior marginal for each target node, given evidence.

    Returns ``node_id -> {state: probability}``. Each target is queried
    independently so the result is per-node marginals (not a joint).
    """
    _, _, VariableElimination = _import_pgmpy()
    infer = VariableElimination(network)

    out: dict[str, dict[str, float]] = {}
    for node in targets:
        factor = infer.query(variables=[node], evidence=evidence or None, show_progress=False)
        states = factor.state_names[node]
        out[node] = {state: float(factor.values[i]) for i, state in enumerate(states)}
    return out
