"""System Dynamics operations — roles, equations, values, tables, check, simulate.

Each mutation upserts one parameter Set, dumps it, and auto-commits, returning
``(model, commit_sha)`` per the operations convention. Classification is a view
role (``views/roles/sd-roles.yaml``) written through ``operations/view_roles``.

Storage:
- ``views/parameters/sd-equations.yaml``     — :class:`SDEquationSet`
- ``views/parameters/sd-initial_value.yaml`` — :class:`SDStockSet`
- ``views/parameters/sd-constant.yaml``      — :class:`SDConstantSet`
- ``views/parameters/sd-table.yaml``         — :class:`SDTableSet`

Simulation settings are per-run (built from overrides), not persisted — the
same as BN and FCM settings today.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from latris.operations import sd_inference
from latris.operations._resolve import resolve_entity
from latris.operations._sd_eval import parse, slugify
from latris.operations._units import parse_unit
from latris.operations.commit import auto_commit
from latris.operations.sd_inference import SDSimulationResult
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_model, load_model
from latris.schema import Substrate
from latris.schema.common import ProvenanceOrigin
from latris.schema.roles import RoleSet
from latris.schema.sd import (
    SDConstantEntry,
    SDConstantSet,
    SDEquationEntry,
    SDEquationSet,
    SDStockEntry,
    SDStockSet,
    SDTableEntry,
    SDTableSet,
    TablePoint,
)
from latris.schema.settings import SDSettings

_MODEL_TYPE = "sd"


# ── storage helpers ──────────────────────────────────────────────────


def _path(paths, attribute: str) -> Path:
    return paths.view_attribute_path(_MODEL_TYPE, attribute)


def _load(paths, cls, attribute: str):
    p = _path(paths, attribute)
    return load_model(cls, p) if p.exists() else cls()


def _dump(path: Path, store) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    dump_model(store, path)


def _load_roles(paths) -> RoleSet:
    p = paths.role_path(_MODEL_TYPE)
    return load_model(RoleSet, p) if p.exists() else RoleSet()


def _resolve(paths, target: str) -> tuple[Substrate, str, str]:
    substrate = load_model(Substrate, paths.conceptual_yaml)
    entity = resolve_entity(target, substrate.entities)
    return substrate, entity.id, entity.label


def _require_role(paths, entity_id: str, label: str, allowed: tuple[str, ...], action: str) -> str:
    role = sd_inference.role_map(_load_roles(paths)).get(entity_id)
    if role not in allowed:
        need = " or ".join(allowed)
        have = f"is classified as {role}" if role else "has no SD role yet"
        raise ValueError(
            f"{label!r} {have}; {action} needs a {need}. Classify it first: `sd set-role {label!r} {allowed[0]}`"
        )
    return role


def _upsert(store, entry) -> None:
    store.entries = [e for e in store.entries if e.target_id != entry.target_id]
    store.entries.append(entry)


# ── classification ───────────────────────────────────────────────────


def set_role(target: str, role: str, *, root: Path | None = None) -> tuple[str, str]:
    """Classify an entity as stock, flow, auxiliary, constant, or source_sink."""
    from latris.operations import view_roles

    paths = require_project(root)
    _, entity_id, _ = _resolve(paths, target)
    return view_roles.set_role(entity_id, _MODEL_TYPE, role, root=paths.root)


def get_roles(*, root: Path | None = None) -> RoleSet:
    return _load_roles(require_project(root))


# ── parameters ───────────────────────────────────────────────────────


def set_equation(
    target: str,
    expression: str,
    units: str,
    *,
    origin: ProvenanceOrigin = "human-direct",
    source_id: str | None = None,
    root: Path | None = None,
) -> tuple[SDEquationEntry, str]:
    """Set (or replace) a flow's or auxiliary's equation.

    Variables are referenced by slugified label (``Birth Rate`` → ``birth_rate``)
    and must already be classified. Syntax, names and units are checked now;
    dimensional consistency across the model is checked by ``sd check``.
    """
    paths = require_project(root)
    substrate, vid, label = _resolve(paths, target)
    _require_role(paths, vid, label, ("flow", "auxiliary"), "an equation")
    parsed = parse(expression)
    parse_unit(units)

    roles = sd_inference.role_map(_load_roles(paths))
    labels = {e.id: e.label for e in substrate.entities}
    known = {slugify(labels[i]): i for i, r in roles.items() if r in ("stock", "flow", "auxiliary", "constant")
             and i in labels}
    unknown = sorted(n for n in parsed.names if n not in known)
    if unknown:
        raise ValueError(
            f"equation refers to {', '.join(repr(n) for n in unknown)}, which "
            f"{'is' if len(unknown) == 1 else 'are'} not a classified SD variable. "
            f"Known: {', '.join(sorted(known)) or '(none — classify variables with `sd set-role` first)'}"
        )
    if slugify(label) in parsed.names:
        raise ValueError(f"the equation for {label!r} refers to itself; only stocks accumulate their own history")

    entry = SDEquationEntry(
        target_id=vid, expression=parsed.expression, units=units.strip(), origin=origin, source_id=source_id
    )
    store = _load(paths, SDEquationSet, "equations")
    _upsert(store, entry)
    path = _path(paths, "equations")
    _dump(path, store)
    sha = auto_commit(
        paths.root,
        subject=f"Set SD equation on {label}: {parsed.expression} [{entry.units}]",
        body=f"target: {vid}\nexpression: {parsed.expression}\nunits: {entry.units}\norigin: {origin}\n"
             f"source_id: {source_id}",
        paths=[path],
    )
    return entry, sha


def set_initial_value(
    stock: str,
    value: float,
    units: str,
    *,
    non_negative: bool = False,
    origin: ProvenanceOrigin = "human-direct",
    source_id: str | None = None,
    root: Path | None = None,
) -> tuple[SDStockEntry, str]:
    """Set (or replace) a stock's value at the initial time."""
    paths = require_project(root)
    _, sid, label = _resolve(paths, stock)
    _require_role(paths, sid, label, ("stock",), "an initial value")
    parse_unit(units)

    entry = SDStockEntry(
        target_id=sid, initial_value=value, units=units.strip(), non_negative=non_negative,
        origin=origin, source_id=source_id,
    )
    store = _load(paths, SDStockSet, "initial_value")
    _upsert(store, entry)
    path = _path(paths, "initial_value")
    _dump(path, store)
    sha = auto_commit(
        paths.root,
        subject=f"Set SD initial value on {label}: {value} {entry.units}",
        body=f"target: {sid}\ninitial_value: {value}\nunits: {entry.units}\nnon_negative: {non_negative}\n"
             f"origin: {origin}\nsource_id: {source_id}",
        paths=[path],
    )
    return entry, sha


