"""Provenance log operations — append-only logs for the audit trail.

Covers assumptions, decisions, model choices, sign-offs, sessions, questions,
exclusions, and predictions. Consumed by the CLI, server routes, and GUI alike.

Author identity is derived from git's effective identity (env or config) so
the commit author and the provenance record always agree on who did what.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from latris.operations._actor import author as _author
from latris.operations._logs import append_entry as _append
from latris.operations.commit import auto_commit
from latris.repo.project import require_project
from latris.repo.yaml_io import load_model
from latris.schema import (
    Assumption,
    AssumptionLog,
    Decision,
    DecisionLog,
    Exclusion,
    ExclusionLog,
    HumanActor,
    Prediction,
    PredictionLog,
    Question,
    QuestionLog,
    Session,
    SessionLog,
    Signoff,
    SignoffLog,
    new_id,
)

# Imported directly from the submodule (not re-exported via schema/__init__ yet).
from latris.schema.provenance import ModelChoice, ModelChoiceLog


def add_assumption(
    statement: str,
    rationale: str | None = None,
    *,
    target_id: str | None = None,
    root: Path | None = None,
) -> tuple[Assumption, str]:
    paths = require_project(root)
    entry = Assumption(
        id=new_id("assumption"),
        statement=statement,
        rationale=rationale,
        target_id=target_id,
        authored_by=_author(paths.root),
    )
    _append(AssumptionLog, paths.assumptions_yaml, entry)
    sha = auto_commit(
        paths.root,
        subject=f"Logged assumption: {_truncate(statement)}",
        body=f"id: {entry.id}",
        paths=[paths.assumptions_yaml],
    )
    return entry, sha


def log_decision(
    statement: str,
    rationale: str,
    *,
    target_id: str | None = None,
    root: Path | None = None,
) -> tuple[Decision, str]:
    paths = require_project(root)
    entry = Decision(
        id=new_id("decision"),
        statement=statement,
        rationale=rationale,
        target_id=target_id,
        authored_by=_author(paths.root),
    )
    _append(DecisionLog, paths.decisions_yaml, entry)
    sha = auto_commit(
        paths.root,
        subject=f"Logged decision: {_truncate(statement)}",
        body=f"id: {entry.id}\nrationale: {rationale}",
        paths=[paths.decisions_yaml],
    )
    return entry, sha


def log_model_choice(
    model_type_id: str,
    action: str,
    rationale: str = "",
    *,
    origin: str = "human-direct",
    root: Path | None = None,
) -> tuple[ModelChoice, str]:
    """Append a model-choice entry (selection / retirement / rationale edit).

    Append-only: the latest entry for a ``model_type_id`` is its current
    rationale; the history shows how the choice and its justification evolved.
    """
    paths = require_project(root)
    entry = ModelChoice(
        id=new_id("model-choice"),
        model_type_id=model_type_id,
        action=action,  # type: ignore[arg-type]
        rationale=rationale,
        origin=origin,  # type: ignore[arg-type]
        authored_by=_author(paths.root),
    )
    _append(ModelChoiceLog, paths.model_choices_yaml, entry)
    sha = auto_commit(
        paths.root,
        subject=f"Model choice: {action} {model_type_id}",
        body=f"id: {entry.id}\nmodel_type: {model_type_id}\naction: {action}\norigin: {origin}",
        paths=[paths.model_choices_yaml],
    )
    return entry, sha


def load_model_choices(root: Path | None = None) -> ModelChoiceLog:
    """Load the append-only model-choice log (empty if none recorded yet)."""
    paths = require_project(root)
    if not paths.model_choices_yaml.exists():
        return ModelChoiceLog()
    return load_model(ModelChoiceLog, paths.model_choices_yaml)


def record_signoff(
    *,
    target_id: str | None = None,
    role: str = "Reviewer",
    scope: str | None = None,
    notes: str | None = None,
    root: Path | None = None,
) -> tuple[Signoff, str]:
    paths = require_project(root)
    effective_scope = scope or ("Model" if target_id is None else target_id)
    entry = Signoff(
        id=new_id("signoff"),
        reviewer=_author(paths.root),
        role=role,
        scope=effective_scope,
        target_id=target_id,
        notes=notes,
    )
    _append(SignoffLog, paths.signoffs_yaml, entry)
    label = target_id[:15] + "…" if target_id else "model"
    sha = auto_commit(
        paths.root,
        subject=f"Recorded sign-off on {label}",
        body=f"id: {entry.id}",
        paths=[paths.signoffs_yaml],
    )
    return entry, sha


def record_session(
    held_at: date,
    attendees: list[str],
    *,
    notes: str | None = None,
    notes_file: str | None = None,
    root: Path | None = None,
) -> tuple[Session, str]:
    if not attendees:
        raise ValueError("at least one attendee is required")
    paths = require_project(root)
    entry = Session(
        id=new_id("session"),
        held_at=held_at,
        attendees=[HumanActor(name=n) for n in attendees],
        notes=notes,
        notes_file=notes_file,
    )
    _append(SessionLog, paths.sessions_yaml, entry)
    sha = auto_commit(
        paths.root,
        subject=f"Recorded session on {held_at.isoformat()} ({len(attendees)} attendees)",
        body=f"id: {entry.id}\nattendees: {', '.join(attendees)}",
        paths=[paths.sessions_yaml],
    )
    return entry, sha


def add_question(
    question: str,
    *,
    target_id: str | None = None,
    root: Path | None = None,
) -> tuple[Question, str]:
    paths = require_project(root)
    entry = Question(
        id=new_id("question"),
        question=question,
        target_id=target_id,
        raised_by=_author(paths.root),
    )
    _append(QuestionLog, paths.questions_yaml, entry)
    sha = auto_commit(
        paths.root,
        subject=f"Logged open question: {_truncate(question)}",
        body=f"id: {entry.id}",
        paths=[paths.questions_yaml],
    )
    return entry, sha


def add_exclusion(
    statement: str,
    rationale: str,
    *,
    root: Path | None = None,
) -> tuple[Exclusion, str]:
    paths = require_project(root)
    entry = Exclusion(
        id=new_id("exclusion"),
        statement=statement,
        rationale=rationale,
        authored_by=_author(paths.root),
    )
    _append(ExclusionLog, paths.exclusions_yaml, entry)
    sha = auto_commit(
        paths.root,
        subject=f"Logged exclusion: {_truncate(statement)}",
        body=f"id: {entry.id}\nrationale: {rationale}",
        paths=[paths.exclusions_yaml],
    )
    return entry, sha


def add_prediction(
    statement: str,
    horizon: str,
    *,
    root: Path | None = None,
) -> tuple[Prediction, str]:
    paths = require_project(root)
    entry = Prediction(
        id=new_id("prediction"),
        statement=statement,
        horizon=horizon,
        authored_by=_author(paths.root),
    )
    _append(PredictionLog, paths.predictions_yaml, entry)
    sha = auto_commit(
        paths.root,
        subject=f"Logged prediction ({horizon}): {_truncate(statement)}",
        body=f"id: {entry.id}",
        paths=[paths.predictions_yaml],
    )
    return entry, sha


def _truncate(text: str, limit: int = 60) -> str:
    clean = " ".join(text.split())
    return clean if len(clean) <= limit else clean[: limit - 1] + "…"
