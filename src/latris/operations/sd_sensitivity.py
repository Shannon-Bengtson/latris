"""SD one-at-a-time sensitivity — which values move a result, and how well each is grounded.

For every constant and stock initial value, run the model at a low and a high
value (holding everything else at baseline) and measure one result metric of
one variable: its final value, peak, time of peak, minimum, time-average, or
value at a chosen time. The swing |high − low| ranks the parameters — the
tornado chart Vensim calls Sensitivity2All.

Ranges come from each value's uncertainty distribution (5th–95th percentile)
where one is recorded, otherwise ±10%. Like BN sensitivity, every row carries
the parameter's provenance and is flagged *weak* when it isn't human-verified
or is contested — so the report can say "the answer hinges on a value nobody
has checked".
"""

from __future__ import annotations

from typing import Any

from latris.operations._sampling import Sampler
from latris.operations._sd_eval import EquationError
from latris.operations.sd_inference import SDModel, simulate
from latris.operations.sd_montecarlo import _with_draw, baseline_value, resolve_variables
from latris.operations.sd_scenarios import _r, apply_overrides
from latris.schema.attributes import ParameterUncertainty
from latris.schema.sd import SDScenario

METRICS = ("final", "peak", "peak-time", "min", "mean")
DEFAULT_PCT = 10.0


def parse_metric(metric: str) -> tuple[str, float | None]:
    """``final`` | ``peak`` | ``peak-time`` | ``min`` | ``mean`` | ``at:T``."""
    m = (metric or "final").strip().lower()
    if m.startswith("at:"):
        try:
            return "at", float(m[3:])
        except ValueError as exc:
            raise ValueError(f"metric 'at:T' needs a number for T, got {metric!r}") from exc
    if m not in METRICS:
        raise ValueError(f"unknown metric {metric!r}; use one of {', '.join(METRICS)} or at:T")
    return m, None


def measure(times: list[float], values: list[float], metric: str, at: float | None = None) -> float:
    if not values:
        raise ValueError("no values to measure")
    if metric == "final":
        return values[-1]
    if metric == "peak":
        return max(values)
    if metric == "peak-time":
        return times[max(range(len(values)), key=values.__getitem__)]
    if metric == "min":
        return min(values)
    if metric == "mean":
        if len(times) < 2:
            return values[0]
        area = sum((times[i + 1] - times[i]) * (values[i] + values[i + 1]) / 2 for i in range(len(times) - 1))
        return area / (times[-1] - times[0])
    if metric == "at":
        assert at is not None
        if not times[0] <= at <= times[-1]:
            raise ValueError(f"at:{at:g} is outside the simulated time {times[0]:g}–{times[-1]:g}")
        for i in range(len(times) - 1):
            if times[i] <= at <= times[i + 1]:
                w = 0.0 if times[i + 1] == times[i] else (at - times[i]) / (times[i + 1] - times[i])
                return values[i] + w * (values[i + 1] - values[i])
        return values[-1]
    raise ValueError(metric)


def tornado(
    model: SDModel,
    variable: str,
    *,
    metric: str = "final",
    specs: dict[str, ParameterUncertainty] | None = None,
    provenance: dict[str, dict[str, Any]] | None = None,
    pct: float = DEFAULT_PCT,
    scenario: SDScenario | None = None,
) -> dict[str, Any]:
    """Rank every constant and initial value by how far it moves ``metric`` of ``variable``."""
    if not 0 < pct < 100:
        raise ValueError("the ± percentage must be between 0 and 100")
    kind, at = parse_metric(metric)
    base = apply_overrides(model, scenario.overrides) if scenario else model
    (vid,) = resolve_variables(base, [variable])
    specs = specs or {}
    provenance = provenance or {}

    reference = simulate(base)
    if not reference.success:
        raise ValueError(f"the baseline run failed: {reference.message}")
    baseline_metric = measure(reference.times, reference.series[vid], kind, at)

    params = sorted([*base.constants, *base.stocks], key=lambda k: base.labels.get(k, k))
    rows: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    runs = 1
    for k in params:
        value = baseline_value(base, k)
        spec = specs.get(k)
        if spec is not None:
            sampler = Sampler(spec)
            lo, hi = sampler.quantile(0.05), sampler.quantile(0.95)
            range_source = f"{spec.distribution} 5th–95th percentile"
        elif value == 0:
            skipped.append(
                {"target_id": k, "label": base.labels.get(k, k), "reason": "baseline value is 0; ±% is no change"}
            )
            continue
        else:
            lo, hi = sorted((value * (1 - pct / 100), value * (1 + pct / 100)))
            range_source = f"±{pct:g}%"
        outcome: dict[str, float] = {}
        error = None
        for side, v in (("low", lo), ("high", hi)):
            try:
                res = simulate(_with_draw(base, {k: v}))
                runs += 1
                if not res.success:
                    raise EquationError(res.message)
                outcome[side] = measure(res.times, res.series[vid], kind, at)
            except EquationError as exc:
                error = str(exc)
                break
        prov = provenance.get(k, {})
        verification = prov.get("verification", "unverified")
        contested = bool(prov.get("contested", False))
        row: dict[str, Any] = {
            "target_id": k,
            "label": base.labels.get(k, k),
            "attribute": "constant" if k in base.constants else "initial_value",
            "units": base.unit_text.get(k, ""),
            "baseline_value": _r(value),
            "low": _r(lo),
            "high": _r(hi),
            "range_source": range_source,
            "origin": prov.get("origin", "human-direct"),
            "verification": verification,
            "source_id": prov.get("source_id"),
            "contested": contested,
            "weak": verification != "human-verified" or contested,
            "range_origin": spec.origin if spec else None,
            "range_source_id": spec.source_id if spec else None,
        }
        if error is not None:
            row.update({"error": error, "swing": None})
        else:
            row.update(
                {
                    "result_low": _r(outcome["low"]),
                    "result_high": _r(outcome["high"]),
                    "swing": _r(abs(outcome["high"] - outcome["low"])),
                }
            )
        rows.append(row)

    rows.sort(key=lambda r: -(r["swing"] if r["swing"] is not None else -1.0))
    return {
        "variable": vid,
        "label": base.labels[vid],
        "units": reference.time_units if kind == "peak-time" else reference.units[vid],
        "time_units": reference.time_units,
        "metric": kind,
        "at": at,
        "metric_label": metric_label(kind, at, reference.time_units),
        "baseline": _r(baseline_metric),
        "pct": pct,
        "scenario": scenario.name if scenario else None,
        "parameters": rows,
        "skipped": skipped,
        "runs": runs,
        "method": reference.method,
        "algorithm": reference.algorithm,
        "settings": reference.settings,
    }


def metric_label(kind: str, at: float | None, time_units: str) -> str:
    if kind == "at":
        return f"value at {at:g} {time_units}"
    return {
        "final": "final value",
        "peak": "peak value",
        "peak-time": f"time of peak ({time_units})",
        "min": "minimum",
        "mean": "time-average",
    }[kind]
