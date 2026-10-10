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

import json
from pathlib import Path

from latris.operations import bn as bn_ops
from latris.operations._bn_engine import build_network, query_marginals
from latris.operations._resolve import resolve_target
from latris.operations.analysis_runs import record_run
from latris.operations.commit import auto_commit
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

    Each row is swept over the full [0, 1] range of its most-influential cell.
    """
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

    runs = 0
    findings: list[SensitivityFinding] = []
    for node_id, entry in base_map.items():
        if node_id in evidence_ids:
            continue  # clamped — perturbing its CPT can't move the posterior
        for row_idx, row in enumerate(entry.rows):
            best_inf = -1.0
            best_cell = 0
            for cell_idx in range(len(row.p)):
                lo = _row_posterior(base_map, ss_map, node_id, row_idx, cell_idx, 0.0,
                                    target_id, target_state, evidence_ids)
                hi = _row_posterior(base_map, ss_map, node_id, row_idx, cell_idx, 1.0,
                                    target_id, target_state, evidence_ids)
                runs += 2
                inf = abs(hi - lo)
                if inf > best_inf:
                    best_inf, best_cell = inf, cell_idx
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
    """Persist a sensitivity result to ``analysis/outputs/`` and log an AnalysisRun.

    Returns (commit_sha, run_id)."""
    import pgmpy

    from latris.schema import new_id

    paths = require_project(root)
    # Name the artifact by a fresh unique slug so it can be recorded *in* the run.
    slug = new_id("analysis-run").split("_", 1)[1]
    paths.analysis_outputs_dir.mkdir(parents=True, exist_ok=True)
    artifact = paths.analysis_outputs_dir / f"sensitivity-{slug}.json"
    artifact.write_text(json.dumps(result.model_dump(mode="json"), indent=2), encoding="utf-8")
    rel = artifact.relative_to(paths.root).as_posix()

    run, _ = record_run(
        purpose="sensitivity-analysis",
        algorithm="one-way-tornado",
        library_version=pgmpy.__version__,
        hyperparameters={"target": result.target_id, "target_state": result.target_state,
                         "evidence": result.evidence},
        output_summary=(
            f"Sensitivity of P({result.target_id}={result.target_state}) "
            f"= {result.baseline:.3f}; {len(result.findings)} parameter(s) ranked"
        ),
        output_artifacts=[rel],
        metrics={"inference_runs": result.inference_runs, "baseline": result.baseline},
        affected_target_ids=[result.target_id],
        commit=False,
        root=paths.root,
    )
    sha = auto_commit(
        paths.root,
        subject=f"Sensitivity analysis: {result.target_id[:15]}…={result.target_state}",
        body=f"run: {run.id}\nartifact: {rel}",
        paths=[artifact, paths.analysis_runs_jsonl],
    )
    return sha, run.id
