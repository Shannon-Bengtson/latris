"""Does every pointer in the project resolve? One read-only pass.

The schema validates each file's *shape*; this checks the relationships
*between* files — the part a hand edit, a bad merge or a partial apply can
break while every file still loads. It never writes.

Severities:

- ``error`` — the project says something that can't be true: a link to a
  node that isn't there, a citation of a source that isn't in the library,
  two nodes sharing a label. Blocks ``latris check handover``.
- ``warning`` — a provenance or audit pointer that doesn't resolve or names
  the wrong kind of record (``source_id`` vs ``origin``), or a stored
  extract over the length limit. Worth fixing; doesn't block.
- ``info`` — history pointing at something since removed: a challenge,
  question, signoff, assumption, decision or finding about a deleted node
  or link. Expected after a removal; listed so a reviewer isn't surprised.

``source_id`` follows the origin → record table in
``docs/engineering/SCHEMA_NOTES.md``: ``ai-proposed`` → an AI interaction,
``data-derived`` → an analysis run, ``human-elicited`` → an elicitation
session, ``human-direct`` → none. ``mixed`` may point at any of the three;
``imported`` may carry the source project's pointer, which needn't resolve
here.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from latris.repo.layout import ProjectPaths
from latris.repo.project import require_project
from latris.repo.yaml_io import iter_jsonl, load_model, load_model_or_default, load_raw
from latris.schema.ids import parse_id

if TYPE_CHECKING:
    from latris.schema import Substrate

Severity = Literal["error", "warning", "info"]

_SOURCE_KIND_FOR_ORIGIN: dict[str, str] = {
    "ai-proposed": "interaction",
    "data-derived": "analysis-run",
    "human-elicited": "elicitation",
}
_SOURCE_KIND_NAME = {
    "interaction": "AI interaction",
    "analysis-run": "analysis run",
    "elicitation": "elicitation session",
}


@dataclass
class IntegrityProblem:
    severity: Severity
    # e.g. dangling_edge_endpoint | dangling_target | unknown_bibkey | unknown_dataset | duplicate_label
    # | duplicate_edge | duplicate_id | malformed_id | source_mismatch | dangling_source
    # | dangling_supersedes | extract_too_long | audit_target_removed
    kind: str
    message: str
    where: str  # project-relative file the problem lives in
    ids: list[str] = field(default_factory=list)


@dataclass
class IntegrityReport:
    problems: list[IntegrityProblem]

    @property
    def errors(self) -> list[IntegrityProblem]:
        return [p for p in self.problems if p.severity == "error"]

    @property
    def ok(self) -> bool:
        return not self.errors


def _rel(paths: ProjectPaths, path: Path) -> str:
    try:
        return path.relative_to(paths.root).as_posix()
    except ValueError:
        return str(path)


def _entries(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = load_raw(path)
    rows = data.get("entries") if isinstance(data, dict) else None
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def _jsonl_ids(cls: type, path: Path) -> set[str]:
    return {rec.id for rec in iter_jsonl(cls, path)} if path.exists() else set()


@dataclass
class _Pass:
    """One pass over the project: what the checks read, and the problems they find."""

    paths: ProjectPaths
    substrate: Substrate
    problems: list[IntegrityProblem] = field(default_factory=list)
    # The provenance records a source_id can point at, by kind (see ``_source_records``).
    records: dict[str, set[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.entity_ids = {e.id for e in self.substrate.entities}
        self.element_ids = self.entity_ids | {e.id for e in self.substrate.edges}
        self.label_of = {e.id: e.label for e in self.substrate.entities}

    def add(self, severity: Severity, kind: str, message: str, where: Path, ids: Iterable[str] = ()) -> None:
        self.problems.append(IntegrityProblem(severity, kind, message, _rel(self.paths, where), list(ids)))

    def missing(self, ids: Iterable[Any]) -> list[str]:
        """Those of *ids* that name no node or link in the model, sorted."""
        return sorted({str(i) for i in ids if i and i not in self.element_ids})

    def check_source(self, origin: str | None, source_id: str | None, where: Path, owner: str) -> None:
        """Does *owner*'s ``source_id`` point at the kind of record its ``origin`` says it should?"""
        if not source_id or origin is None:
            return
        if origin == "human-direct":
            self.add("warning", "source_mismatch",
                     f"{owner} is human-direct but carries source_id {source_id}", where, [source_id])
            return
        if origin == "imported":
            return  # the source project's pointer; needn't resolve here
        records = self.records
        allowed = list(records) if origin == "mixed" else [_SOURCE_KIND_FOR_ORIGIN.get(origin, "")]
        if any(source_id in records.get(k, set()) for k in allowed):
            return
        actual = next((k for k, ids in records.items() if source_id in ids), None)
        if actual is not None:
            self.add("warning", "source_mismatch",
                     f"{owner} is {origin} but its source_id is an {_SOURCE_KIND_NAME[actual]} ({source_id})",
                     where, [source_id])
        else:
            wanted = " or ".join(_SOURCE_KIND_NAME[k] for k in allowed if k in _SOURCE_KIND_NAME)
            self.add("warning", "dangling_source",
                     f"{owner} ({origin}) points at {source_id}, which isn't a recorded {wanted}", where, [source_id])


