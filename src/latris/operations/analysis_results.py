"""Recorded analysis results — what the reports show, and whether it's still current.

A *result* is an :class:`~latris.schema.AnalysisRun` whose artifact
(``analysis/outputs/<run_id>.json``) holds the numbers a reader needs: a
simulation's series, a Monte Carlo's bands, a BN query's posteriors. Three
fields on the run make reports work:

- ``result_kind`` — what the artifact holds (``sd-simulation``, ``bn-query``, ...);
- ``analysis_key`` — which runs are "the same analysis"; reports show only the
  latest run of each;
- ``model_fingerprint`` — a hash of the model the run used. When the model
  changes afterwards the result is *stale*: still shown, marked out of date.

``analysis/report.yaml`` lists results hidden from reports; the run log itself
stays append-only.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from latris.operations.analysis_runs import RunPurpose, iter_runs, record_run
from latris.operations.commit import auto_commit
from latris.repo.layout import ProjectPaths
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_model, load_model
from latris.schema import AnalysisRun, ReportSelection, Substrate, new_id

# Order results appear in reports, and the most of each kind a client report shows.
KIND_ORDER: tuple[str, ...] = (
    "sd-simulation", "sd-monte-carlo", "sd-sensitivity", "sd-loops",
    "bn-query", "bn-explanation", "bn-monte-carlo", "bn-sensitivity",
)
REPORT_LIMIT: dict[str, int] = {"bn-query": 6}
_DEFAULT_LIMIT = 4

KIND_MODEL_TYPE = {k: k.split("-", 1)[0] for k in KIND_ORDER}


# ── fingerprints ─────────────────────────────────────────────────────


def _file_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def fingerprint(
    paths: ProjectPaths,
    model_type: str,
    *,
    scenarios: list[str] | None = None,
    uncertainty: bool = False,
) -> str:
    """Hash of everything a ``model_type`` result depends on.

    The model's structure (entities, edges), its roles and parameter files.
    Scenario and uncertainty definitions count only when the run used them, so
    adding a scenario doesn't make an earlier baseline run out of date.
    """
    h = hashlib.sha256()
    if paths.conceptual_yaml.exists():
        sub = load_model(Substrate, paths.conceptual_yaml)
        for e in sorted(sub.entities, key=lambda x: x.id):
            h.update(f"n|{e.id}|{e.label}|{e.kind}\n".encode())
        for e in sorted(sub.edges, key=lambda x: x.id):
            h.update(f"e|{e.id}|{e.from_id}|{e.to_id}|{e.kind}\n".encode())
    h.update(_file_text(paths.role_path(model_type)).encode())
    scenario_file = paths.view_attribute_path(model_type, "scenarios")
    if paths.parameters_dir.exists():
        for f in sorted(paths.parameters_dir.glob(f"{model_type}-*.yaml")):
            if f != scenario_file:
                h.update(f.name.encode() + b"\n" + f.read_bytes())
    if scenarios:
        from latris.operations import sd_scenarios

        defs = {s.name: s.model_dump(mode="json") for s in sd_scenarios.load(paths).scenarios}
        h.update(json.dumps({n: defs.get(n) for n in sorted(scenarios)}, sort_keys=True).encode())
    if uncertainty:
        # Only this model type's ranges (cells "sd:..." / "bn:..."), so a BN range doesn't age an SD run.
        from latris.operations import uncertainty as unc

        own = [e.model_dump(mode="json") for e in unc.load(paths).entries
               if (e.parameter_cell_id or "").startswith(f"{model_type}:")]
        h.update(json.dumps(own, sort_keys=True).encode())
    return h.hexdigest()[:16]


def _fingerprint_inputs(run: AnalysisRun) -> dict[str, Any]:
    return dict(run.hyperparameters.get("fingerprint_inputs") or {})


def is_stale(run: AnalysisRun, paths: ProjectPaths) -> bool:
    if not run.model_fingerprint:
        return True
    inputs = _fingerprint_inputs(run)
    model_type = inputs.get("model_type") or KIND_MODEL_TYPE.get(run.result_kind, run.target_view or "")
    current = fingerprint(
        paths, model_type, scenarios=inputs.get("scenarios") or None, uncertainty=bool(inputs.get("uncertainty"))
    )
    return current != run.model_fingerprint


# ── recording ────────────────────────────────────────────────────────


def record_result(
    *,
    kind: str,
    key: str,
    payload: dict[str, Any],
    purpose: RunPurpose,
    algorithm: str,
    library_version: str,
    summary: str,
    model_type: str,
    hyperparameters: dict | None = None,
    scenarios: list[str] | None = None,
    uncertainty: bool = False,
    seed: int | None = None,
    metrics: dict | None = None,
    affected_target_ids: list[str] | None = None,
    duration_seconds: float | None = None,
    commit_subject: str | None = None,
    root: Path | None = None,
) -> tuple[str, AnalysisRun]:
    """Write ``payload`` to ``analysis/outputs/<run_id>.json``, log the run, commit both.

    Returns (commit_sha, run).
    """
    paths = require_project(root)
    run_id = new_id("analysis-run")
    paths.analysis_outputs_dir.mkdir(parents=True, exist_ok=True)
    artifact = paths.analysis_outputs_dir / f"{run_id}.json"
    artifact.write_text(json.dumps({"kind": kind, "result": payload}, indent=1, default=str), encoding="utf-8")
    rel = artifact.relative_to(paths.root).as_posix()
    inputs = {"model_type": model_type, "scenarios": sorted(scenarios or []), "uncertainty": uncertainty}
    run, _ = record_run(
        run_id=run_id,
        purpose=purpose,
        algorithm=algorithm,
        library_version=library_version,
        hyperparameters={**(hyperparameters or {}), "fingerprint_inputs": inputs},
        seed=seed,
        target_view=model_type,
        output_summary=summary,
        output_artifacts=[rel],
        metrics=metrics,
        affected_target_ids=affected_target_ids,
        duration_seconds=duration_seconds,
        result_kind=kind,
        analysis_key=key,
        model_fingerprint=fingerprint(paths, model_type, scenarios=scenarios, uncertainty=uncertainty),
        commit=False,
        root=paths.root,
    )
    sha = auto_commit(
        paths.root,
        subject=commit_subject or f"Analysis: {kind} ({algorithm})",
        body=f"run: {run.id}\nartifact: {rel}\n{summary}"[:2000],
        paths=[artifact, paths.analysis_runs_jsonl],
    )
    return sha, run


def load_payload(run: AnalysisRun, *, root: Path | None = None) -> dict[str, Any] | None:
    """The result an artifact holds, or ``None`` if it's missing or unreadable."""
    paths = require_project(root)
    for rel in run.output_artifacts:
        path = paths.root / rel
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data.get("result", data) if isinstance(data, dict) else None
    return None


