"""SD Monte Carlo — propagate parameter uncertainty into bands over time.

Pure computation over a compiled model (no file I/O): sample every uncertain
constant and initial value from its distribution (Latin hypercube by default,
seeded), simulate each draw on the shared fast path, and summarise each
chosen variable as percentile bands at every reported time — the 50/75/95/100%
envelopes Vensim and Stella draw — plus the baseline run for reference.

It also reports which uncertainty drives each outcome: the Spearman rank
correlation between each sampled parameter and the variable's end value.
That, together with each range's provenance, is what lets a report say
"the spread comes mostly from the dispersal rate, whose range is AI-proposed".
"""

from __future__ import annotations

import math
import time
from typing import Any

from latris.operations._sampling import PERCENTILES, percentile, sample, spearman
from latris.operations._sd_eval import EquationError
from latris.operations._units import Quantity
from latris.operations.sd_inference import SDModel, simulate, with_values
from latris.operations.sd_scenarios import _r, _thin, apply_overrides
from latris.schema.attributes import ParameterUncertainty
from latris.schema.sd import SDScenario

MAX_RUNS = 1000
DEFAULT_RUNS = 200
DEFAULT_SEED = 1234
_DEFAULT_VARIABLES = 6


def resolve_variables(model: SDModel, names: list[str] | None) -> list[str]:
    """Variable ids from labels/ids; default: the stocks (at most six)."""
    reportable = [v for v in (*model.stocks, *model.order) if v not in model.hidden]
    if not names:
        return sorted((s for s in model.stocks if s not in model.hidden), key=lambda s: model.labels[s])[
            :_DEFAULT_VARIABLES
        ]
    by_label = {model.labels[v].lower(): v for v in reportable}
    out = []
    for n in names:
        v = n if n in reportable else by_label.get(n.strip().lower())
        if v is None:
            known = ", ".join(sorted(model.labels[x] for x in reportable))
            raise ValueError(f"{n!r} is not a stock, flow or auxiliary of this model; choose from: {known}")
        out.append(v)
    return list(dict.fromkeys(out))


def _with_draw(model: SDModel, draw: dict[str, float]) -> SDModel:
    constants = {k: Quantity(v, model.constants[k].units) for k, v in draw.items() if k in model.constants}
    initial = {k: v for k, v in draw.items() if k in model.stock_units}
    return with_values(model, constants=constants, initial=initial)


def baseline_value(model: SDModel, target_id: str) -> float:
    if target_id in model.constants:
        return float(model.constants[target_id].magnitude)
    return float(model.initial[target_id])


