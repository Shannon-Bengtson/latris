"""Effect estimation on a DAG — how big is the effect of X on Y, under the DAG's assumptions?

The DAG analyses say *whether* an effect can be estimated and what must be
adjusted for (the backdoor criterion: Pearl 2009; Hernán & Robins 2020).
This takes the next step with a dataset:

1. **Measured variables.** A factor is measured when the dataset has a
   column named like it (its label or id, any case) or one named for it
   explicitly.
2. **Adjustment set.** One you give is checked against the DAG; otherwise
   the smallest valid backdoor set made only of measured factors is chosen.
   If every valid set needs something the dataset doesn't have, it says
   what to measure instead of estimating something biased.
3. **Model.** Ordinary least squares with heteroskedasticity-robust (HC3)
   standard errors for a numeric outcome; logistic regression for a two-
   valued outcome (odds ratio, and the average change in probability).
   Complete cases only; rows with a missing value are counted and dropped.
4. **Comparison.** The same model without adjustment, so a reader sees how
   much the adjustment moved the estimate.

What it is *not*: proof of causation. The estimate is the effect of X on Y
only if the DAG is right (no confounder left out of it), the model's form is
right (linear and additive in the adjustment variables), and every kind of
unit can receive every level of X (positivity). The payload states these
assumptions, and the report repeats them.
"""

from __future__ import annotations

import hashlib
import itertools
import math
from pathlib import Path
from typing import Any, Literal

from latris.operations import graph_analysis as ga
from latris.operations._graph_checks import find_cycle
from latris.operations._resolve import resolve_entity
from latris.repo.project import require_project
from latris.repo.yaml_io import load_model
from latris.schema import Substrate

MODEL_TYPE = "dag"
Estimator = Literal["auto", "linear", "logistic"]
MAX_SEARCH_SIZE = 6
MAX_SEARCH_CHECKS = 50_000
ASSUMPTIONS = (
    "The DAG is right: no common cause of the treatment and the outcome is missing from it.",
    "The model's form is right: the outcome depends linearly (or, for a yes/no outcome, logistically) and "
    "additively on the adjustment variables.",
    "Positivity: units with every combination of the adjustment variables could receive every treatment level.",
    "Rows with a missing value are left out (complete-case analysis), which is unbiased only if they are "
    "missing for reasons unrelated to the outcome.",
)


class EstimationError(ValueError):
    """The effect can't be estimated as asked; the message says why and what would fix it."""


# ── identification on measured variables ─────────────────────────────


def _descendants(node: str, edges) -> set[str]:
    children: dict[str, list[str]] = {}
    for e in edges:
        children.setdefault(e.from_id, []).append(e.to_id)
    out: set[str] = set()
    stack = list(children.get(node, []))
    while stack:
        n = stack.pop()
        if n not in out:
            out.add(n)
            stack.extend(children.get(n, []))
    return out


def is_valid_adjustment(treatment: str, outcome: str, edges, z: set[str]) -> str | None:
    """None if ``z`` satisfies the backdoor criterion for treatment → outcome; else why not."""
    desc = _descendants(treatment, edges)
    bad = sorted(z & (desc | {treatment, outcome}))
    if bad:
        return "descendant" if (set(bad) & desc) else "endpoint"
    manipulated = [e for e in edges if e.from_id != treatment]
    if not ga.d_separation(manipulated, {treatment}, {outcome}, set(z)):
        return "open_backdoor"
    return None


def choose_adjustment(treatment: str, outcome: str, edges, measured: set[str]) -> tuple[set[str] | None, dict]:
    """The smallest valid backdoor set using only measured factors, and what the search found.

    Tries the DAG's minimal sets first, then subsets of the measured non-descendants of the treatment in
    increasing size (up to ``MAX_SEARCH_SIZE`` factors, ``MAX_SEARCH_CHECKS`` checks).
    """
    minimal = ga.adjustment_sets(treatment, outcome, edges)
    info: dict[str, Any] = {"minimal_sets": [sorted(s) for s in minimal], "searched_to": None}
    usable = sorted((s for s in minimal if s <= measured), key=lambda s: (len(s), sorted(s)))
    if usable:
        return set(usable[0]), info
    nodes = {e.from_id for e in edges} | {e.to_id for e in edges}
    candidates = sorted((measured & nodes) - _descendants(treatment, edges) - {treatment, outcome})
    checks = 0
    for size in range(0, min(MAX_SEARCH_SIZE, len(candidates)) + 1):
        info["searched_to"] = size
        for combo in itertools.combinations(candidates, size):
            checks += 1
            if checks > MAX_SEARCH_CHECKS:
                return None, info
            if is_valid_adjustment(treatment, outcome, edges, set(combo)) is None:
                return set(combo), info
    return None, info