def check_integrity(*, root: Path | None = None) -> IntegrityReport:
    """Check every cross-file pointer in the project. Read-only."""
    from latris.schema import Substrate

    paths = require_project(root)
    check = _Pass(paths, load_model(Substrate, paths.conceptual_yaml))
    _check_ids(check)
    _check_duplicate_labels(check)
    _check_edges(check)
    check.records = _source_records(paths)
    for item in [*check.substrate.entities, *check.substrate.edges]:
        check.check_source(item.origin, item.source_id, paths.conceptual_yaml, item.id)
    _check_stores(check)
    _check_mappings(check)
    _check_views(check)
    _check_evidence(check)
    _check_data_links(check)
    _check_findings(check)
    _check_audit_logs(check)
    return IntegrityReport(check.problems)


# ── Substrate: IDs, endpoints, duplicates ───────────────────────────────


def _check_ids(check: _Pass) -> None:
    substrate, conceptual = check.substrate, check.paths.conceptual_yaml
    for expected, items in (("node", substrate.entities), ("edge", substrate.edges)):
        for item in items:
            try:
                kind, _ = parse_id(item.id)
            except ValueError as exc:
                check.add("error", "malformed_id", f"{expected} ID isn't valid: {exc}", conceptual, [item.id])
                continue
            if kind != expected:
                check.add("error", "malformed_id", f"{expected} has a {kind!r} ID: {item.id}", conceptual, [item.id])

    for dup, n in Counter([e.id for e in substrate.entities] + [e.id for e in substrate.edges]).items():
        if n > 1:
            check.add("error", "duplicate_id", f"ID used {n} times: {dup}", conceptual, [dup])


def _check_duplicate_labels(check: _Pass) -> None:
    by_label: dict[str, list[str]] = {}
    for e in check.substrate.entities:
        by_label.setdefault(" ".join(e.label.split()).casefold(), []).append(e.id)
    for ids in by_label.values():
        if len(ids) > 1:
            check.add("error", "duplicate_label",
                      f'{len(ids)} nodes are called "{check.label_of[ids[0]]}" — a label can address only one',
                      check.paths.conceptual_yaml, ids)


def _check_edges(check: _Pass) -> None:
    label_of, conceptual = check.label_of, check.paths.conceptual_yaml
    seen_edges: dict[tuple[str, str, str], str] = {}
    for edge in check.substrate.edges:
        missing = [end for end in (edge.from_id, edge.to_id) if end not in check.entity_ids]
        if missing:
            check.add("error", "dangling_edge_endpoint",
                      f"link {edge.id} joins a node that isn't there: {', '.join(missing)}", conceptual, [edge.id])
        key = (edge.from_id, edge.to_id, edge.kind)
        if key in seen_edges:
            check.add("error", "duplicate_edge",
                      f'two {edge.kind} links "{label_of.get(edge.from_id, edge.from_id)}" → '
                      f'"{label_of.get(edge.to_id, edge.to_id)}"',
                      conceptual, [seen_edges[key], edge.id])
        else:
            seen_edges[key] = edge.id


