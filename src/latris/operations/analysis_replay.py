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
from latris.schema.build_spec import SpecAnalysis

_SETTING_KEYS = ("initial_time", "final_time", "dt", "saveper", "method", "time_units")


def _settings(raw: dict[str, Any]) -> dict[str, Any]:
    out = {k: raw[k] for k in _SETTING_KEYS if raw.get(k) is not None}
    if "method" not in out and raw.get("integration_method"):
        out["method"] = raw["integration_method"]
    return out


def run_analysis(a: SpecAnalysis, *, root: Path | None = None) -> str:
    """Run and record one analysis; returns the run id."""
    from latris.operations import formalisms

    paths = require_project(root)
    rk = formalisms.for_analysis(a.kind)
    if rk:
        return rk.run(a, paths.root)
    raise ValueError(f"unknown analysis kind {a.kind!r}")


def definitions(*, root: Path | None = None) -> list[SpecAnalysis]:
    """The analyses behind the results reports currently show (stale ones left out), oldest first."""
    from latris.operations import formalisms
    from latris.operations.analysis_results import report_results

    paths = require_project(root)
    out: list[SpecAnalysis] = []
    results = sorted((r for r in report_results(root=paths.root) if not r.stale), key=lambda r: r.run.id)
    for r in results:
        p, kind = r.payload, r.run.result_kind
        found = formalisms.result_kind(kind)
        if found:
            rk = found[1]
            out.append(rk.run_definition(p, r.run) if rk.run_definition else rk.definition(p))
    return out
