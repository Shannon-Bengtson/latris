"""Analyses as definitions — run one from a spec, or describe a recorded one as a spec.

A share link carries the model, not its results: the numbers are re-computed
when the link is opened. That keeps links small and results honest (they're
always computed from the parameters the link carries). This module is both
directions of that:

- :func:`run_analysis` runs a :class:`~latris.schema.build_spec.SpecAnalysis`
  and records it, so the report shows it;
- :func:`definitions` turns the results a report currently shows back into
  those definitions (same seed, same scenario, same settings), so replaying
  them reproduces the report.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from latris.repo.project import require_project
from latris.schema.build_spec import SpecAnalysis, make_analysis

_SETTING_KEYS = ("initial_time", "final_time", "dt", "saveper", "method", "time_units")


def _settings(raw: dict[str, Any]) -> dict[str, Any]:
    out = {k: raw[k] for k in _SETTING_KEYS if raw.get(k) is not None}
    if "method" not in out and raw.get("integration_method"):
        out["method"] = raw["integration_method"]
    return out


def run_analysis(a: SpecAnalysis, *, root: Path | None = None) -> str:
    """Run and record one analysis; returns the run id."""
    from latris.operations import sd as sd_ops

    paths = require_project(root)
    s = _settings(a.settings) if a.kind in ("simulate", "monte_carlo", "compare", "sensitivity", "loops") else {}
    if a.kind == "simulate":
        payload, runs = sd_ops.simulate_scenarios(a.scenarios, a.set, **s, apply_to_all=a.apply_to_all or None,
                                                  root=paths.root)
        return sd_ops.record_comparison(payload, runs, root=paths.root)[1]
    if a.kind == "monte_carlo":
        payload = sd_ops.run_monte_carlo(
            runs=a.runs or 200, seed=a.seed if a.seed is not None else 1234, sampling=a.sampling or "lhs",
            variables=a.variables or None, scenario=a.scenario, settings=s, apply_to_all=a.apply_to_all or None,
            root=paths.root,
        )
        return sd_ops.record_monte_carlo(payload, root=paths.root)[1]
    if a.kind == "compare":
        if not a.variable:
            raise ValueError("comparing options needs a variable")
        payload = sd_ops.run_compare(
            a.scenarios, a.variable, metric=a.metric or "final", runs=a.runs or 200,
            seed=a.seed if a.seed is not None else 1234, sampling=a.sampling or "lhs", settings=s,
            apply_to_all=a.apply_to_all or None, reference=a.reference, root=paths.root,
        )
        return sd_ops.record_compare(payload, root=paths.root)[1]
    if a.kind == "sensitivity":
        if not a.variable:
            raise ValueError("a sensitivity analysis needs a variable")
        payload = sd_ops.run_sensitivity(
            a.variable, metric=a.metric or "final", pct=a.pct or 10.0, scenario=a.scenario, settings=s,
            apply_to_all=a.apply_to_all or None, root=paths.root,
        )
        return sd_ops.record_sensitivity(payload, root=paths.root)[1]
    if a.kind == "loops":
        payload = sd_ops.run_loops(scenario=a.scenario, start=a.start, end=a.end, settings=s, root=paths.root)
        return sd_ops.record_loops(payload, root=paths.root)[1]
    from latris.operations import formalisms

    rk = formalisms.for_analysis(a.kind)
    if rk:
        return rk.run(a, paths.root)
    raise ValueError(f"unknown analysis kind {a.kind!r}")


def _what_if(payload: dict[str, Any]) -> list[str]:
    for sc in payload.get("scenarios", [])[1:]:
        if sc["name"] == "what-if":
            return [f"{o['label']}={o['value']!r} {o['units']}" for o in sc.get("overrides", [])]
    return []


def definitions(*, root: Path | None = None) -> list[SpecAnalysis]:
    """The analyses behind the results reports currently show (stale ones left out), oldest first."""
    from latris.operations.analysis_results import report_results

    paths = require_project(root)
    out: list[SpecAnalysis] = []
    results = sorted((r for r in report_results(root=paths.root) if not r.stale), key=lambda r: r.run.id)
    for r in results:
        h, p, kind = r.run.hyperparameters, r.payload, r.run.result_kind
        s = _settings(h)
        labels = p.get("labels", {})
        if kind == "sd-simulation":
            saved = [n for n in h.get("scenarios", []) if n != "what-if"]
            out.append(make_analysis(kind="simulate", settings=s, scenarios=saved, set=_what_if(p),
                                    apply_to_all=p.get("world") or []))
        elif kind == "sd-monte-carlo":
            out.append(make_analysis(
                kind="monte_carlo", settings=s, runs=p["runs"], seed=p["seed"], sampling=p["sampling"],
                variables=[labels.get(v, v) for v in p["variables"]], scenario=p.get("scenario"),
                apply_to_all=p.get("world") or [],
            ))
        elif kind == "sd-options":
            metric = p["metric"] if p.get("at") is None else f"at:{p['at']:g}"
            out.append(make_analysis(
                kind="compare", settings=s, scenarios=p["scenarios"], variable=p["label"], metric=metric,
                runs=p["runs"], seed=p["seed"], sampling=p["sampling"], apply_to_all=p.get("world") or [],
                reference=p.get("reference"),
            ))
        elif kind == "sd-sensitivity":
            metric = p["metric"] if p.get("at") is None else f"at:{p['at']:g}"
            out.append(make_analysis(
                kind="sensitivity", settings=s, variable=p["label"], metric=metric, pct=p["pct"],
                scenario=p.get("scenario"), apply_to_all=p.get("world") or [],
            ))
        elif kind == "sd-loops":
            lo, hi = p["window"]
            full = p["times"] and lo == p["times"][0] and hi == p["times"][-1]
            out.append(make_analysis(
                kind="loops", settings=s, scenario=p.get("scenario"),
                start=None if full else lo, end=None if full else hi,
            ))
        else:
            from latris.operations import formalisms

            found = formalisms.result_kind(kind)
            if found:
                out.append(found[1].definition(p))
    return out
