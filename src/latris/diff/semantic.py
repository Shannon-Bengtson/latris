"""Structural, model-aware diffs between two project states.

Inputs are either two commit SHAs or HEAD vs working tree. Output is a flat
list of ``SemanticEvent``s — "Added node X", "Edge polarity flipped",
"Resolved challenge Y (modified)" — rather than raw text diffs. This is what
makes `latris log/diff/status` readable.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from latris.repo import git
from latris.repo.layout import STATE_DIR_NAME, ProjectPaths
from latris.repo.yaml_io import load_model, load_model_from_string
from latris.schema import (
    AssumptionLog,
    ChallengeLog,
    ConfidenceSet,
    DecisionLog,
    DescriptionSet,
    EvidenceLinkSet,
    ExclusionLog,
    MappingRegistry,
    PolaritySet,
    PredictionLog,
    ProjectFoundation,
    QuestionLog,
    ReferenceLibrary,
    SessionLog,
    SignoffLog,
    Substrate,
)


@dataclass
class SemanticEvent:
    kind: str
    summary: str
    path: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    target_id: str | None = None  # the factor or link the event is about, when it's about one
    # What happened to the thing the event is about: added, removed, or changed (an attribute set on a
    # factor, a source attached to a link, a challenge resolved… all change something already there).
    change: str = ""  # derived from kind (kept a plain field so serialisers include it)

    def __post_init__(self) -> None:
        if self.target_id is None:
            self.target_id = self.details.get("id")
        if self.kind.startswith("mapping_"):  # putting a factor in or out of a view changes the factor
            self.change = "changed"
        elif self.kind.endswith("_added") or self.kind in ("project_initialised", "challenge_opened"):
            self.change = "added"
        elif self.kind.endswith("_removed"):
            self.change = "removed"
        else:
            self.change = "changed"


# Labels of the factors and links in the two states being compared, so a summary names what changed
# ("description on Rainfall") rather than its id. Set by the engine for the length of one diff.
_LABELS: ContextVar[dict[str, str] | None] = ContextVar("_LABELS", default=None)


def _name(element_id: str) -> str:
    return (_LABELS.get() or {}).get(element_id) or _id_short(element_id)


# ---------- helpers ----------


def _truncate(text: str | None, limit: int = 60) -> str:
    if not text:
        return ""
    clean = " ".join(text.split())
    return clean if len(clean) <= limit else clean[: limit - 1] + "…"


def _id_short(value: str, keep: int = 15) -> str:
    if len(value) <= keep + 1:
        return value
    return f"{value[:keep]}…"


def _keyed_diff(
    old: Iterable,
    new: Iterable,
    key: Callable[[Any], Any],
) -> tuple[list, list, list[tuple]]:
    old_map = {key(e): e for e in old}
    new_map = {key(e): e for e in new}
    added = [new_map[k] for k in new_map if k not in old_map]
    removed = [old_map[k] for k in old_map if k not in new_map]
    changed = [(old_map[k], new_map[k]) for k in old_map.keys() & new_map.keys() if old_map[k] != new_map[k]]
    return added, removed, changed


# ---------- per-file diffs ----------


def _diff_project(
    old: ProjectFoundation | None,
    new: ProjectFoundation | None,
    path: str,
) -> list[SemanticEvent]:
    if old is None and new is not None:
        return [
            SemanticEvent(
                "project_initialised",
                f"Initialised project: {_truncate(new.statement, 50)}",
                path,
            )
        ]
    if new is None or old is None:
        return []
    events: list[SemanticEvent] = []
    if old.statement != new.statement:
        events.append(
            SemanticEvent(
                "project_statement_changed",
                f"Project statement updated: {_truncate(new.statement, 50)}",
                path,
            )
        )
    return events


def _diff_substrate(
    old: Substrate | None,
    new: Substrate | None,
    path: str,
) -> list[SemanticEvent]:
    old_sub = old or Substrate()
    new_sub = new or Substrate()
    events: list[SemanticEvent] = []

    added, removed, changed = _keyed_diff(old_sub.entities, new_sub.entities, lambda e: e.id)
    for e in added:
        events.append(
            SemanticEvent(
                "node_added",
                f'Added node "{e.label}" ({e.kind})',
                path,
                {"id": e.id},
            )
        )
    for e in removed:
        events.append(
            SemanticEvent(
                "node_removed",
                f'Removed node "{e.label}"',
                path,
                {"id": e.id},
            )
        )
    for old_e, new_e in changed:
        if old_e.label != new_e.label:
            events.append(
                SemanticEvent(
                    "node_renamed",
                    f'Renamed node {_id_short(old_e.id)}: "{old_e.label}" → "{new_e.label}"',
                    path,
                    {"id": new_e.id},
                )
            )
        if old_e.kind != new_e.kind:
            events.append(
                SemanticEvent(
                    "node_retyped",
                    f'Retyped node "{new_e.label}": {old_e.kind} → {new_e.kind}',
                    path,
                    {"id": new_e.id},
                )
            )
        if old_e.maturity != new_e.maturity:
            events.append(
                SemanticEvent(
                    "node_maturity_changed",
                    f'Node "{new_e.label}" maturity: {old_e.maturity} → {new_e.maturity}',
                    path,
                    {"id": new_e.id},
                )
            )
        if old_e.origin != new_e.origin:
            events.append(
                SemanticEvent(
                    "node_origin_changed",
                    f'Node "{new_e.label}" origin: {old_e.origin} → {new_e.origin}',
                    path,
                    {"id": new_e.id},
                )
            )
        if old_e.verification != new_e.verification:
            events.append(
                SemanticEvent(
                    "node_verification_changed",
                    f'Node "{new_e.label}" verification: {old_e.verification} → {new_e.verification}',
                    path,
                    {"id": new_e.id},
                )
            )

    labels = {e.id: e.label for e in list(new_sub.entities) + list(old_sub.entities)}

    added_edges, removed_edges, changed_edges = _keyed_diff(old_sub.edges, new_sub.edges, lambda e: e.id)
    for e in added_edges:
        src = labels.get(e.from_id, _id_short(e.from_id))
        dst = labels.get(e.to_id, _id_short(e.to_id))
        events.append(
            SemanticEvent(
                "edge_added",
                f'Added edge "{src}" → "{dst}" ({e.kind})',
                path,
                {"id": e.id},
            )
        )
    for e in removed_edges:
        src = labels.get(e.from_id, _id_short(e.from_id))
        dst = labels.get(e.to_id, _id_short(e.to_id))
        events.append(
            SemanticEvent(
                "edge_removed",
                f'Removed edge "{src}" → "{dst}"',
                path,
                {"id": e.id},
            )
        )
    for old_e, new_e in changed_edges:
        src = labels.get(new_e.from_id, _id_short(new_e.from_id))
        dst = labels.get(new_e.to_id, _id_short(new_e.to_id))
        if old_e.kind != new_e.kind:
            events.append(
                SemanticEvent(
                    "edge_kind_changed",
                    f'Changed edge kind "{src}" → "{dst}": {old_e.kind} → {new_e.kind}',
                    path,
                    {"id": new_e.id},
                )
            )
        if old_e.maturity != new_e.maturity:
            events.append(
                SemanticEvent(
                    "edge_maturity_changed",
                    f'Edge "{src}" → "{dst}" maturity: {old_e.maturity} → {new_e.maturity}',
                    path,
                    {"id": new_e.id},
                )
            )
        if old_e.origin != new_e.origin:
            events.append(
                SemanticEvent(
                    "edge_origin_changed",
                    f'Edge "{src}" → "{dst}" origin: {old_e.origin} → {new_e.origin}',
                    path,
                    {"id": new_e.id},
                )
            )
        if old_e.verification != new_e.verification:
            events.append(
                SemanticEvent(
                    "edge_verification_changed",
                    f'Edge "{src}" → "{dst}" verification: {old_e.verification} → {new_e.verification}',
                    path,
                    {"id": new_e.id},
                )
            )

    return events


def _fmt_value(v: Any) -> str:
    if isinstance(v, str):
        trimmed = _truncate(v, 60)
        return f'"{trimmed}"'
    return repr(v)


def _diff_attribute_set(
    old: BaseModel | None,
    new: BaseModel | None,
    path: str,
) -> list[SemanticEvent]:
    """Diff any set of entries keyed by (target_id, attribute)."""
    old_entries = getattr(old, "entries", []) if old else []
    new_entries = getattr(new, "entries", []) if new else []
    added, removed, changed = _keyed_diff(
        old_entries,
        new_entries,
        key=lambda e: (e.target_id, e.attribute),
    )
    events: list[SemanticEvent] = []
    for e in added:
        events.append(
            SemanticEvent(
                "attribute_set",
                f"Set {e.attribute} on {_name(e.target_id)}: {_fmt_value(e.value)}",
                path,
                target_id=e.target_id,
            )
        )
    for e in removed:
        events.append(
            SemanticEvent(
                "attribute_removed",
                f"Removed {e.attribute} from {_name(e.target_id)}",
                path,
                target_id=e.target_id,
            )
        )
    for o, n in changed:
        parts: list[str] = []
        if o.value != n.value:
            parts.append(f"value: {_fmt_value(o.value)} → {_fmt_value(n.value)}")
        if o.contested != n.contested:
            parts.append(f"contested: {o.contested} → {n.contested}")
        if o.informants != n.informants:
            parts.append("informants updated")
        if o.origin != n.origin:
            parts.append(f"origin: {o.origin} → {n.origin}")
        if o.verification != n.verification:
            parts.append(f"verification: {o.verification} → {n.verification}")
        if parts:
            events.append(
                SemanticEvent(
                    "attribute_changed",
                    f"{n.attribute} on {_name(n.target_id)}: {'; '.join(parts)}",
                    path,
                    target_id=n.target_id,
                )
            )
    return events


def _diff_evidence(
    old: EvidenceLinkSet | None,
    new: EvidenceLinkSet | None,
    path: str,
) -> list[SemanticEvent]:
    old_entries = old.entries if old else []
    new_entries = new.entries if new else []
    added, removed, changed = _keyed_diff(
        old_entries,
        new_entries,
        key=lambda e: (e.target_id, e.attribute, e.bibkey),
    )
    events: list[SemanticEvent] = []
    for e in added:
        events.append(
            SemanticEvent(
                "evidence_attached",
                f'Attached "{e.bibkey}" to {_name(e.target_id)}/{e.attribute}',
                path,
                target_id=e.target_id,
            )
        )
    for e in removed:
        events.append(
            SemanticEvent(
                "evidence_detached",
                f'Detached "{e.bibkey}" from {_name(e.target_id)}/{e.attribute}',
                path,
                target_id=e.target_id,
            )
        )
    for o, n in changed:
        parts: list[str] = []
        if o.origin != n.origin:
            parts.append(f"origin: {o.origin} → {n.origin}")
        if o.verified_by != n.verified_by:
            parts.append(f"verified_by: {o.verified_by} → {n.verified_by}")
        if o.source_access != n.source_access:
            parts.append(f"source_access: {o.source_access} → {n.source_access}")
        if o.support_verdict != n.support_verdict:
            parts.append(f"support_verdict: {o.support_verdict} → {n.support_verdict}")
        if parts:
            events.append(
                SemanticEvent(
                    "evidence_changed",
                    f'Evidence "{n.bibkey}" on {_name(n.target_id)}/{n.attribute}: {"; ".join(parts)}',
                    path,
                    target_id=n.target_id,
                )
            )
    return events


def _diff_mappings(
    old: MappingRegistry | None,
    new: MappingRegistry | None,
    path: str,
) -> list[SemanticEvent]:
    old_entries = old.entries if old else []
    new_entries = new.entries if new else []
    added, removed, _ = _keyed_diff(
        old_entries,
        new_entries,
        key=lambda m: (m.l2_id, m.l3_view, m.l3_id),
    )
    events: list[SemanticEvent] = []
    for m in added:
        events.append(
            SemanticEvent(
                "mapping_added",
                f"Put {_name(m.l2_id)} in the {m.l3_view} view",
                path,
                target_id=m.l2_id,
            )
        )
    for m in removed:
        events.append(
            SemanticEvent(
                "mapping_removed",
                f"Took {_name(m.l2_id)} out of the {m.l3_view} view",
                path,
                target_id=m.l2_id,
            )
        )
    gone, back, _ = _keyed_diff(
        old.left_out if old else [], new.left_out if new else [], key=lambda x: (x.l2_id, x.l3_view),
    )
    for x in gone:
        why = f": {_truncate(x.reason, 50)}" if x.reason else ""
        events.append(SemanticEvent(
            "left_out_of_view", f"Left {_name(x.l2_id)} out of the {x.l3_view} view{why}", path, target_id=x.l2_id,
        ))
    for x in back:
        events.append(SemanticEvent(
            "put_back_in_view", f"Put {_name(x.l2_id)} back in the {x.l3_view} view", path, target_id=x.l2_id,
        ))
    return events


def _diff_challenges(
    old: ChallengeLog | None,
    new: ChallengeLog | None,
    path: str,
) -> list[SemanticEvent]:
    old_entries = old.entries if old else []
    new_entries = new.entries if new else []
    added, removed, changed = _keyed_diff(old_entries, new_entries, key=lambda c: c.id)
    events: list[SemanticEvent] = []
    for c in added:
        suffix = f"/{c.target_attribute}" if c.target_attribute else ""
        events.append(
            SemanticEvent(
                "challenge_opened",
                f"Opened challenge on {_name(c.target_id)}{suffix}: {_truncate(c.argument, 40)}",
                path,
                target_id=c.target_id,
            )
        )
    for c in removed:
        events.append(
            SemanticEvent(
                "challenge_removed",
                f"Removed challenge {_id_short(c.id)}",
                path,
            )
        )
    for o, n in changed:
        if o.state != n.state:
            if n.state == "open" and o.state != "open":
                events.append(
                    SemanticEvent(
                        "challenge_reopened",
                        f"Reopened challenge {_id_short(n.id)}",
                        path,
                    )
                )
            else:
                events.append(
                    SemanticEvent(
                        "challenge_resolved",
                        f"Resolved challenge {_id_short(n.id)}: {o.state} → {n.state}",
                        path,
                    )
                )
        if len(o.conversation) != len(n.conversation):
            delta = len(n.conversation) - len(o.conversation)
            if delta > 0:
                events.append(
                    SemanticEvent(
                        "challenge_turns_added",
                        f"Added {delta} turn(s) to challenge {_id_short(n.id)}",
                        path,
                    )
                )
    return events


def _summarise_log_entry(entry, kind: str) -> str:
    statement = (
        getattr(entry, "statement", None) or getattr(entry, "question", None) or getattr(entry, "scope", None) or ""
    )
    verb = {
        "assumption": "Logged assumption",
        "decision": "Logged decision",
        "signoff": "Recorded sign-off",
        "session": "Recorded session",
        "question": "Logged question",
        "exclusion": "Logged exclusion",
        "prediction": "Logged prediction",
    }.get(kind, "Added")
    return f"{verb}: {_truncate(statement, 60)}"


def _make_log_differ(kind: str):
    def _diff(old, new, path):
        old_entries = old.entries if old else []
        new_entries = new.entries if new else []
        added, removed, _ = _keyed_diff(old_entries, new_entries, key=lambda e: e.id)
        events: list[SemanticEvent] = []
        for e in added:
            events.append(
                SemanticEvent(
                    f"{kind}_added",
                    _summarise_log_entry(e, kind),
                    path,
                )
            )
        for e in removed:
            events.append(
                SemanticEvent(
                    f"{kind}_removed",
                    f"Removed {kind} {_id_short(e.id)}",
                    path,
                )
            )
        return events

    return _diff


def _diff_references(
    old: ReferenceLibrary | None,
    new: ReferenceLibrary | None,
    path: str,
) -> list[SemanticEvent]:
    old_entries = old.entries if old else []
    new_entries = new.entries if new else []
    added, removed, _ = _keyed_diff(old_entries, new_entries, key=lambda r: r.bibkey)
    events: list[SemanticEvent] = []
    for r in added:
        events.append(
            SemanticEvent(
                "reference_added",
                f'Added reference "{r.bibkey}": {_truncate(r.title, 50)}',
                path,
            )
        )
    for r in removed:
        events.append(
            SemanticEvent(
                "reference_removed",
                f'Removed reference "{r.bibkey}"',
                path,
            )
        )
    return events


# ---------- registry ----------

def _rel(attr: str) -> str:
    """A ``ProjectPaths`` path relative to the project root, posix (git's form)."""
    return getattr(ProjectPaths(Path()), attr).as_posix()


# Paths are stored as posix (forward-slash) to match git's output.
DIFF_REGISTRY: list[tuple[str, type[BaseModel], Callable]] = [
    (_rel("project_yaml"), ProjectFoundation, _diff_project),
    (_rel("conceptual_yaml"), Substrate, _diff_substrate),
    (_rel("mappings_yaml"), MappingRegistry, _diff_mappings),
    (_rel("descriptions_yaml"), DescriptionSet, _diff_attribute_set),
    (_rel("confidence_yaml"), ConfidenceSet, _diff_attribute_set),
    (_rel("polarity_yaml"), PolaritySet, _diff_attribute_set),
    (_rel("evidence_links_yaml"), EvidenceLinkSet, _diff_evidence),
    (_rel("challenges_yaml"), ChallengeLog, _diff_challenges),
    (_rel("references_yaml"), ReferenceLibrary, _diff_references),
    (_rel("assumptions_yaml"), AssumptionLog, _make_log_differ("assumption")),
    (_rel("decisions_yaml"), DecisionLog, _make_log_differ("decision")),
    (_rel("signoffs_yaml"), SignoffLog, _make_log_differ("signoff")),
    (_rel("sessions_yaml"), SessionLog, _make_log_differ("session")),
    (_rel("questions_yaml"), QuestionLog, _make_log_differ("question")),
    (_rel("exclusions_yaml"), ExclusionLog, _make_log_differ("exclusion")),
    (_rel("predictions_yaml"), PredictionLog, _make_log_differ("prediction")),
]


# ---------- engine ----------

# Not changes to the model: latris's own bookkeeping (versions, checkpoints) and generated exports.
_NOT_THE_MODEL = (f"{STATE_DIR_NAME}/", _rel("reports_dir") + "/")


def _is_model_file(path: str) -> bool:
    return not path.startswith(_NOT_THE_MODEL)


def _file_at_commit(root: Path, sha: str, relpath: str) -> str | None:
    """Raw file content at ``sha``, or ``None`` if the file didn't exist there."""
    result = git.run_git(["show", f"{sha}:{relpath}"], cwd=root, check=False)
    if result.returncode != 0:
        return None
    return result.stdout


def _load_at(
    root: Path,
    sha: str | None,
    relpath: str,
    model_cls: type[BaseModel],
) -> BaseModel | None:
    """Load and validate the given path at a commit (or working tree if sha is None)."""
    if sha is None:
        file_path = root / relpath
        if not file_path.exists():
            return None
        return load_model(model_cls, file_path)
    content = _file_at_commit(root, sha, relpath)
    if content is None:
        return None
    return load_model_from_string(model_cls, content)


def _changed_files_between(root: Path, base: str, head: str) -> list[tuple[str, str]]:
    """Return (status, posix_path) pairs — status is A/M/D/R..."""
    result = git.run_git(
        ["diff", "--name-status", "-z", f"{base}..{head}"],
        cwd=root,
    )
    return _parse_name_status_z(result.stdout)


def _working_tree_changes(root: Path) -> list[tuple[str, str]]:
    """Return (status, posix_path) pairs for working-tree + index changes vs HEAD."""
    result = git.run_git(
        ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=root,
    )
    out: list[tuple[str, str]] = []
    # Each record is "XY path\0" — X is index, Y is worktree; both space means clean.
    for chunk in result.stdout.split("\x00"):
        if not chunk:
            continue
        if len(chunk) < 4:
            continue
        xy = chunk[:2]
        path = chunk[3:]
        status = xy.strip() or "?"
        out.append((status, path))
    return out


def _parse_name_status_z(stream: str) -> list[tuple[str, str]]:
    tokens = [t for t in stream.split("\x00") if t]
    out: list[tuple[str, str]] = []
    i = 0
    while i < len(tokens):
        status = tokens[i]
        if status.startswith(("R", "C")) and i + 2 < len(tokens):
            # Renames/copies have two following paths; keep the destination.
            out.append((status[0], tokens[i + 2]))
            i += 3
            continue
        if i + 1 < len(tokens):
            out.append((status, tokens[i + 1]))
        i += 2
    return out


def _labels(*substrates: Substrate | None) -> dict[str, str]:
    """Factor labels and "From → To" link names across the states compared (the later state wins)."""
    out: dict[str, str] = {}
    for sub in substrates:
        if sub is None:
            continue
        nodes = {e.id: e.label for e in sub.entities}
        out.update(nodes)
        out.update({e.id: f"{nodes.get(e.from_id, '?')} → {nodes.get(e.to_id, '?')}" for e in sub.edges})
    return out


def diff_commits(root: Path, base: str, head: str) -> list[SemanticEvent]:
    conceptual = _rel("conceptual_yaml")
    token = _LABELS.set(_labels(
        _load_at(root, base, conceptual, Substrate), _load_at(root, head, conceptual, Substrate),
    ))
    try:
        return _diff_commits(root, base, head)
    finally:
        _LABELS.reset(token)


def _diff_commits(root: Path, base: str, head: str) -> list[SemanticEvent]:
    events: list[SemanticEvent] = []
    registry = {p: (cls, fn) for p, cls, fn in DIFF_REGISTRY}
    for status, path in _changed_files_between(root, base, head):
        if not _is_model_file(path):
            continue
        if path in registry:
            cls, fn = registry[path]
            old = None if status == "A" else _load_at(root, base, path, cls)
            new = None if status == "D" else _load_at(root, head, path, cls)
            events.extend(fn(old, new, path))
        else:
            events.append(
                SemanticEvent(
                    "file_changed",
                    f"{status} {path}",
                    path,
                )
            )
    return events


def diff_working_tree(root: Path) -> list[SemanticEvent]:
    conceptual = _rel("conceptual_yaml")
    token = _LABELS.set(_labels(
        _load_at(root, "HEAD", conceptual, Substrate), _load_at(root, None, conceptual, Substrate),
    ))
    try:
        return _diff_working_tree(root)
    finally:
        _LABELS.reset(token)


def _diff_working_tree(root: Path) -> list[SemanticEvent]:
    events: list[SemanticEvent] = []
    registry = {p: (cls, fn) for p, cls, fn in DIFF_REGISTRY}
    for status, path in _working_tree_changes(root):
        if not _is_model_file(path):
            continue
        if path in registry:
            cls, fn = registry[path]
            is_new = status in ("A", "?", "??")
            old = None if is_new else _load_at(root, "HEAD", path, cls)
            new = _load_at(root, None, path, cls)
            events.extend(fn(old, new, path))
        else:
            events.append(
                SemanticEvent(
                    "file_changed",
                    f"{status} {path}",
                    path,
                )
            )
    return events


def read_log(root: Path, limit: int = 20) -> list[dict[str, str]]:
    """Return the last ``limit`` commits as dicts with sha, subject, iso_date, author."""
    fmt = "%H%x1f%s%x1f%aI%x1f%an"
    result = git.run_git(
        ["log", f"--format={fmt}", f"-n{limit}"],
        cwd=root,
    )
    out: list[dict[str, str]] = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("\x1f")
        if len(parts) < 4:
            continue
        sha, subject, iso_date, author = parts[:4]
        out.append(
            {
                "sha": sha,
                "subject": subject,
                "date": iso_date,
                "author": author,
            }
        )
    return out