def set_constant(
    target: str,
    value: float,
    units: str,
    *,
    origin: ProvenanceOrigin = "human-direct",
    source_id: str | None = None,
    root: Path | None = None,
) -> tuple[SDConstantEntry, str]:
    """Set (or replace) a constant's value."""
    paths = require_project(root)
    _, cid, label = _resolve(paths, target)
    _require_role(paths, cid, label, ("constant",), "a constant value")
    parse_unit(units)

    entry = SDConstantEntry(target_id=cid, value=value, units=units.strip(), origin=origin, source_id=source_id)
    store = _load(paths, SDConstantSet, "constant")
    _upsert(store, entry)
    path = _path(paths, "constant")
    _dump(path, store)
    sha = auto_commit(
        paths.root,
        subject=f"Set SD constant {label} = {value} {entry.units}",
        body=f"target: {cid}\nvalue: {value}\nunits: {entry.units}\norigin: {origin}\nsource_id: {source_id}",
        paths=[path],
    )
    return entry, sha


def set_table(
    target: str,
    points: list[tuple[float, float]],
    x_units: str,
    y_units: str,
    *,
    extrapolate: str = "clamp",
    origin: ProvenanceOrigin = "human-elicited",
    source_id: str | None = None,
    root: Path | None = None,
) -> tuple[SDTableEntry, str]:
    """Set (or replace) the lookup table a flow/auxiliary calls as ``TABLE(x)``."""
    paths = require_project(root)
    _, vid, label = _resolve(paths, target)
    _require_role(paths, vid, label, ("flow", "auxiliary"), "a table function")
    parse_unit(x_units)
    parse_unit(y_units)

    entry = SDTableEntry(
        target_id=vid,
        points=[TablePoint(x=x, y=y) for x, y in points],
        x_units=x_units.strip(),
        y_units=y_units.strip(),
        extrapolate=extrapolate,  # type: ignore[arg-type]
        origin=origin,
        source_id=source_id,
    )
    store = _load(paths, SDTableSet, "table")
    _upsert(store, entry)
    path = _path(paths, "table")
    _dump(path, store)
    sha = auto_commit(
        paths.root,
        subject=f"Set SD table on {label} ({len(points)} point(s))",
        body=f"target: {vid}\npoints: {points}\nx_units: {entry.x_units}\ny_units: {entry.y_units}\n"
             f"extrapolate: {extrapolate}\norigin: {origin}\nsource_id: {source_id}",
        paths=[path],
    )
    return entry, sha


# ── reads ────────────────────────────────────────────────────────────


def get_equations(*, root: Path | None = None) -> SDEquationSet:
    return _load(require_project(root), SDEquationSet, "equations")