def _source_records(paths: ProjectPaths) -> dict[str, set[str]]:
    """The provenance records a ``source_id`` can point at, by kind."""
    from latris.schema import AnalysisRun
    from latris.schema.ai import AIInteraction
    from latris.schema.elicitation import ElicitationLog

    return {
        "interaction": _jsonl_ids(AIInteraction, paths.interactions_jsonl),
        "analysis-run": _jsonl_ids(AnalysisRun, paths.analysis_runs_jsonl),
        "elicitation": (
            {e.id for e in load_model(ElicitationLog, paths.elicitations_yaml).entries}
            if paths.elicitations_yaml.exists() else set()
        ),
    }


# ── The files that point at the substrate ───────────────────────────────


def _check_stores(check: _Pass) -> None:
    """Attribute, parameter and role stores."""
    paths = check.paths
    store_files: list[Path] = []
    for directory in (paths.attributes_dir, paths.parameters_dir, paths.roles_dir):
        if directory.is_dir():
            store_files.extend(sorted(directory.glob("*.yaml")))
    for path in store_files:
        if path == paths.evidence_links_yaml or path == paths.data_links_yaml:
            continue  # checked with their own pointers (_check_evidence, _check_data_links)
        dangling = check.missing(r.get("target_id") for r in _entries(path))
        if dangling:
            check.add("error", "dangling_target",
                      f"{len(dangling)} row(s) describe a node or link that isn't there", path, dangling)
        for r in _entries(path):
            check.check_source(r.get("origin"), r.get("source_id"), path, str(r.get("target_id")))


def _check_mappings(check: _Pass) -> None:
    mappings = check.paths.mappings_yaml
    if not mappings.exists():
        return
    raw = load_raw(mappings)
    left_out = raw.get("left_out") if isinstance(raw, dict) else None
    rows = [*_entries(mappings), *(r for r in (left_out or []) if isinstance(r, dict))]
    dangling = check.missing(r.get("l2_id") for r in rows)
    if dangling:
        check.add("error", "dangling_target",
                  f"{len(dangling)} mapping(s) map a node or link that isn't there", mappings, dangling)


def _check_views(check: _Pass) -> None:
    if not check.paths.views_dir.is_dir():
        return
    for path in sorted(check.paths.views_dir.glob("*.yaml")):
        data = load_raw(path)
        if not isinstance(data, dict):
            continue
        listed = [*(data.get("entity_ids") or []), *(data.get("edge_ids") or [])]
        dangling = sorted({i for i in listed if i not in check.element_ids})
        if dangling:
            check.add("error", "dangling_target",
                      f"view lists {len(dangling)} node(s)/link(s) that aren't there", path, dangling)


def _check_evidence(check: _Pass) -> None:
    """Citations, and the reference library they cite."""
    from latris.schema import ReferenceLibrary
    from latris.schema.references import SNAPSHOT_EXTRACT_MAX

    paths = check.paths
    evidence = paths.evidence_links_yaml
    library = load_model_or_default(ReferenceLibrary, paths.references_yaml)
    bibkeys = {r.bibkey for r in library.entries}
    ev_rows = _entries(evidence)
    dangling = check.missing(r.get("target_id") for r in ev_rows)
    if dangling:
        check.add("error", "dangling_target",
                  f"{len(dangling)} citation target(s) aren't in the model", evidence, dangling)
    unknown = sorted({str(r["bibkey"]) for r in ev_rows if r.get("bibkey") and r["bibkey"] not in bibkeys})
    if unknown:
        check.add("error", "unknown_bibkey",
                  f"cited source(s) not in the reference library: {', '.join(unknown)}", evidence, unknown)
    for r in ev_rows:
        check.check_source(r.get("origin"), r.get("source_id"), evidence, f"citation of {r.get('bibkey')}")

    for ref in library.entries:
        snap = ref.source_snapshot
        if snap is not None and snap.extract and len(snap.extract) > SNAPSHOT_EXTRACT_MAX:
            check.add("warning", "extract_too_long",
                      f"{ref.bibkey}: stored extract is {len(snap.extract)} characters (limit {SNAPSHOT_EXTRACT_MAX})",
                      paths.references_yaml, [ref.bibkey])


