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
            continue
        kept = [row for row in entries if not (isinstance(row, dict) and row.get("target_id") in doomed)]
        if len(kept) != len(entries):
            removed += len(entries) - len(kept)
            data["entries"] = kept
            dump_raw(data, path)
            changed.append(path)

    if paths.mappings_yaml.exists():
        data = load_raw(paths.mappings_yaml)
        entries = data.get("entries") if isinstance(data, dict) else None
        if isinstance(entries, list):
            kept = [row for row in entries if not (isinstance(row, dict) and row.get("l2_id") in doomed)]
            if len(kept) != len(entries):
                removed += len(entries) - len(kept)
                data["entries"] = kept
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
