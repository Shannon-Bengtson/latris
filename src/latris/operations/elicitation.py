"""Elicitation session lifecycle — start, record rounds, aggregate, finalise.

Every mutation auto-commits.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from latris.operations.commit import auto_commit
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_model, load_model
from latris.schema import (
    ElicitationIndexEntry,
    ElicitationLog,
    ElicitationSession,
    ExpertActor,
    HumanActor,
    new_id,
)
from latris.schema.elicitation import (
    ElicitationProtocol,
    ExpertResponse,
    TargetAttribute,
)


def _sanitize_slug(text: str, max_len: int = 50) -> str:
    """Lowercase, hyphens only, truncated."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len]


def _session_file_path(paths, held_at: date, protocol: str, slug: str) -> Path:
    return paths.elicitations_dir / f"{held_at.isoformat()}-{protocol}-{slug}.yaml"


def start_session(
    protocol_name: str,
    facilitator_name: str,
    experts: list[str],
    target_attributes: list[tuple[str, str]],
    *,
    held_at: date | None = None,
    root: Path | None = None,
) -> tuple[ElicitationSession, str]:
    """Start a new elicitation session. Returns (session, commit_sha)."""
    paths = require_project(root)
    session_id = new_id("elicitation")
    effective_date = held_at or date.today()

    expert_actors = [ExpertActor(name=name) for name in experts]
    protocol = ElicitationProtocol(name=protocol_name)
    targets = [TargetAttribute(target_id=tid, attribute=attr) for tid, attr in target_attributes]

    slug = _sanitize_slug(targets[0].attribute if targets else "session")
    session_file = _session_file_path(paths, effective_date, protocol_name, slug)

    session = ElicitationSession(
        id=session_id,
        held_at=effective_date,
        facilitator=HumanActor(name=facilitator_name),
        experts=expert_actors,
        protocol=protocol,
        target_attributes=targets,
    )

    session_file.parent.mkdir(parents=True, exist_ok=True)
    dump_model(session, session_file)

    # Update index
    log = load_model(ElicitationLog, paths.elicitations_yaml)
    rel_path = session_file.relative_to(paths.root).as_posix()
    log.entries.append(ElicitationIndexEntry(id=session_id, file_path=rel_path))
    dump_model(log, paths.elicitations_yaml)

    sha = auto_commit(
        paths.root,
        subject=f"Start elicitation session ({protocol_name})",
        body=f"Session {session_id}",
        provenance="human-authored",
        paths=[session_file, paths.elicitations_yaml],
    )
    return session, sha


def _load_session(session_id: str, root: Path | None = None) -> tuple:
    """Load a session by ID via the index. Returns (paths, session, session_file)."""
    paths = require_project(root)
    log = load_model(ElicitationLog, paths.elicitations_yaml)
    for entry in log.entries:
        if entry.id == session_id or session_id.startswith(entry.id[:8]):
            session_file = paths.root / entry.file_path
            session = load_model(ElicitationSession, session_file)
            return paths, session, session_file
    raise ValueError(f"Elicitation session not found: {session_id!r}")


def add_round(
    session_id: str,
    expert_name: str,
    raw_input: str,
    *,
    rationale: str | None = None,
    round_num: int = 1,
    root: Path | None = None,
) -> tuple[ElicitationSession, str]:
    """Add an expert response to a session. Returns (session, commit_sha)."""
    paths, session, session_file = _load_session(session_id, root)
    if session.phase == "finalised":
        raise ValueError("Cannot add rounds to a finalised session.")

    expert = next((e for e in session.experts if e.name == expert_name), None)
    response = ExpertResponse(
        expert=expert,
        round=round_num,
        raw_input=raw_input,
        rationale=rationale,
    )
    session.raw_responses.append(response)
    dump_model(session, session_file)

    sha = auto_commit(
        paths.root,
        subject=f"Add round {round_num} response from {expert_name}",
        body=None,
        provenance="human-authored",
        paths=[session_file],
    )
    return session, sha


def aggregate_session(
    session_id: str,
    aggregated_result: dict,
    *,
    confidence_summary: str | None = None,
    root: Path | None = None,
) -> tuple[ElicitationSession, str]:
    """Set the aggregated result for a session. Returns (session, commit_sha)."""
    paths, session, session_file = _load_session(session_id, root)
    if session.phase == "finalised":
        raise ValueError("Cannot aggregate a finalised session.")

    session.aggregated_result = aggregated_result
    session.confidence_summary = confidence_summary
    dump_model(session, session_file)

    sha = auto_commit(
        paths.root,
        subject=f"Aggregate elicitation session {session_id[:20]}",
        body=confidence_summary,
        provenance="human-authored",
        paths=[session_file],
    )
    return session, sha


def finalise_session(
    session_id: str,
    *,
    root: Path | None = None,
) -> tuple[ElicitationSession, str]:
    """Finalise a session — set phase, update affected attribute provenance."""
    paths, session, session_file = _load_session(session_id, root)
    if session.phase == "finalised":
        raise ValueError("Session is already finalised.")

    session.phase = "finalised"
    dump_model(session, session_file)

    # Update provenance on affected attributes
    changed_files = [session_file]
    from latris.schema import ConfidenceSet, DescriptionSet, PolaritySet

    for attr_file, model_cls in (
        (paths.descriptions_yaml, DescriptionSet),
        (paths.confidence_yaml, ConfidenceSet),
        (paths.view_attribute_path("cld", "polarity"), PolaritySet),
    ):
        store = load_model(model_cls, attr_file)
        modified = False
        for ta in session.target_attributes:
            for entry in store.entries:
                if entry.target_id == ta.target_id and entry.attribute == ta.attribute:
                    entry.origin = "human-elicited"
                    entry.verification = "human-verified"
                    entry.source_id = session.id
                    modified = True
        if modified:
            dump_model(store, attr_file)
            changed_files.append(attr_file)

    sha = auto_commit(
        paths.root,
        subject=f"Finalise elicitation session {session_id[:20]}",
        body=None,
        provenance="human-authored",
        paths=changed_files,
    )
    return session, sha


def list_sessions(*, root: Path | None = None) -> list[ElicitationIndexEntry]:
    """List all elicitation sessions from the index."""
    paths = require_project(root)
    log = load_model(ElicitationLog, paths.elicitations_yaml)
    return list(log.entries)


def get_session(session_id: str, *, root: Path | None = None) -> ElicitationSession:
    """Load a single session by ID."""
    _, session, _ = _load_session(session_id, root)
    return session
