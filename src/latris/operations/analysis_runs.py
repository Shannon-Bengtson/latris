"""Analysis run log — append-only record of algorithm executions.

Distinct from ``ai/interactions.jsonl`` (LLM calls): this records
deterministic algorithm runs — parameter estimation, sensitivity
analysis, structure learning, etc. Each run is the provenance anchor for
whatever it produced: learned CPT rows point their ``source_id`` at the
run's id, and sensitivity artifacts are listed in ``output_artifacts``.

See ``docs/design/DATA_AND_ANALYSIS.md`` for the design rationale.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from latris.operations.commit import auto_commit
from latris.repo import git
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_jsonl_append
from latris.schema import AnalysisRun, HumanActor, new_id

RunPurpose = Literal[
    "structure-learning",
    "parameter-estimation",
    "validation",
    "sensitivity-analysis",
    "inference",
    "calibration",
    "other",
]


def _actor_from_git(root: Path) -> HumanActor:
    name, email = git.get_effective_identity(root)
    return HumanActor(name=name or "(unknown)", email=email or None)


def _head_sha(root: Path) -> str:
    try:
        return git.head_sha(root)
    except Exception:  # no commits yet / not a repo — non-fatal for the record
        return ""


def record_run(
    *,
    purpose: RunPurpose,
    algorithm: str,
    library_version: str,
    hyperparameters: dict | None = None,
    seed: int | None = None,
    input_dataset_ids: list[str] | None = None,
    target_view: str | None = None,
    output_summary: str = "",
    output_artifacts: list[str] | None = None,
    metrics: dict | None = None,
    affected_target_ids: list[str] | None = None,
    duration_seconds: float | None = None,
    commit: bool = True,
    root: Path | None = None,
) -> tuple[AnalysisRun, str | None]:
    """Append a new :class:`AnalysisRun` to ``analysis/runs.jsonl``.

    ``run_by`` and ``input_model_commit`` are filled from git automatically.
    Returns the record and the commit SHA (``None`` if ``commit=False``).
    """
    paths = require_project(root)
    record = AnalysisRun(
        id=new_id("analysis-run"),
        run_by=_actor_from_git(paths.root),
        purpose=purpose,
        algorithm=algorithm,
        library_version=library_version,
        hyperparameters=dict(hyperparameters or {}),
        seed=seed,
        input_dataset_ids=list(input_dataset_ids or []),
        input_model_commit=_head_sha(paths.root),
        target_view=target_view,
        output_summary=output_summary,
        output_artifacts=list(output_artifacts or []),
        metrics=dict(metrics or {}),
        affected_target_ids=list(affected_target_ids or []),
        duration_seconds=duration_seconds,
    )
    dump_jsonl_append(record, paths.analysis_runs_jsonl)

    sha: str | None = None
    if commit:
        sha = auto_commit(
            paths.root,
            subject=f"Analysis run: {purpose} ({algorithm})",
            body=f"id: {record.id}\nlibrary: {library_version}",
            provenance="human-authored",
            paths=[paths.analysis_runs_jsonl],
        )
    return record, sha


def iter_runs(root: Path | None = None) -> Iterable[AnalysisRun]:
    """Iterate validated AnalysisRun records in file (chronological) order."""
    paths = require_project(root)
    if not paths.analysis_runs_jsonl.exists():
        return
    with open(paths.analysis_runs_jsonl, encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            yield AnalysisRun.model_validate(json.loads(raw))


def list_runs(
    *,
    purpose: RunPurpose | None = None,
    limit: int | None = None,
    root: Path | None = None,
) -> list[AnalysisRun]:
    """Read the run log with optional filter, newest first."""
    records = list(iter_runs(root=root))
    if purpose is not None:
        records = [r for r in records if r.purpose == purpose]
    records.reverse()  # newest first
    if limit is not None:
        records = records[:limit]
    return records
