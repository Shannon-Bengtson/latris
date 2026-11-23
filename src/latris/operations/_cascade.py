"""Remove the rows that describe a deleted node or link.

When a node or link is removed, the rows *about* it — its description,
confidence, polarity, citations, data links, parameter values, roles,
mappings and view membership — go with it, in the same commit. Without
this they linger as orphans: still in the files, still counted by some
readers, pointing at nothing.

Audit records are deliberately left alone: challenges, questions,
findings, signoffs, assumptions and decisions are the history of what was
argued and approved, and stay valid as history after the element is gone.
``latris check integrity`` reports them as pointing at a removed element.

Every parameter and attribute store shares one shape — a top-level
``entries`` list whose rows carry ``target_id`` — so the sweep is
store-agnostic and covers model types added later without changes here.
Saved scenarios are the one other shape (a ``scenarios`` list, each with
``overrides`` rows carrying ``target_id``): an override about a removed
element goes, and a scenario left with nothing to change goes with it.
"""

from __future__ import annotations

from collections.abc import Collection
from pathlib import Path

from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import dump_raw, load_raw


def _entry_store_files(paths: ProjectPaths) -> list[Path]:
    files: list[Path] = []
    for directory in (paths.attributes_dir, paths.parameters_dir, paths.roles_dir):
        if directory.is_dir():
            files.extend(sorted(directory.glob("*.yaml")))
    return files


def _view_files(paths: ProjectPaths) -> list[Path]:
    if not paths.views_dir.is_dir():
        return []
    return sorted(paths.views_dir.glob("*.yaml"))


def _sweep_scenarios(path: Path, doomed: set[str]) -> int:
    """Drop the overrides about *doomed* from a scenarios file (a top-level ``scenarios`` list, each with
    ``overrides`` rows carrying ``target_id``); a scenario left with nothing to change goes too, unless it
    builds on another or another builds on it. Returns the
    number of overrides removed (the file is rewritten if any were)."""
    data = load_raw(path)
    scenarios = data.get("scenarios") if isinstance(data, dict) else None
    if not isinstance(scenarios, list):
        return 0
    removed = 0
    kept_scenarios = []
    extended = {s.get("extends") for s in scenarios if isinstance(s, dict)}  # built on by another: stays
    for s in scenarios:
        rows = s.get("overrides") if isinstance(s, dict) else None
        if not isinstance(rows, list):
            kept_scenarios.append(s)
            continue
        kept = [r for r in rows if not (isinstance(r, dict) and r.get("target_id") in doomed)]
        removed += len(rows) - len(kept)
        s["overrides"] = kept
        if kept or not rows or s.get("extends") or s.get("name") in extended:
            kept_scenarios.append(s)
    if removed:
        data["scenarios"] = kept_scenarios
        dump_raw(data, path)
    return removed


def cascade_removed_ids(paths: ProjectPaths, removed_ids: Collection[str]) -> tuple[list[Path], int]:
    """Drop every row that points at one of *removed_ids*.

    Returns ``(changed_files, rows_removed)``. Writes only files that
    changed; the caller commits them alongside the substrate change.
    """
    doomed = set(removed_ids)
    if not doomed:
        return [], 0
    changed: list[Path] = []
    removed = 0

    for path in _entry_store_files(paths):
        data = load_raw(path)
        entries = data.get("entries") if isinstance(data, dict) else None
        if not isinstance(entries, list):
            swept = _sweep_scenarios(path, doomed)
            if swept:
                removed += swept
                changed.append(path)
            continue
        kept = [row for row in entries if not (isinstance(row, dict) and row.get("target_id") in doomed)]
        if len(kept) != len(entries):
            removed += len(entries) - len(kept)
            data["entries"] = kept
            dump_raw(data, path)
            changed.append(path)

    if paths.mappings_yaml.exists():
        data = load_raw(paths.mappings_yaml)
        touched = False
        for key in ("entries", "left_out"):  # mappings, and what was left out of a view
            rows = data.get(key) if isinstance(data, dict) else None
            if isinstance(rows, list):
                kept = [row for row in rows if not (isinstance(row, dict) and row.get("l2_id") in doomed)]
                if len(kept) != len(rows):
                    removed += len(rows) - len(kept)
                    data[key] = kept
                    touched = True
        if touched:
            dump_raw(data, paths.mappings_yaml)
            changed.append(paths.mappings_yaml)

    for path in _view_files(paths):
        data = load_raw(path)
        if not isinstance(data, dict):
            continue
        touched = False
        for key in ("entity_ids", "edge_ids"):
            ids = data.get(key)
            if isinstance(ids, list) and doomed.intersection(ids):
                data[key] = [i for i in ids if i not in doomed]
                touched = True
        if touched:
            dump_raw(data, path)
            changed.append(path)

    return changed, removed


def cascade_model_type(paths: ProjectPaths, model_type: str, target_ids: Collection[str]) -> tuple[list[Path], int]:
    """Drop the rows that put *target_ids* in ``model_type`` — its role, parameters and their uncertainty —
    leaving the factor itself, its links, citations and every other model type alone.

    How a factor leaves a simulation or a network without being deleted (``sd unset-role``,
    ``bn remove-states``). Returns ``(changed_files, rows_removed)``; the caller commits.
    """
    doomed = set(target_ids)
    changed: list[Path] = []
    removed = 0
    files = [paths.role_path(model_type)]
    if paths.parameters_dir.is_dir():
        files += sorted(paths.parameters_dir.glob(f"{model_type}-*.yaml"))
    for path in files:
        if not path.exists():
            continue
        data = load_raw(path)
        entries = data.get("entries") if isinstance(data, dict) else None
        if not isinstance(entries, list):
            swept = _sweep_scenarios(path, doomed)
            if swept:
                removed += swept
                changed.append(path)
            continue
        kept = [row for row in entries if not (isinstance(row, dict) and row.get("target_id") in doomed)]
        if len(kept) != len(entries):
            removed += len(entries) - len(kept)
            data["entries"] = kept
            dump_raw(data, path)
            changed.append(path)
    unc = paths.parameter_uncertainty_yaml
    if unc.exists():
        data = load_raw(unc)
        entries = data.get("entries") if isinstance(data, dict) else None
        if isinstance(entries, list):
            kept = [row for row in entries if not (
                isinstance(row, dict) and row.get("target_id") in doomed
                and str(row.get("parameter_cell_id") or "").startswith(f"{model_type}:"))]
            if len(kept) != len(entries):
                removed += len(entries) - len(kept)
                data["entries"] = kept
                dump_raw(data, unc)
                changed.append(unc)
    return changed, removed


def records_about(paths: ProjectPaths, ids: Collection[str]) -> list[str]:
    """The audit records (findings, challenges) that mention any of *ids* — kept as history when the
    element is removed, so the caller can say what now points at nothing."""
    from latris.operations.challenges import list_challenges
    from latris.operations.findings import list_findings

    gone = set(ids)
    out = [f"finding: {f.statement}" for f in list_findings(root=paths.root) if gone.intersection(f.target_ids)]
    out += [f"challenge: {c.argument}" for c in list_challenges(root=paths.root) if c.target_id in gone]
    return out
