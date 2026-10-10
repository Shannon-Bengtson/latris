"""Bayesian Network parameter learning — fit CPTs from a dataset.

Wraps pgmpy's estimators (MLE / Bayesian-Dirichlet) and folds the result
back into our CPT store with provenance. The merge policy is deliberate and
provenance-first: rows a human elicited or verified are **protected** — data
fills only the gaps and the low-provenance defaults. A blended table becomes
``origin="mixed"``; learned rows are ``data-derived`` and point ``source_id``
at the :class:`AnalysisRun` that produced them.

Two-step like the AI proposal flow: :func:`learn_cpts` computes a preview
(no writes); :func:`apply_learned` records the run and commits.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from pathlib import Path

from latris.operations import bn as bn_ops
from latris.operations.analysis_runs import record_run
from latris.operations.commit import auto_commit
from latris.repo.project import require_project
from latris.repo.yaml_io import load_model
from latris.schema import Substrate
from latris.schema.bn import CPTEntry, CPTRow

# Rows at or above this provenance are protected from being overwritten by data.
_PROTECTED_ORIGINS = {"human-elicited"}


@dataclass
class NodeLearnDiff:
    node_id: str
    parents: list[str]
    rows_learned: int = 0
    rows_kept: int = 0
    zero_support_combos: int = 0
    merged: CPTEntry | None = None
    skipped_reason: str | None = None


@dataclass
class LearnProposal:
    dataset_id: str
    estimator: str
    prior: str
    ess: int
    library_version: str
    rows_used: int
    rows_dropped_na: int
    diffs: list[NodeLearnDiff] = field(default_factory=list)

    @property
    def affected_ids(self) -> list[str]:
        return [d.node_id for d in self.diffs if d.skipped_reason is None and d.merged is not None]


def _row_key(parent_states: dict[str, str]) -> frozenset:
    return frozenset(parent_states.items())


def _is_protected(row: CPTRow) -> bool:
    return row.origin in _PROTECTED_ORIGINS or row.verification == "human-verified"


def learn_cpts(
    dataset: str,
    *,
    nodes: list[str] | None = None,
    estimator: str = "bayesian",
    prior: str = "BDeu",
    equivalent_sample_size: int = 5,
    root: Path | None = None,
) -> LearnProposal:
    """Compute a parameter-learning preview (no writes).

    Learns the full BN from ``dataset`` (every BN node must map to a column;
    column name matches the node label or id, values must be declared states),
    then merges per node under the protect-expert policy. ``nodes`` optionally
    restricts which nodes are written.
    """
    import pgmpy
    from pgmpy.models import DiscreteBayesianNetwork

    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)

    bn_nodes, parent_map = bn_ops.bn_structure(substrate)
    if not bn_nodes:
        raise ValueError("no BN nodes — add causal edges before learning CPTs")

    ss_map = {e.target_id: e.states for e in bn_ops.get_state_spaces(root=paths.root).entries}
    missing_ss = sorted(n for n in bn_nodes if n not in ss_map)
    if missing_ss:
        labels = {e.id: e.label for e in substrate.entities}
        names = ", ".join(labels.get(n, n) for n in missing_ss)
        raise ValueError(f"set state spaces before learning: {names}")

    # Resolve which nodes to write (default: all).
    from latris.operations._resolve import resolve_target

    target_ids = (
        {resolve_target(n, substrate) for n in nodes} if nodes else set(bn_nodes)
    )

    from latris.operations.datasets import get_dataset

    ds = get_dataset(dataset, root=paths.root)
    df, rows_used, rows_dropped = _load_mapped_dataframe(paths, substrate, ds, bn_nodes, ss_map)

    # Fit the whole network; pick out the nodes we're writing.
    model = DiscreteBayesianNetwork()
    model.add_nodes_from(sorted(bn_nodes))
    model.add_edges_from(
        [(p, child) for child, ps in parent_map.items() for p in ps]
    )
    state_names = {n: list(ss_map[n]) for n in bn_nodes}
    cpds = _fit(model, df, state_names, estimator=estimator, prior=prior, ess=equivalent_sample_size)
    cpd_by_var = {c.variable: c for c in cpds}

    noisy_or_nodes = {e.target_id for e in bn_ops.get_noisy_or(root=paths.root).entries}
    existing = bn_ops.effective_cpts(root=paths.root)

    proposal = LearnProposal(
        dataset_id=ds.id,
        estimator=estimator,
        prior=prior if estimator == "bayesian" else "",
        ess=equivalent_sample_size,
        library_version=pgmpy.__version__,
        rows_used=rows_used,
        rows_dropped_na=rows_dropped,
    )

    for nid in sorted(target_ids):
        parents = parent_map.get(nid, [])
        diff = NodeLearnDiff(node_id=nid, parents=parents)
        if nid in noisy_or_nodes:
            diff.skipped_reason = "node uses a Noisy-OR spec (protected)"
            proposal.diffs.append(diff)
            continue

        learned = _cpd_to_entry(cpd_by_var[nid], parents, state_names)
        diff.zero_support_combos = _count_zero_support(df, nid, parents, state_names)
        prior_entry = existing.get(nid)
        diff.merged = _merge(learned, prior_entry, diff)
        proposal.diffs.append(diff)

    return proposal


def apply_learned(proposal: LearnProposal, *, root: Path | None = None) -> tuple[str, str]:
    """Write the merged CPTs and record the AnalysisRun. Returns (commit_sha, run_id)."""
    paths = require_project(root)
    affected = proposal.affected_ids
    if not affected:
        raise ValueError("nothing to apply (every targeted node was skipped or unchanged)")

    metrics = {
        "rows_used": proposal.rows_used,
        "rows_dropped_na": proposal.rows_dropped_na,
        "nodes_learned": len(affected),
        "rows_learned": sum(d.rows_learned for d in proposal.diffs),
        "rows_kept": sum(d.rows_kept for d in proposal.diffs),
        "zero_support_combos": sum(d.zero_support_combos for d in proposal.diffs),
    }
    algorithm = (
        f"bayesian-{proposal.prior}" if proposal.estimator == "bayesian" else proposal.estimator
    )
    run, _ = record_run(
        purpose="parameter-estimation",
        algorithm=algorithm,
        library_version=proposal.library_version,
        hyperparameters={"estimator": proposal.estimator, "prior": proposal.prior, "ess": proposal.ess},
        input_dataset_ids=[proposal.dataset_id],
        output_summary=f"Learned CPTs for {len(affected)} node(s) from {proposal.dataset_id}",
        metrics=metrics,
        affected_target_ids=affected,
        commit=False,
        root=paths.root,
    )

    # Stamp learned rows with the run id, then upsert into the CPT store.
    store = bn_ops._load_cpts(paths)
    by_id = {e.target_id: e for e in store.entries}
    for diff in proposal.diffs:
        if diff.skipped_reason or diff.merged is None:
            continue
        for row in diff.merged.rows:
            if row.origin == "data-derived" and row.source_id is None:
                row.source_id = run.id
        by_id[diff.node_id] = diff.merged
    store.entries = list(by_id.values())

    cpt_path = bn_ops._cpt_path(paths)
    bn_ops._dump(cpt_path, store)
    sha = auto_commit(
        paths.root,
        subject=f"Learn BN CPTs: {len(affected)} node(s) from {proposal.dataset_id[:20]}…",
        body=f"run: {run.id}\nestimator: {algorithm}\nmetrics: {metrics}",
        paths=[cpt_path, paths.analysis_runs_jsonl],
    )
    return sha, run.id


# ── internals ────────────────────────────────────────────────────────


def _load_mapped_dataframe(paths, substrate, ds, bn_nodes, ss_map):
    """Load the dataset, map columns→node ids by convention, validate states."""
    from latris.operations._data_engine import load_dataframe

    df = load_dataframe(paths.root / ds.location)

    labels = {e.id: e.label for e in substrate.entities}
    col_lower = {c.lower(): c for c in df.columns}
    rename: dict[str, str] = {}
    missing: list[str] = []
    for nid in bn_nodes:
        label = labels.get(nid, "")
        if nid in df.columns:
            rename[nid] = nid
        elif label and label.lower() in col_lower:
            rename[col_lower[label.lower()]] = nid
        else:
            missing.append(label or nid)
    if missing:
        raise ValueError(
            "dataset is missing a column for: " + ", ".join(sorted(missing))
            + " (column name must match the node label or id)"
        )

    df = df[list(rename.keys())].rename(columns=rename)
    rows_before = len(df)
    df = df.dropna()
    # Coerce to string to match declared (string) state names.
    for nid in df.columns:
        df[nid] = df[nid].astype(str)
        bad = set(df[nid].unique()) - set(ss_map[nid])
        if bad:
            label = labels.get(nid, nid)
            raise ValueError(
                f"column {label!r} has values not in its state space {ss_map[nid]}: {sorted(bad)}"
            )
    return df, len(df), rows_before - len(df)


def _fit(model, df, state_names, *, estimator, prior, ess):
    from pgmpy.parameter_estimator import DiscreteBayesianEstimator, DiscreteMLE

    if estimator == "mle":
        return DiscreteMLE(state_names=state_names).fit(model, df).parameters_
    if estimator == "bayesian":
        return (
            DiscreteBayesianEstimator(
                state_names=state_names, prior_type=prior, equivalent_sample_size=ess
            )
            .fit(model, df)
            .parameters_
        )
    raise ValueError(f"unknown estimator {estimator!r} (use 'bayesian' or 'mle')")


def _cpd_to_entry(cpd, parents, state_names) -> CPTEntry:
    """Convert a pgmpy TabularCPD to our CPTEntry, reading cells by state name
    (independent of pgmpy's column ordering)."""
    nid = cpd.variable
    node_states = state_names[nid]
    combos = (
        list(itertools.product(*[state_names[p] for p in parents])) if parents else [()]
    )
    rows: list[CPTRow] = []
    for combo in combos:
        assignment = {p: s for p, s in zip(parents, combo, strict=True)}
        probs = [float(cpd.get_value(**{nid: st, **assignment})) for st in node_states]
        rows.append(CPTRow(parent_states=assignment, p=probs, origin="data-derived"))
    return CPTEntry(
        target_id=nid, parents=list(parents), states=list(node_states), rows=rows, origin="data-derived"
    )


def _merge(learned: CPTEntry, existing: CPTEntry | None, diff: NodeLearnDiff) -> CPTEntry:
    """Protect-expert merge: keep existing rows that are human-elicited or
    human-verified; otherwise take the learned row."""
    if existing is None:
        diff.rows_learned = len(learned.rows)
        return learned

    existing_by_key = {_row_key(r.parent_states): r for r in existing.rows}
    merged_rows: list[CPTRow] = []
    for lrow in learned.rows:
        ex = existing_by_key.get(_row_key(lrow.parent_states))
        if ex is not None and _is_protected(ex):
            merged_rows.append(ex)
            diff.rows_kept += 1
        else:
            merged_rows.append(lrow)
            diff.rows_learned += 1

    if diff.rows_kept and diff.rows_learned:
        origin = "mixed"
    elif diff.rows_learned:
        origin = "data-derived"
    else:
        origin = existing.origin
    return CPTEntry(
        target_id=learned.target_id,
        parents=learned.parents,
        states=learned.states,
        rows=merged_rows,
        origin=origin,
    )


def _count_zero_support(df, nid, parents, state_names) -> int:
    """Parent-state combinations with no observations (prior-only rows)."""
    if not parents:
        return 0
    expected = set(itertools.product(*[state_names[p] for p in parents]))
    observed = {tuple(r) for r in df[parents].itertuples(index=False, name=None)}
    return len(expected - observed)