# ── selection ────────────────────────────────────────────────────────


def _selection(paths: ProjectPaths) -> ReportSelection:
    p = paths.analysis_report_yaml
    return load_model(ReportSelection, p) if p.exists() else ReportSelection()


@dataclass(frozen=True)
class ReportResult:
    run: AnalysisRun
    payload: dict[str, Any]
    stale: bool


def _scope(run: AnalysisRun) -> frozenset[str]:
    """The scenarios a simulation compared: a JSON list since 0.9.1, comma-separated before."""
    rest = run.analysis_key.split("|", 1)[-1]
    try:
        names = json.loads(rest)
        if isinstance(names, list):
            return frozenset(str(n) for n in names)
    except ValueError:
        pass
    return frozenset(s for s in rest.split(",") if s)


def report_results(
    *,
    model_types: list[str] | None = None,
    include_hidden: bool = False,
    root: Path | None = None,
) -> list[ReportResult]:
    """The results reports show: the latest run of each analysis, oldest kind first.

    A simulation whose scenarios are all covered by a later simulation is
    superseded by it. Hidden runs are left out unless ``include_hidden``.
    """
    paths = require_project(root)
    hidden = set(_selection(paths).hidden)
    latest: dict[tuple[str, str], AnalysisRun] = {}
    for run in iter_runs(root=paths.root):
        if not run.result_kind or run.result_kind not in KIND_ORDER:
            continue
        if model_types is not None and KIND_MODEL_TYPE[run.result_kind] not in model_types:
            continue
        if run.id in hidden and not include_hidden:
            continue
        latest[(run.result_kind, run.analysis_key)] = run  # file order is chronological

    runs = list(latest.values())
    sims = [r for r in runs if r.result_kind == "sd-simulation"]
    runs = [
        r for r in runs
        if r.result_kind != "sd-simulation"
        or not any(o is not r and o.id > r.id and _scope(r) <= _scope(o) for o in sims)
    ]
    out: list[ReportResult] = []
    for kind in KIND_ORDER:
        of_kind = sorted((r for r in runs if r.result_kind == kind), key=lambda r: r.id, reverse=True)
        for run in of_kind[: REPORT_LIMIT.get(kind, _DEFAULT_LIMIT)]:
            payload = load_payload(run, root=paths.root)
            if payload is None:
                continue
            out.append(ReportResult(run=run, payload=payload, stale=is_stale(run, paths)))
    return out


def list_results(*, root: Path | None = None) -> list[tuple[AnalysisRun, bool, bool]]:
    """Every recorded result, newest first, as (run, hidden, stale)."""
    paths = require_project(root)
    hidden = set(_selection(paths).hidden)
    runs = [r for r in iter_runs(root=paths.root) if r.result_kind]
    runs.reverse()
    return [(r, r.id in hidden, is_stale(r, paths)) for r in runs]


def _find(run_ref: str, paths: ProjectPaths) -> AnalysisRun:
    runs = [r for r in iter_runs(root=paths.root) if r.result_kind]
    exact = [r for r in runs if r.id == run_ref]
    matches = exact or [r for r in runs if r.id.startswith(run_ref) or r.id.split("_", 1)[-1].startswith(run_ref)]
    if not matches:
        raise ValueError(f"no recorded result {run_ref!r}; see `latris results list`")
    if len(matches) > 1:
        raise ValueError(f"{run_ref!r} matches {len(matches)} results; give more of the id")
    return matches[0]


def get_result(run_ref: str, *, root: Path | None = None) -> tuple[AnalysisRun, dict[str, Any] | None]:
    paths = require_project(root)
    run = _find(run_ref, paths)
    return run, load_payload(run, root=paths.root)


def set_hidden(run_ref: str, hidden: bool, *, root: Path | None = None) -> tuple[AnalysisRun, str | None]:
    """Hide a result from reports (or show it again). Returns (run, commit_sha or None if unchanged)."""
    paths = require_project(root)
    run = _find(run_ref, paths)
    sel = _selection(paths)
    ids = [i for i in sel.hidden if i != run.id] + ([run.id] if hidden else [])
    if ids == sel.hidden:
        return run, None
    paths.analysis_dir.mkdir(parents=True, exist_ok=True)
    dump_model(ReportSelection(hidden=ids), paths.analysis_report_yaml)
    sha = auto_commit(
        paths.root,
        subject=f"{'Hide' if hidden else 'Show'} result in reports: {run.result_kind}",
        body=f"run: {run.id}\n{run.output_summary}"[:2000],
        paths=[paths.analysis_report_yaml],
    )
    return run, sha