# ── data ─────────────────────────────────────────────────────────────


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _map_columns(df, entities, overrides: dict[str, str]) -> dict[str, str]:
    """Entity id → dataset column, by explicit override or by matching the label or id."""
    by_lower = {str(c).lower(): c for c in df.columns}
    out: dict[str, str] = {}
    for e in entities:
        if e.id in overrides:
            col = overrides[e.id]
            if col not in df.columns:
                raise EstimationError(f"the dataset has no column {col!r} (given for {e.label})")
            out[e.id] = col
        elif e.label.lower() in by_lower:
            out[e.id] = by_lower[e.label.lower()]
        elif e.id.lower() in by_lower:
            out[e.id] = by_lower[e.id.lower()]
    return out


def _numeric(series, label: str, role: str):
    """A numeric version of a column: numbers as they are, a two-valued column as 0/1. Returns (series, coding)."""
    import pandas as pd

    if pd.api.types.is_bool_dtype(series):
        return series.astype(float), {"0": "False", "1": "True"}
    if pd.api.types.is_numeric_dtype(series):
        return series.astype(float), None
    values = sorted(series.dropna().astype(str).unique())
    if len(values) == 2:
        return (series.astype(str) == values[1]).astype(float), {"0": values[0], "1": values[1]}
    raise EstimationError(
        f"{label} ({role}) has {len(values)} text categories; it needs numbers or exactly two values "
        "(e.g. yes/no). Recode it in the data workspace first."
    )


def _two_valued(series) -> bool:
    return series.dropna().nunique() == 2


# ── estimation ───────────────────────────────────────────────────────


def _fit(y, X, logistic: bool):
    import statsmodels.api as sm

    X = sm.add_constant(X, has_constant="add")
    if logistic:
        try:
            return sm.Logit(y, X).fit(disp=0)
        except Exception as exc:  # perfect separation, singular matrix, …
            raise EstimationError(f"the logistic model couldn't be fitted ({exc}); the treatment or an "
                                  "adjustment variable may predict the outcome perfectly") from exc
    return sm.OLS(y, X).fit(cov_type="HC3")


def _coef(res, term: str, logistic: bool) -> dict[str, float]:
    ci = res.conf_int().loc[term]
    out = {"estimate": float(res.params[term]), "se": float(res.bse[term]), "ci_low": float(ci.iloc[0]),
           "ci_high": float(ci.iloc[1]), "p": float(res.pvalues[term])}
    if logistic:
        out.update(odds_ratio=math.exp(out["estimate"]), or_ci_low=math.exp(out["ci_low"]),
                   or_ci_high=math.exp(out["ci_high"]))
    return out


def _require_acyclic(edges: list[Any], labels: dict[str, str]) -> None:
    has_cycle, node = find_cycle(edges)
    if has_cycle and node is not None:
        raise EstimationError(f"the causal links loop (through {labels.get(node, node)}); effect estimation needs "
                              "an acyclic graph — use a DAG view without feedback")


_INVALID_ADJUSTMENT = {
    "descendant": "it includes a factor the treatment affects, which would block part of the effect or open a new path",
    "endpoint": "it includes the treatment or the outcome itself",
    "open_backdoor": "it leaves a backdoor path from the treatment to the outcome open",
}


def _given_adjustment(x: str, y: str, edges: list[Any], z: set[str], measured: set[str],
                      labels: dict[str, str]) -> dict[str, Any]:
    """Check an adjustment set the caller gave; returns the minimal sets for the record."""
    unmeasured = sorted(labels[n] for n in z - measured)
    if unmeasured:
        raise EstimationError(f"the dataset has no column for {', '.join(unmeasured)}")
    why = is_valid_adjustment(x, y, edges, z)
    if why:
        raise EstimationError(f"that adjustment set isn't valid for this DAG: {_INVALID_ADJUSTMENT[why]}")
    return {"minimal_sets": [sorted(s) for s in ga.adjustment_sets(x, y, edges)]}