def _check_data_links(check: _Pass) -> None:
    from latris.schema import DatasetLibrary

    paths = check.paths
    datasets = (
        {d.id for d in load_model(DatasetLibrary, paths.data_datasets_yaml).entries}
        if paths.data_datasets_yaml.exists() else set()
    )
    dl_rows = _entries(paths.data_links_yaml)
    dangling = check.missing(r.get("target_id") for r in dl_rows)
    if dangling:
        check.add("error", "dangling_target",
                  f"{len(dangling)} data link(s) describe a node or link that isn't there",
                  paths.data_links_yaml, dangling)
    unknown = sorted({str(r["dataset_id"]) for r in dl_rows if r.get("dataset_id") and r["dataset_id"] not in datasets})
    if unknown:
        check.add("error", "unknown_dataset",
                  f"data link(s) name a dataset that isn't registered: {', '.join(unknown)}",
                  paths.data_links_yaml, unknown)


def _check_findings(check: _Pass) -> None:
    from latris.schema import Finding

    path = check.paths.findings_jsonl
    findings = list(iter_jsonl(Finding, path)) if path.exists() else []
    finding_ids = {f.id for f in findings}
    for f in findings:
        missing = [s for s in f.supersedes if s not in finding_ids]
        if missing:
            check.add("warning", "dangling_supersedes",
                      f"finding {f.id} supersedes finding(s) that aren't recorded: {', '.join(missing)}",
                      path, missing)
        gone = [t for t in f.target_ids if t not in check.element_ids]
        if gone:
            check.add("info", "audit_target_removed",
                      f"finding {f.id} is about node(s)/link(s) since removed", path, gone)
        check.check_source(f.origin, f.source_id, path, f"finding {f.id}")


def _check_audit_logs(check: _Pass) -> None:
    """History about removed elements: kept, and listed so a reviewer isn't surprised."""
    from latris.schema import AssumptionLog, ChallengeLog, DecisionLog, QuestionLog, SignoffLog

    paths = check.paths
    audit_logs = [
        (ChallengeLog, paths.challenges_yaml, "challenge"),
        (QuestionLog, paths.questions_yaml, "question"),
        (SignoffLog, paths.signoffs_yaml, "signoff"),
        (AssumptionLog, paths.assumptions_yaml, "assumption"),
        (DecisionLog, paths.decisions_yaml, "decision"),
    ]
    for cls, path, noun in audit_logs:
        if not path.exists():
            continue
        entries = load_model(cls, path).entries
        gone = sorted({e.target_id for e in entries if e.target_id and e.target_id not in check.element_ids})
        if gone:
            check.add("info", "audit_target_removed",
                      f"{len(gone)} {noun} record(s) are about node(s)/link(s) since removed (kept as history)",
                      path, gone)


def remove_dangling_rows(*, root: Path | None = None) -> tuple[int, str]:
    """Remove attribute, parameter, role, citation, data-link, mapping and view rows
    about nodes or links that no longer exist — the leftovers of removals made
    before removal cleaned up after itself. Audit history is kept.

    Returns ``(rows_removed, commit_sha)``; ``(0, "")`` when there was nothing to do.
    """
    from latris.operations._cascade import cascade_removed_ids
    from latris.operations.commit import auto_commit
    from latris.schema import Substrate

    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    present = {e.id for e in substrate.entities} | {e.id for e in substrate.edges}
    missing = {
        i for p in check_integrity(root=paths.root).problems
        if p.kind == "dangling_target" for i in p.ids if i not in present
    }
    changed, removed = cascade_removed_ids(paths, missing)
    if not removed:
        return 0, ""
    sha = auto_commit(
        paths.root,
        subject=f"Removed {removed} row(s) about deleted nodes/links",
        body="ids: " + ", ".join(sorted(missing)),
        paths=changed,
    )
    return removed, sha