def monte_carlo(
    model: SDModel,
    specs: dict[str, ParameterUncertainty],
    *,
    runs: int = DEFAULT_RUNS,
    seed: int = DEFAULT_SEED,
    sampling: str = "lhs",
    variables: list[str] | None = None,
    scenario: SDScenario | None = None,
    max_seconds: float = 60.0,
) -> dict[str, Any]:
    """Run ``runs`` sampled simulations and summarise the chosen variables as percentile bands."""
    if not 2 <= runs <= MAX_RUNS:
        raise ValueError(f"runs must be between 2 and {MAX_RUNS}")
    base = apply_overrides(model, scenario.overrides) if scenario else model
    fixed = {o.target_id for o in scenario.overrides} if scenario else set()
    uncertain = {k: v for k, v in specs.items() if (k in base.constants or k in base.stock_units) and k not in fixed}
    skipped = [
        {"target_id": k, "label": model.labels.get(k, k), "reason": "fixed by the scenario"}
        for k in sorted(specs)
        if k in fixed
    ]
    if not uncertain:
        raise ValueError(
            "no uncertain values to sample — give constants or initial values a range first, "
            "e.g. `latris sd set-uncertainty 'Emission Rate' triangular --min 80 --mode 120 --max 150`"
        )
    var_ids = resolve_variables(base, variables)

    reference = simulate(base)
    if not reference.success:
        raise ValueError(f"the baseline run failed before sampling: {reference.message}")
    n_times = len(reference.times)
    draws = sample(uncertain, runs, seed=seed, method=sampling)

    collected: dict[str, list[list[float]]] = {v: [] for v in var_ids}
    kept_draws: list[dict[str, float]] = []
    failures: list[str] = []
    started = time.perf_counter()
    for i, draw in enumerate(draws):
        if i == 1:
            estimate = (time.perf_counter() - started) * runs
            if estimate > max_seconds:
                raise ValueError(
                    f"{runs} runs would take about {estimate:.0f} s (limit {max_seconds:g} s). Use fewer runs, "
                    f"a larger --dt, or --method euler"
                )
        try:
            res = simulate(_with_draw(base, draw))
        except EquationError as exc:
            failures.append(str(exc))
            continue
        if not res.success or len(res.times) != n_times:
            failures.append(res.message)
            continue
        for v in var_ids:
            collected[v].append(res.series[v])
        kept_draws.append(draw)
    if len(kept_draws) < max(2, runs // 2):
        detail = f" First error: {failures[0]}" if failures else ""
        raise ValueError(
            f"only {len(kept_draws)} of {runs} runs succeeded; the sampled ranges break the model.{detail}"
        )

    idx = _thin(n_times)
    bands: dict[str, Any] = {}
    end: dict[str, Any] = {}
    influence: dict[str, list[dict[str, Any]]] = {}
    for v in var_ids:
        matrix = collected[v]
        per_time = [sorted(row[t] for row in matrix) for t in idx]
        bands[v] = {
            "percentiles": list(PERCENTILES),
            "series": {f"{p:g}": [_r(percentile(col, p)) for col in per_time] for p in PERCENTILES},
            "mean": [_r(sum(col) / len(col)) for col in per_time],
            "baseline": [_r(reference.series[v][t]) for t in idx],
        }
        finals = [row[-1] for row in matrix]
        fs = sorted(finals)
        end[v] = {
            **{f"p{p:g}": _r(percentile(fs, p)) for p in PERCENTILES},
            "mean": _r(sum(fs) / len(fs)),
            "baseline": _r(reference.series[v][-1]),
        }
        rows = []
        for k in sorted(uncertain):
            rho = spearman([d[k] for d in kept_draws], finals)
            rows.append({"target_id": k, "label": model.labels.get(k, k), "rho": None if rho is None else _r(rho)})
        rows.sort(key=lambda r: -abs(r["rho"] or 0.0))
        influence[v] = rows

    parameters = []
    for k in sorted(uncertain, key=lambda x: model.labels.get(x, x)):
        spec = uncertain[k]
        values = [d[k] for d in kept_draws]
        parameters.append(
            {
                "target_id": k,
                "label": model.labels.get(k, k),
                "attribute": "constant" if k in base.constants else "initial_value",
                "units": model.unit_text.get(k, ""),
                "baseline_value": _r(baseline_value(base, k)),
                "distribution": spec.distribution,
                "params": spec.params,
                "reason": spec.reason,
                "origin": spec.origin,
                "verification": spec.verification,
                "source_id": spec.source_id,
                "sampled": {"min": _r(min(values)), "mean": _r(sum(values) / len(values)), "max": _r(max(values))},
            }
        )

    return {
        "times": [_r(reference.times[t]) for t in idx],
        "time_units": reference.time_units,
        "labels": {**{v: model.labels[v] for v in var_ids}, **{k: model.labels.get(k, k) for k in uncertain}},
        "units": {v: reference.units[v] for v in var_ids},
        "roles": {v: model.roles[v] for v in var_ids},
        "variables": var_ids,
        "runs": runs,
        "succeeded": len(kept_draws),
        "failed": len(failures),
        "failure_examples": failures[:3],
        "seed": seed,
        "sampling": sampling,
        "method": reference.method,
        "algorithm": reference.algorithm,
        "library_version": reference.library_version,
        "settings": reference.settings,
        "scenario": scenario.name if scenario else None,
        "parameters": parameters,
        "skipped_parameters": skipped,
        "bands": bands,
        "end": end,
        "influence": influence,
        "seconds": round(time.perf_counter() - started, 3),
    }


def describe_end(payload: dict[str, Any], v: str) -> str:
    """'PM2.5 Load at t=10: median 118, 95% of runs 96.2–131 tonne'."""
    e = payload["end"][v]
    t = payload["times"][-1] if payload["times"] else math.nan
    return (
        f"{payload['labels'][v]} at {t:g} {payload['time_units']}: median {e['p50']:.4g}, "
        f"95% of runs {e['p2.5']:.4g}–{e['p97.5']:.4g} {payload['units'][v]}"
    )


# ── comparing options under uncertainty ──────────────────────────────


def compare_options(
    model: SDModel,
    specs: dict[str, ParameterUncertainty],
    options: list[SDScenario],
    *,
    variable: str,
    metric: str = "final",
    runs: int = DEFAULT_RUNS,
    seed: int = DEFAULT_SEED,
    sampling: str = "lhs",
    max_seconds: float = 60.0,
) -> dict[str, Any]:
    """Run the baseline and every option on the SAME sampled draws and compare one result metric.

    Common random numbers: draw *i* of every option uses the same sampled values (a value an option
    fixes is the option's), so the difference between an option and the baseline is measured draw by
    draw — the spread of that paired difference is far narrower, and more honest, than comparing two
    independent bands. Reports each option's metric (median, 95% of draws, the central-value run) and
    its paired difference from the baseline, with the share of draws where it is lower or higher.
    """
    from latris.operations.sd_sensitivity import measure, metric_label, metric_units, parse_metric

    if not 2 <= runs <= MAX_RUNS:
        raise ValueError(f"runs must be between 2 and {MAX_RUNS}")
    if not options:
        raise ValueError("name at least one saved scenario to compare with the baseline")
    kind, at = parse_metric(metric)
    (vid,) = resolve_variables(model, [variable])
    uncertain = {k: v for k, v in specs.items() if k in model.constants or k in model.stock_units}
    if not uncertain:
        raise ValueError(
            "no uncertain values to sample — give constants or initial values a range first (set_uncertainty)"
        )
    arms = [("baseline", model, set())] + [
        (sc.name, apply_overrides(model, sc.overrides), {o.target_id for o in sc.overrides}) for sc in options
    ]
    reference = simulate(model)
    if not reference.success:
        raise ValueError(f"the baseline run failed before sampling: {reference.message}")

    def value(m: SDModel) -> float:
        res = simulate(m)
        if not res.success:
            raise EquationError(res.message)
        return measure(res.times, res.series[vid], kind, at)

    central = {name: value(m) for name, m, _ in arms}
    draws = sample(uncertain, runs, seed=seed, method=sampling)
    per_arm: dict[str, list[float]] = {name: [] for name, _, _ in arms}
    failures: list[str] = []
    started = time.perf_counter()
    for i, draw in enumerate(draws):
        if i == 1:
            estimate = (time.perf_counter() - started) * runs
            if estimate > max_seconds:
                raise ValueError(
                    f"{runs} draws × {len(arms)} options would take about {estimate:.0f} s (limit {max_seconds:g} s). "
                    f"Use fewer runs, a larger dt, or method euler"
                )
        try:
            values = {name: value(_with_draw(m, {k: v for k, v in draw.items() if k not in fixed}))
                      for name, m, fixed in arms}
        except (EquationError, ValueError) as exc:
            failures.append(str(exc))
            continue
        for name, v in values.items():
            per_arm[name].append(v)
    kept = len(per_arm["baseline"])
    if kept < max(2, runs // 2):
        detail = f" First error: {failures[0]}" if failures else ""
        raise ValueError(f"only {kept} of {runs} draws succeeded; the sampled ranges break the model.{detail}")

    def spread(xs: list[float]) -> dict[str, float]:
        ys = sorted(xs)
        return {"p2.5": _r(percentile(ys, 2.5)), "p50": _r(percentile(ys, 50)), "p97.5": _r(percentile(ys, 97.5)),
                "mean": _r(sum(ys) / len(ys))}

    base = per_arm["baseline"]
    rows = []
    for name, _, _ in arms:
        xs = per_arm[name]
        row: dict[str, Any] = {"name": name, "central": _r(central[name]), **spread(xs)}
        if name != "baseline":
            diffs = [x - b for x, b in zip(xs, base, strict=True)]
            row["difference"] = {
                **spread(diffs),
                "share_lower": _r(sum(d < 0 for d in diffs) / len(diffs)),
                "share_higher": _r(sum(d > 0 for d in diffs) / len(diffs)),
            }
        rows.append(row)
    units = metric_units(kind, reference.units[vid], reference.time_units)
    return {
        "variable": vid,
        "label": model.labels[vid],
        "metric": kind,
        "at": at,
        "metric_label": metric_label(kind, at, reference.time_units),
        "units": units,
        "time_units": reference.time_units,
        "options": rows,
        "scenarios": [sc.name for sc in options],
        "uncertain": sorted(model.labels.get(k, k) for k in uncertain),
        "runs": runs,
        "succeeded": kept,
        "failed": len(failures),
        "failure_examples": failures[:3],
        "seed": seed,
        "sampling": sampling,
        "method": reference.method,
        "algorithm": reference.algorithm,
        "library_version": reference.library_version,
        "settings": reference.settings,
        "seconds": round(time.perf_counter() - started, 3),
    }


def describe_option(p: dict[str, Any], row: dict[str, Any]) -> str:
    """'Both options: 4.1 week (95% of draws 2.9–5.6); 2.3 lower than the baseline in the median draw
    (95% of draws: -3.8 to -1.1), lower in 99% of draws'."""
    u = p["units"]
    head = f"{row['name']}: {row['p50']:.4g} {u} (95% of draws {row['p2.5']:.4g}–{row['p97.5']:.4g})"
    d = row.get("difference")
    if not d:
        return head
    word = "lower" if d["p50"] < 0 else "higher"
    return (f"{head}; {abs(d['p50']):.4g} {word} than the baseline in the median draw "
            f"(95% of draws: {d['p2.5']:+.4g} to {d['p97.5']:+.4g}), lower in {d['share_lower']:.0%} of draws")