def get_stocks(*, root: Path | None = None) -> SDStockSet:
    return _load(require_project(root), SDStockSet, "initial_value")


def get_constants(*, root: Path | None = None) -> SDConstantSet:
    return _load(require_project(root), SDConstantSet, "constant")


def get_tables(*, root: Path | None = None) -> SDTableSet:
    return _load(require_project(root), SDTableSet, "table")


# ── readiness check ──────────────────────────────────────────────────


def check(*, root: Path | None = None):
    """Run every SD structural validator and return the gaps.

    Bypasses ``assess_readiness`` (which short-circuits while SD is "planned").
    Unlike BN, SD validators depend on view roles, so the real role set is loaded.
    """
    from latris.operations.readiness import _STRUCTURAL_VALIDATORS, SD_VALIDATORS, ValidationContext
    from latris.schema.model_types import get_model_type

    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    ctx = ValidationContext(
        substrate=substrate,
        view_entity_ids=[e.id for e in substrate.entities],
        view_edge_ids=[e.id for e in substrate.edges],
        spec=get_model_type(_MODEL_TYPE),
        roles=_load_roles(paths),
        paths=paths,
    )
    gaps = []
    for name in SD_VALIDATORS:
        gaps.extend(_STRUCTURAL_VALIDATORS[name](ctx))  # type: ignore[operator]
    return gaps


# ── simulation ───────────────────────────────────────────────────────


def build_settings(
    *,
    initial_time: float | None = None,
    final_time: float | None = None,
    dt: float | None = None,
    saveper: float | None = None,
    method: str | None = None,
    time_units: str | None = None,
) -> SDSettings:
    overrides = {
        "initial_time": initial_time, "final_time": final_time, "dt": dt, "saveper": saveper,
        "integration_method": method, "time_units": time_units,
    }
    return SDSettings(**{k: v for k, v in overrides.items() if v is not None})


def simulate(
    *,
    initial_time: float | None = None,
    final_time: float | None = None,
    dt: float | None = None,
    saveper: float | None = None,
    method: str | None = None,
    time_units: str | None = None,
    root: Path | None = None,
) -> SDSimulationResult:
    """Compile the project's SD model and run one deterministic simulation."""
    paths = require_project(root)
    settings = build_settings(
        initial_time=initial_time, final_time=final_time, dt=dt, saveper=saveper,
        method=method, time_units=time_units,
    )
    model = sd_inference.build_model(
        load_model(Substrate, paths.conceptual_yaml),
        _load_roles(paths),
        _load(paths, SDEquationSet, "equations"),
        _load(paths, SDStockSet, "initial_value"),
        _load(paths, SDConstantSet, "constant"),
        _load(paths, SDTableSet, "table"),
        settings,
    )
    return sd_inference.simulate(model)


def record_simulation(result: SDSimulationResult, *, root: Path | None = None) -> tuple[str, str]:
    """Persist a run's full time series to ``analysis/outputs/`` and log an AnalysisRun.

    Returns (commit_sha, run_id).
    """
    from latris.operations._units import library_version as pint_version
    from latris.operations.analysis_runs import record_run
    from latris.schema import new_id

    paths = require_project(root)
    slug = new_id("analysis-run").split("_", 1)[1]
    paths.analysis_outputs_dir.mkdir(parents=True, exist_ok=True)
    artifact = paths.analysis_outputs_dir / f"sd-simulation-{slug}.json"
    artifact.write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
    rel = artifact.relative_to(paths.root).as_posix()

    stocks = [i for i, r in result.roles.items() if r == "stock"]
    span = f"{result.times[0]:g}–{result.times[-1]:g} {result.time_units}" if result.times else "(no output)"
    finals = "; ".join(
        f"{result.labels[s]} {result.series[s][0]:.6g} → {result.series[s][-1]:.6g} {result.units[s]}"
        for s in stocks if result.series[s]
    )
    run, _ = record_run(
        purpose="simulation",
        algorithm=result.algorithm,
        library_version=f"{result.library_version}; pint {pint_version()}",
        hyperparameters=result.settings,
        target_view=_MODEL_TYPE,
        output_summary=f"Simulated {span}{' (FAILED: ' + result.message + ')' if not result.success else ''}. "
                       f"{finals}",
        output_artifacts=[rel],
        metrics={"report_points": len(result.times), "success": result.success, "warnings": len(result.warnings)},
        affected_target_ids=stocks,
        commit=False,
        root=paths.root,
    )
    sha = auto_commit(
        paths.root,
        subject=f"SD simulation: {len(stocks)} stock(s), {span} [{result.method}]",
        body=f"run: {run.id}\nartifact: {rel}",
        paths=[artifact, paths.analysis_runs_jsonl],
    )
    return sha, run.id
