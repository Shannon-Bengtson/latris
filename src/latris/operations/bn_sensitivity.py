"""BN sensitivity analysis — one-way tornado with a provenance overlay.

For a chosen target posterior, vary each CPT conditional and measure how much
the target moves. Findings are ranked (the tornado) and annotated with each
parameter's provenance — so you can see when a conclusion hinges on cells that
are unverified, AI-proposed, or contested. No incumbent surfaces this: it fuses
classic sensitivity with our per-cell provenance.

Read-only on the stored CPTs (perturbations happen on in-memory copies). The
run is logged as an :class:`AnalysisRun` with the result persisted to
``analysis/outputs/``.
"""

from __future__ import annotations

from pathlib import Path

from latris.operations import bn as bn_ops
from latris.operations._bn_engine import build_network, query_marginals
from latris.operations._resolve import resolve_target
from latris.repo.project import require_project
from latris.repo.yaml_io import load_model
from latris.schema import Substrate
from latris.schema.bn import SensitivityFinding, SensitivityResult


def _row_posterior(base_map, ss_map, node_id, row_idx, cell_idx, value, target, target_state, evidence):
    """Target posterior after setting one CPT cell to ``value`` (others in the
    row renormalised proportionally). Operates on a deep copy."""
    entry = base_map[node_id].model_copy(deep=True)
    p = list(entry.rows[row_idx].p)
    old = p[cell_idx]
    rest = 1.0 - old
    new_rest = 1.0 - value
    if rest > 1e-12:
        scale = new_rest / rest
        p = [pi * scale for pi in p]
    else:  # row was degenerate at this cell; spread the remainder evenly
        others = len(p) - 1
        p = [new_rest / others if others else 1.0] * len(p)
    p[cell_idx] = value
    entry.rows[row_idx].p = p

    cmap = dict(base_map)
    cmap[node_id] = entry
    net = build_network(ss_map, cmap)
    return query_marginals(net, [target], evidence)[target][target_state]


def sensitivity(
    target: str,
    target_state: str,
    *,
    evidence: dict[str, str] | None = None,
    top: int | None = None,
    root: Path | None = None,
) -> SensitivityResult:
    """Rank CPT conditionals by their one-way influence on ``P(target=state|evidence)``.

    Each row's most influential cell is swept across a range: the 5th–95th
    percentile of its uncertainty when the table has one ("worth n observations",
    ``bn set-uncertainty``), otherwise the whole of 0 to 1 — said so in
    ``range_source``, because a 0-to-1 swing overstates what's plausible.
    """
    from latris.operations import uncertainty as unc
    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    target_id = resolve_target(target, substrate)
    evidence_ids = {resolve_target(k, substrate): v for k, v in (evidence or {}).items()}

    ss_map = {e.target_id: e.states for e in bn_ops.get_state_spaces(root=paths.root).entries}
    base_map = bn_ops.effective_cpts(root=paths.root)

    if target_id not in base_map:
        raise ValueError(f"{target!r} has no CPT to analyse")
    if target_state not in ss_map.get(target_id, []):
        raise ValueError(f"{target_state!r} is not a state of {target!r} (states: {ss_map.get(target_id)})")

    base_net = build_network(ss_map, base_map)
    baseline = query_marginals(base_net, [target_id], evidence_ids)[target_id][target_state]

    specs = unc.bn_specs(paths)

    def cell_range(node_id: str, entry, row, p: float) -> tuple[float, float, str]:  # noqa: ANN001
        node_specs = specs.get(node_id, {})
        spec = node_specs.get(unc.row_cell(entry.parents, row.parent_states)) if entry.parents else None
        spec = spec or node_specs.get(unc.BN_TABLE)
        if spec is None or not 0 < p < 1:
            return 0.0, 1.0, "any value from 0 to 1"
        from latris.operations._sampling import Sampler
        from latris.schema.attributes import ParameterUncertainty

        n = spec.params["n"]
        beta = Sampler(ParameterUncertainty(target_id=node_id, distribution="beta",
                                            params={"alpha": n * p, "beta": n * (1 - p)}))
        return beta.quantile(0.05), beta.quantile(0.95), f"5th–95th percentile, worth {n:g} observations"

    runs = 0
    findings: list[SensitivityFinding] = []
    for node_id, entry in base_map.items():
        if node_id in evidence_ids:
            continue  # clamped — perturbing its CPT can't move the posterior
        for row_idx, row in enumerate(entry.rows):
            best_inf = -1.0
            best_cell = 0
            best_range = (0.0, 1.0, "any value from 0 to 1")
            for cell_idx in range(len(row.p)):
                low, high, source = cell_range(node_id, entry, row, row.p[cell_idx])
                lo = _row_posterior(base_map, ss_map, node_id, row_idx, cell_idx, low,
                                    target_id, target_state, evidence_ids)
                hi = _row_posterior(base_map, ss_map, node_id, row_idx, cell_idx, high,
                                    target_id, target_state, evidence_ids)
                runs += 2
                inf = abs(hi - lo)
                if inf > best_inf:
                    best_inf, best_cell, best_range = inf, cell_idx, (low, high, source)
            weak = (row.verification != "human-verified") or row.contested
            findings.append(
                SensitivityFinding(
                    node_id=node_id,
                    parent_states=dict(row.parent_states),
                    state=entry.states[best_cell],
                    influence=best_inf,
                    baseline_prob=row.p[best_cell],
                    origin=row.origin,
                    verification=row.verification,
                    source_id=row.source_id,
                    contested=row.contested,
                    weak=weak,
                    low=best_range[0],
                    high=best_range[1],
                    range_source=best_range[2],
                )
            )

    findings.sort(key=lambda f: f.influence, reverse=True)
    if top is not None:
        findings = findings[:top]
    return SensitivityResult(
        target_id=target_id,
        target_state=target_state,
        evidence=evidence_ids,
        baseline=baseline,
        inference_runs=runs,
        findings=findings,
    )


def record_sensitivity(result: SensitivityResult, *, root: Path | None = None) -> tuple[str, str]:
    """Persist a sensitivity result as a result reports show, and log an AnalysisRun.

    Returns (commit_sha, run_id)."""
    import pgmpy

    from latris.operations.analysis_results import record_result

    evidence = ",".join(f"{k}={v}" for k, v in sorted((result.evidence or {}).items()))
    sha, run = record_result(
        kind="bn-sensitivity",
        key=f"bn-sensitivity|{result.target_id}={result.target_state}|{evidence}",
        payload=result.model_dump(mode="json"),
        purpose="sensitivity-analysis",
        algorithm="one-way-tornado",
        library_version=f"pgmpy {pgmpy.__version__}",
        summary=(
            f"Sensitivity of P({result.target_id}={result.target_state}) "
            f"= {result.baseline:.3f}; {len(result.findings)} parameter(s) ranked"
        ),
        model_type="bn",
        hyperparameters={"target": result.target_id, "target_state": result.target_state,
                         "evidence": result.evidence},
        metrics={"inference_runs": result.inference_runs, "baseline": result.baseline},
        affected_target_ids=[result.target_id],
        commit_subject=f"Sensitivity analysis: {result.target_id[:15]}…={result.target_state}",
        root=root,
    )
    return sha, run.id