def _chosen_adjustment(x: str, y: str, edges: list[Any], measured: set[str], labels: dict[str, str]
                       ) -> tuple[set[str], dict[str, Any]]:
    """The smallest valid adjustment set of measured factors, or a refusal naming what to measure."""
    chosen, search = choose_adjustment(x, y, edges, measured)
    if chosen is None:
        needs = sorted({labels[n] for s in search["minimal_sets"] for n in s} - {labels[n] for n in measured})
        hint = f" Measure one of: {', '.join(needs)}." if needs else ""
        raise EstimationError(
            f"no valid adjustment set uses only what the dataset measures, so the effect of {labels[x]} on "
            f"{labels[y]} can't be estimated without bias under this DAG.{hint}"
        )
    return chosen, search


def _numeric_columns(frame: Any, colmap: dict[str, str], order: list[str], x: str, y: str,
                     labels: dict[str, str]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Each factor's column as numbers, and how any categories were coded."""
    coding: dict[str, Any] = {}
    data = {}
    for n in order:
        role = "outcome" if n == y else "treatment" if n == x else "adjustment"
        col, code = _numeric(frame[colmap[n]], labels[n], role)
        data[n] = col
        if code:
            coding[labels[n]] = code
    return data, coding


def _is_logistic(estimator: Estimator, yv: Any, outcome_label: str) -> bool:
    if estimator == "auto":
        return _two_valued(yv)
    logistic = estimator == "logistic"
    if logistic and not _two_valued(yv):
        raise EstimationError(f"a logistic model needs a two-valued outcome; {outcome_label} has "
                              f"{yv.nunique()} values")
    return logistic


def _main_effect(adjusted: Any, term: str, logistic: bool) -> dict[str, float | None]:
    main: dict[str, float | None] = dict(_coef(adjusted, term, logistic))
    if logistic:
        try:
            me = adjusted.get_margeff(at="overall").summary_frame().loc[term]
            main["marginal_effect"] = float(me.iloc[0])
        except Exception:  # noqa: BLE001 — the marginal effect is a convenience, not the estimate
            main["marginal_effect"] = None
    return main


def _warnings(treatment: Any, n_complete: int, n_coefficients: int, dropped: int, n_rows: int) -> list[str]:
    warnings: list[str] = []
    if _two_valued(treatment):
        counts = treatment.value_counts()
        if counts.min() < 10:
            warnings.append(f"only {int(counts.min())} row(s) in one treatment group; the estimate is fragile")
    per_param = n_complete / n_coefficients
    if per_param < 10:
        warnings.append(f"about {per_param:.0f} rows per coefficient; with fewer than 10 the estimate is unstable")
    if dropped:
        warnings.append(f"{dropped} of {n_rows} rows dropped for missing values")
    return warnings


def estimate(
    treatment: str,
    outcome: str,
    dataset: str,
    *,
    adjust: list[str] | None = None,
    columns: dict[str, str] | None = None,
    estimator: Estimator = "auto",
    root: Path | None = None,
) -> dict[str, Any]:
    """Estimate the effect of ``treatment`` on ``outcome`` from ``dataset``, adjusting as the DAG requires.

    ``adjust`` overrides the chosen adjustment set (it is checked, not trusted); ``columns`` maps factor
    labels to dataset columns where the names differ.
    """
    import pandas as pd
    import statsmodels

    from latris.operations import datasets as data_ops
    from latris.operations._data_engine import load_dataframe

    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    labels = {e.id: e.label for e in substrate.entities}
    edges = ga.causal_edges(substrate.edges)
    _require_acyclic(edges, labels)
    x = resolve_entity(treatment, substrate.entities).id
    y = resolve_entity(outcome, substrate.entities).id
    if x == y:
        raise EstimationError("the treatment and the outcome are the same factor")

    ds = data_ops.get_dataset(dataset, root=paths.root)
    file = paths.root / ds.location
    df = load_dataframe(file)
    overrides = {resolve_entity(k, substrate.entities).id: v for k, v in (columns or {}).items()}
    colmap = _map_columns(df, substrate.entities, overrides)
    measured = set(colmap)
    for nid, role in ((x, "treatment"), (y, "outcome")):
        if nid not in measured:
            raise EstimationError(f"the dataset has no column for {labels[nid]} ({role}); name a column for it "
                                  f"with --column \"{labels[nid]}=<column>\"")

    if adjust is not None:
        z = {resolve_entity(a, substrate.entities).id for a in adjust}
        how, search = "given", _given_adjustment(x, y, edges, z, measured, labels)
    else:
        z, search = _chosen_adjustment(x, y, edges, measured, labels)
        how = "smallest valid set of measured factors"

    order = [x, *sorted(z, key=lambda n: labels[n]), y]
    frame = df[[colmap[n] for n in order]].copy()
    n_rows = len(frame)
    frame = frame.dropna()
    dropped = n_rows - len(frame)
    if len(frame) < len(order) + 2:
        raise EstimationError(f"only {len(frame)} complete row(s) — too few to estimate {len(order) - 1} "
                              "coefficient(s)")

    data, coding = _numeric_columns(frame, colmap, order, x, y, labels)
    yv = data[y]
    logistic = _is_logistic(estimator, yv, labels[y])

    def design(cols: list[str]):
        return pd.DataFrame({labels[c]: data[c] for c in cols}, index=frame.index)

    adjusted = _fit(yv, design([x, *sorted(z, key=lambda n: labels[n])]), logistic)
    unadjusted = _fit(yv, design([x]), logistic)
    term = labels[x]
    main = _main_effect(adjusted, term, logistic)
    warnings = _warnings(data[x], len(frame), len(order), dropped, n_rows)

    return {
        "treatment": labels[x], "outcome": labels[y],
        "treatment_id": x, "outcome_id": y,
        "dataset": {"id": ds.id, "name": ds.name, "location": ds.location, "sha256": _file_hash(file)},
        "columns": {labels[n]: colmap[n] for n in order},
        "coding": coding,
        "adjustment": [labels[n] for n in sorted(z, key=lambda n: labels[n])],
        "adjustment_how": how,
        "minimal_sets": [[labels[n] for n in s] for s in search.get("minimal_sets", [])],
        "measured": sorted(labels[n] for n in measured),
        "model": "logistic" if logistic else "linear",
        "se_type": "maximum likelihood" if logistic else "HC3 robust",
        "effect": main,
        "unadjusted": _coef(unadjusted, term, logistic),
        "covariates": {c: _coef(adjusted, c, logistic) for c in adjusted.params.index if c not in ("const", term)},
        "n": int(len(frame)), "dropped": int(dropped),
        "fit": {"r2": float(adjusted.rsquared)} if not logistic else {"pseudo_r2": float(adjusted.prsquared)},
        "warnings": warnings,
        "assumptions": list(ASSUMPTIONS),
        "library_version": f"statsmodels {statsmodels.__version__}",
    }


def describe(p: dict[str, Any]) -> str:
    e = p["effect"]
    adj = f"adjusting for {', '.join(p['adjustment'])}" if p["adjustment"] else "no adjustment needed"
    if p["model"] == "logistic":
        size = (f"odds ratio {e['odds_ratio']:.3g} (95% CI {e['or_ci_low']:.3g}–{e['or_ci_high']:.3g})"
                + (f", about {e['marginal_effect']:+.3g} in probability per unit of {p['treatment']}"
                   if e.get("marginal_effect") is not None else ""))
    else:
        size = (f"{e['estimate']:+.4g} in {p['outcome']} per unit of {p['treatment']} "
                f"(95% CI {e['ci_low']:.4g} to {e['ci_high']:.4g})")
    return f"Effect of {p['treatment']} on {p['outcome']} ({p['dataset']['name']}, n={p['n']}, {adj}): {size}"


def record(payload: dict[str, Any], *, root: Path | None = None) -> tuple[str, str]:
    """Record an estimate so reports show it. Returns (commit_sha, run_id)."""
    from latris.operations.analysis_results import record_result

    sha, run = record_result(
        kind="dag-estimate",
        key=f"dag-estimate|{payload['treatment_id']}|{payload['outcome_id']}|{payload['dataset']['id']}",
        payload=payload,
        purpose="parameter-estimation",
        algorithm=f"backdoor adjustment; {payload['model']} regression ({payload['se_type']} standard errors)",
        library_version=payload["library_version"],
        summary=describe(payload),
        model_type=MODEL_TYPE,
        hyperparameters={"adjustment": payload["adjustment"], "adjustment_how": payload["adjustment_how"],
                         "columns": payload["columns"], "model": payload["model"]},
        input_dataset_ids=[payload["dataset"]["id"]],
        metrics={"n": payload["n"], "estimate": payload["effect"]["estimate"], "p": payload["effect"]["p"]},
        affected_target_ids=[payload["treatment_id"], payload["outcome_id"]],
        commit_subject=f"Analysis: effect of {payload['treatment']} on {payload['outcome']}",
        root=root,
    )
    return sha, run.id
