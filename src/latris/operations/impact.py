"""Impact estimation for a theory of change — did the outcome change when the intervention started?

Two quasi-experimental designs on a registered dataset, for one factor of the
theory of change (usually an outcome or the impact):

- **Interrupted time series** (no comparison group): segmented regression of
  the outcome on time, a step at the start and a change of slope after it
  (Wagner et al. 2002; Bernal, Cummins & Gasparrini 2017). The effect at the
  last period is the gap between the fitted series and the pre-period trend
  projected forward. Errors are modelled as AR(1) (Prais & Winsten 1954), so
  autocorrelation doesn't make the interval falsely narrow.
- **Difference-in-differences** (a comparison group): the change in the
  treated group minus the change in the comparison group, from
  ``y ~ treated + post + treated:post`` (Angrist & Pischke 2009). Before
  estimating, the pre-period trends of the two groups are compared — the
  design's central assumption is that they would have stayed parallel.

The validity guardrails are the substance: each design states what it assumes,
and the result carries a warning for each check that fails or can't be made
(too few periods, autocorrelation, diverging pre-trends, too few groups to
cluster, irregular time spacing). Rows are aggregated to one value per period
(per group, for DiD).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from latris.operations._resolve import resolve_entity
from latris.repo.project import require_project
from latris.repo.yaml_io import load_model
from latris.schema import Substrate

MODEL_TYPE = "theory_of_change"
MIN_PERIODS = 3  # per segment, to fit at all
ADVISED_PERIODS = 8  # per segment, for a stable ITS (Wagner et al. 2002)
MIN_CLUSTERS = 20  # groups needed for cluster-robust errors to be trusted

ITS_ASSUMPTIONS = (
    "Nothing else that affects the outcome changed at the same time as the intervention.",
    "Without the intervention, the pre-period trend would have continued in a straight line.",
    "How the outcome is measured, and who it is measured on, didn't change at the start.",
    "Seasonality, if any, is not confused with the change (the model has no seasonal terms).",
)
DID_ASSUMPTIONS = (
    "Without the intervention, the treated and comparison groups would have changed in parallel.",
    "Nothing else that affects the outcome changed for one group and not the other at the start.",
    "The intervention didn't affect the comparison group (no spill-over), and group membership didn't change "
    "because of it.",
)


class ImpactError(ValueError):
    pass


def _times(series):
    """Numeric time values: numbers as they are, dates as days. Returns (values, is_date)."""
    import pandas as pd

    if pd.api.types.is_numeric_dtype(series):
        return series.astype(float), False
    parsed = pd.to_datetime(series, errors="coerce")
    if parsed.isna().any():
        bad = series[parsed.isna()].iloc[0]
        raise ImpactError(f"the time column has a value that is neither a number nor a date: {bad!r}")
    return (parsed - pd.Timestamp("1970-01-01")).dt.days.astype(float), True


def _at(value: str | float, is_date: bool) -> float:
    import pandas as pd

    if is_date:
        try:
            return float((pd.Timestamp(str(value)) - pd.Timestamp("1970-01-01")).days)
        except (ValueError, TypeError) as exc:
            raise ImpactError(f"the start {value!r} isn't a date, but the time column holds dates") from exc
    try:
        return float(value)
    except (ValueError, TypeError) as exc:
        raise ImpactError(f"the start {value!r} isn't a number, but the time column holds numbers") from exc


def _coef(res, term: str) -> dict[str, float]:
    ci = res.conf_int().loc[term]
    return {"estimate": float(res.params[term]), "se": float(res.bse[term]), "ci_low": float(ci.iloc[0]),
            "ci_high": float(ci.iloc[1]), "p": float(res.pvalues[term])}


def _contrast(res, weights: dict[str, float]) -> dict[str, float]:
    import numpy as np

    c = np.array([[weights.get(n, 0.0) for n in res.params.index]])
    t = res.t_test(c)
    ci = np.asarray(t.conf_int())[0]
    return {"estimate": float(np.asarray(t.effect).ravel()[0]), "se": float(np.asarray(t.sd).ravel()[0]),
            "ci_low": float(ci[0]), "ci_high": float(ci[1]), "p": float(np.asarray(t.pvalue).ravel()[0])}


def _spacing_warning(times) -> str | None:
    import numpy as np

    d = np.diff(np.sort(np.unique(times)))
    if len(d) and d.min() > 0 and d.max() / d.min() > 1.2:
        return ("the periods are unevenly spaced; the model treats each period as one step, so the trend is per "
                "period, not per unit of time")
    return None


def _its(frame, warnings: list[str]) -> dict[str, Any]:
    import numpy as np
    import pandas as pd
    import statsmodels.api as sm
    from statsmodels.stats.stattools import durbin_watson

    s = frame.groupby("t", sort=True)["y"].mean()
    if (frame.groupby("t").size() > 1).any():
        warnings.append("several rows share a period; each period's mean is used")
    post = s.index >= frame.attrs["at"]
    n_pre, n_post = int((~post).sum()), int(post.sum())
    if n_pre < MIN_PERIODS or n_post < MIN_PERIODS:
        raise ImpactError(f"an interrupted time series needs at least {MIN_PERIODS} periods before and after the "
                          f"start; there are {n_pre} before and {n_post} after")
    for n, when in ((n_pre, "before"), (n_post, "after")):
        if n < ADVISED_PERIODS:
            warnings.append(f"only {n} period(s) {when} the start; at least {ADVISED_PERIODS} on each side are "
                            "advised for a stable trend")
    k = np.arange(len(s), dtype=float)  # period number
    k0 = float(k[post][0])
    X = np.column_stack([k, post.astype(float), np.where(post, k - k0, 0.0)])
    X = sm.add_constant(pd.DataFrame(X, columns=["trend", "level_change", "slope_change"]), has_constant="add")
    y = s.to_numpy(dtype=float)
    ols = sm.OLS(y, X).fit()
    dw = float(durbin_watson(ols.resid))
    # Prais–Winsten-style AR(1) errors (iterated GLS): in simulation, with series this short it keeps the 95%
    # interval near its stated coverage with or without autocorrelation, where Newey–West errors fall well short.
    res = sm.GLSAR(y, X, rho=1).iterative_fit(maxiter=20)
    rho = float(res.model.rho[0])
    if abs(rho) >= 0.3 and len(y) < 50:
        warnings.append(f"the residuals are autocorrelated (lag-1 correlation {rho:.2f}); the model allows for it, "
                        "but with fewer than 50 periods the interval is still likely somewhat too narrow")
    end = float(k[-1])
    effect = _contrast(res, {"level_change": 1.0, "slope_change": end - k0})
    counterfactual = float(res.params["const"] + res.params["trend"] * end)
    fitted = X.to_numpy() @ res.params.to_numpy()
    cf = float(res.params["const"]) + float(res.params["trend"]) * k  # the pre-period trend, projected
    return {
        "periods_before": n_pre, "periods_after": n_post,
        "pre_trend": _coef(res, "trend"),
        "level_change": _coef(res, "level_change"),
        "slope_change": _coef(res, "slope_change"),
        "effect": effect,
        "counterfactual_end": counterfactual,
        "relative": effect["estimate"] / counterfactual if counterfactual else None,
        "durbin_watson": dw, "ar1": rho,
        "series": [{"time": float(t), "observed": float(o), "fitted": float(f), "counterfactual": float(c),
                    "post": bool(p)} for t, o, f, c, p in zip(s.index, y, fitted, cf, post, strict=True)],
        "fit": {"r2": float(ols.rsquared)},
    }


def _did(frame, treated_values: list[str], warnings: list[str]) -> dict[str, Any]:
    import pandas as pd
    import statsmodels.formula.api as smf

    frame = frame.copy()
    frame["treated"] = frame["g"].astype(str).isin(treated_values).astype(float)
    if frame["treated"].sum() == 0:
        raise ImpactError(f"no row's group is {', '.join(treated_values)}; check --treated against the group column")
    if frame["treated"].min() == 1:
        raise ImpactError("every row is in the treated group; difference-in-differences needs a comparison group")
    frame["post"] = (frame["t"] >= frame.attrs["at"]).astype(float)
    pre, post = frame[frame["post"] == 0], frame[frame["post"] == 1]
    if pre.empty or post.empty:
        raise ImpactError("difference-in-differences needs rows both before and after the start")
    cells = frame.groupby(["treated", "post"]).size()
    if len(cells) < 4:
        raise ImpactError("each group needs rows both before and after the start")
    groups = frame["g"].astype(str).nunique()
    if groups >= MIN_CLUSTERS:
        res = smf.ols("y ~ treated + post + treated:post", data=frame).fit(
            cov_type="cluster", cov_kwds={"groups": pd.factorize(frame["g"].astype(str))[0]})
        se_type = f"cluster-robust by group ({groups} groups)"
    else:
        res = smf.ols("y ~ treated + post + treated:post", data=frame).fit(cov_type="HC3")
        se_type = "HC3 robust"
        warnings.append(f"only {groups} group(s), too few to cluster the standard errors by group; the interval "
                        "ignores shocks shared within a group and is likely too narrow")
    # Parallel pre-trends: do the groups' trends differ before the start?
    pre_periods = pre["t"].nunique()
    if pre_periods >= 2:
        pt = smf.ols("y ~ treated * t", data=pre).fit(cov_type="HC3")
        trend = _coef(pt, "treated:t")
        trend["testable"] = True
        if trend["p"] < 0.10:
            warnings.append(f"before the start the groups' trends already differ (p = {trend['p']:.2g}); the "
                            "parallel-trends assumption looks doubtful, so the estimate may be biased")
    else:
        trend = {"testable": False}
        warnings.append("only one period before the start, so whether the groups were on parallel trends can't "
                        "be checked")
    means = frame.groupby(["treated", "post"])["y"].mean()
    return {
        "effect": _coef(res, "treated:post"),
        "se_type": se_type,
        "groups": groups,
        "periods_before": int(pre_periods), "periods_after": int(post["t"].nunique()),
        "means": {"treated_before": float(means[(1.0, 0.0)]), "treated_after": float(means[(1.0, 1.0)]),
                  "comparison_before": float(means[(0.0, 0.0)]), "comparison_after": float(means[(0.0, 1.0)])},
        "pre_trend_difference": trend,
        "fit": {"r2": float(res.rsquared)},
    }


def estimate(
    outcome: str,
    dataset: str,
    *,
    time: str,
    at: str | float,
    group: str | None = None,
    treated: list[str] | None = None,
    column: str | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    """Estimate the intervention's impact on ``outcome`` from ``dataset``.

    ``time`` is the dataset's time column (numbers or dates) and ``at`` the first period the intervention
    could affect. With ``group`` and ``treated`` (the group values that received it), difference-in-differences;
    otherwise an interrupted time series. ``column`` names the outcome's column if it isn't the factor's label.
    """
    import pandas as pd
    import statsmodels

    from latris.operations import datasets as data_ops
    from latris.operations import toc
    from latris.operations._data_engine import load_dataframe
    from latris.operations.estimation import _file_hash, _map_columns

    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    ent = resolve_entity(outcome, substrate.entities)
    level = toc.get_levels(root=paths.root).get(ent.id)
    if level is None:
        raise ImpactError(f"{ent.label} has no theory-of-change level; impact is estimated for a factor in the "
                          "results chain (`latris toc level`)")
    ds = data_ops.get_dataset(dataset, root=paths.root)
    file = paths.root / ds.location
    df = load_dataframe(file)
    colmap = _map_columns(df, [ent], {ent.id: column} if column else {})
    if ent.id not in colmap:
        raise ImpactError(f"the dataset has no column for {ent.label}; name it with --column <column>")
    needed = {"time": time} | ({"group": group} if group else {})
    for role, col in needed.items():
        if col not in df.columns:
            raise ImpactError(f"the dataset has no column {col!r} ({role})")
    if group and not treated:
        raise ImpactError("with a comparison group, say which group value(s) received the intervention (--treated)")
    if treated and not group:
        raise ImpactError("--treated needs --group, the column that says which group each row is in")

    ycol = colmap[ent.id]
    frame = pd.DataFrame({"y": df[ycol], "t_raw": df[time]} | ({"g": df[group]} if group else {}))
    n_rows = len(frame)
    frame = frame.dropna()
    warnings: list[str] = []
    if n_rows - len(frame):
        warnings.append(f"{n_rows - len(frame)} of {n_rows} rows dropped for missing values")
    if not pd.api.types.is_numeric_dtype(frame["y"]):
        raise ImpactError(f"{ent.label} ({ycol}) isn't numeric")
    frame["y"] = frame["y"].astype(float)
    frame["t"], is_date = _times(frame["t_raw"])
    frame.attrs["at"] = _at(at, is_date)
    if (w := _spacing_warning(frame["t"].to_numpy())) is not None:
        warnings.append(w)
    if level in ("input", "activity", "output"):
        warnings.append(f"{ent.label} is an {level.replace('_', ' ')} in the theory of change; impact estimation "
                        "usually concerns an outcome or the impact")

    method = "did" if group else "its"
    body = _did(frame, [str(v) for v in treated or []], warnings) if group else _its(frame, warnings)
    if method == "its":
        body["se_type"] = f"GLS with AR(1) errors (lag-1 correlation {body['ar1']:.2f})"
    return {
        "method": method,
        "outcome": ent.label, "outcome_id": ent.id, "level": level,
        "dataset": {"id": ds.id, "name": ds.name, "location": ds.location, "sha256": _file_hash(file)},
        "column": ycol, "time": time, "at": str(at), "time_is_date": is_date,
        "group": group, "treated": [str(v) for v in treated or []],
        "n": int(len(frame)),
        **body,
        "warnings": warnings,
        "assumptions": list(DID_ASSUMPTIONS if group else ITS_ASSUMPTIONS),
        "library_version": f"statsmodels {statsmodels.__version__}",
    }


def _g(x: float) -> str:
    return f"{x:.4g}"


def describe(p: dict[str, Any]) -> str:
    e = p["effect"]
    ci = f"95% CI {_g(e['ci_low'])} to {_g(e['ci_high'])}"
    if p["method"] == "its":
        rel = f", {p['relative']:+.0%} on the projected trend" if p.get("relative") is not None \
            and math.isfinite(p["relative"]) else ""
        return (f"Interrupted time series for {p['outcome']} ({p['dataset']['name']}, {p['periods_before']} periods "
                f"before and {p['periods_after']} after {p['at']}): by the last period {_g(e['estimate'])} against "
                f"the pre-period trend ({ci}{rel})")
    return (f"Difference-in-differences for {p['outcome']} ({p['dataset']['name']}, from {p['at']}, treated: "
            f"{', '.join(p['treated'])}): {_g(e['estimate'])} relative to the comparison group ({ci})")


def record(payload: dict[str, Any], *, root: Path | None = None) -> tuple[str, str]:
    from latris.operations.analysis_results import record_result

    its = payload["method"] == "its"
    sha, run = record_result(
        kind="toc-impact",
        key=f"toc-impact|{payload['outcome_id']}|{payload['dataset']['id']}|{payload['method']}",
        payload=payload,
        purpose="parameter-estimation",
        algorithm=("interrupted time series: segmented regression, GLS with AR(1) errors" if its
                   else "difference-in-differences: two-way regression with interaction"),
        library_version=payload["library_version"],
        summary=describe(payload),
        model_type=MODEL_TYPE,
        hyperparameters={"time": payload["time"], "at": payload["at"], "group": payload["group"],
                         "treated": payload["treated"], "column": payload["column"]},
        input_dataset_ids=[payload["dataset"]["id"]],
        metrics={"n": payload["n"], "estimate": payload["effect"]["estimate"], "p": payload["effect"]["p"]},
        affected_target_ids=[payload["outcome_id"]],
        commit_subject=f"Analysis: impact on {payload['outcome']} ({'ITS' if its else 'DiD'})",
        root=root,
    )
    return sha, run.id
