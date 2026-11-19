"""Results a share link carries as the sender's, because they can't be re-run where the link opens.

A link carries the model, not its results: opening it re-runs every analysis from the parameters it
carries, so the numbers are always computed, never pasted. An analysis that read a dataset (effect
estimation, impact estimation) can't be re-run that way — links don't carry data — so rather than
leave it out (a link must never show less than the sender's report), its result travels as the
sender's: the recorded payload, the datasets it read (name and content hash), and a note in the report
that says so. Anyone with the same data can check the number; nobody gets the data from the link.

Payloads name factors and links by the sender's ids; on export those become labels
(``{{node:Label}}``, ``{{link:From -> To}}``), and on import this project's ids.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from latris.repo.layout import ProjectPaths
from latris.repo.project import require_project
from latris.repo.yaml_io import load_model
from latris.schema import Substrate
from latris.schema.build_spec import SpecCarriedResult

_ID = re.compile(r"\b(node|edge)_[0-9A-HJKMNP-TV-Z]{26}\b")
_TOKEN = re.compile(r"\{\{(node|link):(.*?)\}\}")
CARRIED = "carried_from_link"  # the run's hyperparameters key that marks a carried result


def _walk(value: Any, fn) -> Any:  # noqa: ANN001 — fn maps one string
    if isinstance(value, dict):
        return {_walk(k, fn): _walk(v, fn) for k, v in value.items()}
    if isinstance(value, list):
        return [_walk(v, fn) for v in value]
    return fn(value) if isinstance(value, str) else value


def _names(paths: ProjectPaths) -> tuple[dict[str, str], dict[str, str]]:
    sub = load_model(Substrate, paths.conceptual_yaml)
    nodes = {e.id: e.label for e in sub.entities}
    links = {e.id: f"{nodes.get(e.from_id, e.from_id)} -> {nodes.get(e.to_id, e.to_id)}" for e in sub.edges}
    return nodes, links


def needs_dataset(kind: str) -> bool:
    from latris.operations.analysis_results import result_surfaces

    return any(r.kind == kind and r.needs_dataset for r in result_surfaces())


def export_carried(*, root: Path | None = None) -> list[SpecCarriedResult]:
    """The results reports show that need a dataset (stale ones left out), as the sender's."""
    from latris.operations.analysis_results import get_result, report_results

    paths = require_project(root)
    nodes, links = _names(paths)

    def label(s: str) -> str:
        def one(m: re.Match[str]) -> str:
            i = m.group(0)
            if i in nodes:
                return "{{node:" + nodes[i] + "}}"
            return "{{link:" + links[i] + "}}" if i in links else i
        return _ID.sub(one, s)

    out = []
    for r in report_results(root=paths.root):
        if r.stale or not needs_dataset(r.run.result_kind):
            continue
        run, payload = get_result(r.run.id, root=paths.root)
        if payload is None:
            continue
        carried = run.hyperparameters.get(CARRIED) or {}
        datasets = carried.get("datasets") or _datasets(payload)
        out.append(SpecCarriedResult(
            kind=run.result_kind, model_type=run.target_view or "", key=label(run.analysis_key),
            summary=run.output_summary, purpose=run.purpose, algorithm=run.algorithm,
            library_version=run.library_version, datasets=datasets, payload=_walk(payload, label),
        ))
    return out


def _datasets(payload: dict[str, Any]) -> list[dict[str, str]]:
    ds = payload.get("dataset")
    found = ds if isinstance(ds, list) else [ds] if isinstance(ds, dict) else []
    return [{"name": str(d.get("name", "")), "sha256": str(d.get("sha256", ""))} for d in found if d.get("name")]


def import_carried(items: list[SpecCarriedResult], *, root: Path | None = None) -> list[str]:
    """Record each carried result in this project, marked as the sender's; returns the run ids."""
    from latris.operations.analysis_results import record_result

    paths = require_project(root)
    nodes, links = _names(paths)
    node_ids = {label.casefold(): i for i, label in nodes.items()}
    link_ids = {label.casefold(): i for i, label in links.items()}

    def resolve(s: str) -> str:
        def one(m: re.Match[str]) -> str:
            table = node_ids if m.group(1) == "node" else link_ids
            return table.get(m.group(2).casefold(), m.group(2))
        return _TOKEN.sub(one, s)

    run_ids = []
    for item in items:
        _, run = record_result(
            kind=item.kind, key=resolve(item.key), payload=_walk(item.payload, resolve),
            purpose=item.purpose, algorithm=item.algorithm or "carried",  # type: ignore[arg-type]
            library_version=item.library_version, summary=item.summary, model_type=item.model_type,
            hyperparameters={CARRIED: {"datasets": item.datasets}},
            commit_subject=f"Carried result from a link: {item.kind}", root=paths.root,
        )
        run_ids.append(run.id)
    return run_ids


def carried_note(hyperparameters: dict[str, Any]) -> list[str]:
    """The report's line under a carried result (``[]`` for one computed here)."""
    carried = hyperparameters.get(CARRIED)
    if carried is None:
        return []
    named = [f"'{d['name']}'" + (f" (sha256 {d['sha256'][:12]}…)" if d.get("sha256") else "")
             for d in carried.get("datasets") or []]
    data = f"dataset {', '.join(named)}" if named else "a dataset"
    return [f"> **Computed by the sender** from {data}. The data isn't in this link, so it can't be re-run "
            "here; anyone with the same data can check it.", ""]
