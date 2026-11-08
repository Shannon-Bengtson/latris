"""SD scenarios — named what-ifs saved with the model, and runs that compare them.

A scenario is the baseline model with some constants or initial stock values
changed. Every override is unit-checked against the value it replaces (a
scenario may say ``6 month`` for a delay declared in years; it may not say
``6 person``). Scenarios live in ``views/parameters/sd-scenarios.yaml`` with
their own provenance, so a report can show what each one changed and why.

:func:`run` simulates the baseline plus each scenario on one compiled model
(the fast path is shared) and :func:`comparison` turns the runs into the
payload reports and agents read: the series, what each scenario changed, and
per variable the end value, peak and change against the baseline.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from latris.operations._units import Quantity, UnitError, describe, is_compatible, parse_unit
from latris.operations.commit import auto_commit
from latris.operations.sd_inference import SDModel, SDSimulationResult, simulate, with_values
from latris.repo.layout import ProjectPaths
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_model, load_model
from latris.schema.common import ProvenanceOrigin
from latris.schema.sd import SDOverride, SDScenario, SDScenarioSet

BASELINE = "baseline"
WHAT_IF = "what-if"
_MAX_POINTS = 200  # series kept per variable in a recorded comparison
_SIG = 6

_ASSIGN = re.compile(r"^\s*(?P<target>[^=]+?)\s*=\s*(?P<value>[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?)\s*(?P<units>.*)$")


def path(paths: ProjectPaths) -> Path:
    return paths.view_attribute_path("sd", "scenarios")


def load(paths: ProjectPaths) -> SDScenarioSet:
    p = path(paths)
    return load_model(SDScenarioSet, p) if p.exists() else SDScenarioSet()


def list_scenarios(*, root: Path | None = None) -> list[SDScenario]:
    return load(require_project(root)).scenarios


def get(name: str, paths: ProjectPaths) -> SDScenario:
    for s in load(paths).scenarios:
        if s.name.lower() == name.strip().lower():
            return s
    known = ", ".join(s.name for s in load(paths).scenarios) or "(none yet)"
    raise ValueError(f"no scenario named {name!r}; saved scenarios: {known}")


# ── overrides ────────────────────────────────────────────────────────


def parse_assignment(text: str, paths: ProjectPaths) -> SDOverride:
    """``"Tax Rate=0.2"`` or ``"Population = 1e6 person"`` → a checked override.

    Without units the value is taken in the target's declared units.
    """
    from latris.operations import sd as sd_ops

    m = _ASSIGN.match(text or "")
    if not m:
        raise ValueError(f"expected 'Variable=value [units]', got {text!r}")
    _, target_id, label = sd_ops._resolve(paths, m["target"])
    role = sd_ops._require_role(paths, target_id, label, ("constant", "stock"), "a scenario value")
    attribute = "constant" if role == "constant" else "initial_value"
    declared = _declared_units(paths, target_id, attribute, label)
    units = m["units"].strip() or declared
    check_units(units, declared, label)
    return SDOverride(target_id=target_id, attribute=attribute, value=float(m["value"]), units=units)


def _declared_units(paths: ProjectPaths, target_id: str, attribute: str, label: str) -> str:
    from latris.operations import sd as sd_ops

    store = sd_ops.get_constants(root=paths.root) if attribute == "constant" else sd_ops.get_stocks(root=paths.root)
    for e in store.entries:
        if e.target_id == target_id:
            return e.units
    what = "a value" if attribute == "constant" else "an initial value"
    raise ValueError(f"{label} has no {what} yet, so a scenario has nothing to change; set it first")


def check_units(units: str, declared: str, label: str) -> None:
    try:
        u, d = parse_unit(units), parse_unit(declared)
    except UnitError as exc:
        raise ValueError(f"{label}: {exc}") from exc
    if not is_compatible(u, d):
        raise ValueError(
            f"{label} is in {declared}; a scenario value in {describe(u)} can't replace it "
            f"(give it in {declared} or a compatible unit)"
        )


def apply_overrides(model: SDModel, overrides: list[SDOverride]) -> SDModel:
    """A copy of the compiled model with the overrides applied (converted to declared units)."""
    constants: dict[str, Any] = {}
    initial: dict[str, float] = {}
    for o in overrides:
        q = Quantity(o.value, parse_unit(o.units))
        label = model.labels.get(o.target_id, o.target_id)
        if o.attribute == "constant":
            if o.target_id not in model.constants:
                raise ValueError(f"{label} is not a constant of this model")
            target_units = model.constants[o.target_id].units
            if not q.is_compatible_with(target_units):
                raise ValueError(f"{label}: {o.units} is not compatible with {describe(target_units)}")
            constants[o.target_id] = q.to(target_units)
        else:
            if o.target_id not in model.stock_units:
                raise ValueError(f"{label} is not a stock of this model")
            target_units = model.stock_units[o.target_id]
            if not q.is_compatible_with(target_units):
                raise ValueError(f"{label}: {o.units} is not compatible with {describe(target_units)}")
            initial[o.target_id] = float(q.to(target_units).magnitude)
    return with_values(model, constants=constants, initial=initial)


# ── storage ──────────────────────────────────────────────────────────


def set_scenario(
    name: str,
    assignments: list[str],
    *,
    description: str = "",
    reason: str = "",
    origin: ProvenanceOrigin = "human-direct",
    source_id: str | None = None,
    root: Path | None = None,
) -> tuple[SDScenario, str]:
    """Create or replace a named scenario from ``Variable=value [units]`` assignments."""
    paths = require_project(root)
    if not assignments:
        raise ValueError("a scenario needs at least one change, e.g. --set 'Tax Rate=0.2'")
    overrides: dict[tuple[str, str], SDOverride] = {}
    for a in assignments:
        o = parse_assignment(a, paths)
        overrides[(o.target_id, o.attribute)] = o
    scenario = SDScenario(
        name=name, description=description, overrides=list(overrides.values()), reason=reason,
        origin=origin, source_id=source_id,
    )
    store = load(paths)
    store.scenarios = [s for s in store.scenarios if s.name.lower() != scenario.name.lower()] + [scenario]
    p = path(paths)
    p.parent.mkdir(parents=True, exist_ok=True)
    dump_model(store, p)
    changes = "; ".join(f"{o.target_id}={o.value:g} {o.units}" for o in scenario.overrides)
    sha = auto_commit(
        paths.root,
        subject=f"Set SD scenario {scenario.name}",
        body=f"changes: {changes}\norigin: {origin}\nsource_id: {source_id}\nreason: {reason}",
        paths=[p],
    )
    return scenario, sha


def remove_scenario(name: str, *, root: Path | None = None) -> str:
    paths = require_project(root)
    scenario = get(name, paths)
    store = load(paths)
    store.scenarios = [s for s in store.scenarios if s.name != scenario.name]
    p = path(paths)
    dump_model(store, p)
    return auto_commit(paths.root, subject=f"Remove SD scenario {scenario.name}", paths=[p])


# ── comparison runs ──────────────────────────────────────────────────


@dataclass(frozen=True)
class ScenarioRun:
    name: str
    scenario: SDScenario | None  # None for the baseline
    result: SDSimulationResult


def what_if(assignments: list[str], paths: ProjectPaths) -> SDScenario:
    """An unsaved scenario from ad-hoc ``--set`` assignments."""
    overrides = [parse_assignment(a, paths) for a in assignments]
    return SDScenario(name=WHAT_IF, description="Ad-hoc values (not saved as a scenario)", overrides=overrides)


def run(model: SDModel, scenarios: list[SDScenario]) -> list[ScenarioRun]:
    """Simulate the baseline and each scenario on one compiled model."""
    out = [ScenarioRun(BASELINE, None, simulate(model))]
    for s in scenarios:
        out.append(ScenarioRun(s.name, s, simulate(apply_overrides(model, s.overrides))))
    return out


def key(runs: list[ScenarioRun]) -> str:
    """Analysis key: the saved scenarios compared (a what-if is keyed by its values)."""
    names = []
    for r in runs[1:]:
        if r.name == WHAT_IF and r.scenario is not None:
            digest = hashlib.sha1(r.scenario.model_dump_json().encode()).hexdigest()[:8]
            names.append(f"{WHAT_IF}-{digest}")
        else:
            names.append(r.name)
    return "sd-simulation|" + ",".join(sorted(names))


def _r(x: float) -> float:
    if not math.isfinite(x) or x == 0:
        return x
    return round(x, _SIG - 1 - int(math.floor(math.log10(abs(x)))))


def _thin(n: int) -> list[int]:
    if n <= _MAX_POINTS:
        return list(range(n))
    step = (n - 1) / (_MAX_POINTS - 1)
    idx = sorted({round(i * step) for i in range(_MAX_POINTS)})
    return idx if idx[-1] == n - 1 else [*idx, n - 1]


def describe_series(times: list[float], values: list[float]) -> dict[str, float]:
    if not values:
        return {}
    peak = max(range(len(values)), key=values.__getitem__)
    low = min(range(len(values)), key=values.__getitem__)
    return {
        "start": _r(values[0]), "end": _r(values[-1]),
        "peak": _r(values[peak]), "peak_time": _r(times[peak]),
        "min": _r(values[low]), "min_time": _r(times[low]),
    }


def comparison(runs: list[ScenarioRun], model: SDModel | None = None) -> dict[str, Any]:
    """The recorded payload: series (thinned to ≤200 points), changes, and per-variable summaries."""
    base = runs[0].result
    idx = _thin(len(base.times))
    times = [_r(base.times[i]) for i in idx]
    variables = list(base.series)

    def override_view(o: SDOverride) -> dict[str, Any]:
        if model is None:
            raise ValueError("a comparison with scenarios needs the compiled model")
        if o.attribute == "constant":
            q = model.constants[o.target_id]
            was = f"{q.magnitude:g} {model.unit_text.get(o.target_id) or describe(q.units)}"
        else:
            was = f"{model.initial[o.target_id]:g} {model.unit_text[o.target_id]}"
        return {
            "target_id": o.target_id, "label": model.labels.get(o.target_id, o.target_id),
            "attribute": o.attribute, "value": o.value, "units": o.units, "baseline": was,
        }

    scenarios = []
    for r in runs:
        res = r.result
        entry: dict[str, Any] = {
            "name": r.name, "success": res.success, "message": res.message, "warnings": res.warnings,
            "series": {v: [_r(res.series[v][i]) for i in idx if i < len(res.series[v])] for v in variables},
            "summary": {v: describe_series(res.times, res.series[v]) for v in variables},
        }
        if r.scenario is not None:
            s = r.scenario
            entry.update({
                "description": s.description, "reason": s.reason, "origin": s.origin,
                "verification": s.verification, "source_id": s.source_id,
                "overrides": [override_view(o) for o in s.overrides],
            })
            base_end = {v: base.series[v][-1] for v in variables if base.series[v]}
            entry["change_vs_baseline"] = {
                v: {
                    "end": _r(res.series[v][-1] - base_end[v]),
                    "end_pct": _r(100 * (res.series[v][-1] - base_end[v]) / abs(base_end[v])) if base_end[v] else None,
                }
                for v in variables if res.series[v] and v in base_end
            }
        scenarios.append(entry)

    return {
        "times": times, "time_units": base.time_units, "labels": base.labels, "units": base.units,
        "roles": base.roles, "method": base.method, "algorithm": base.algorithm,
        "library_version": base.library_version, "settings": base.settings, "scenarios": scenarios,
    }
