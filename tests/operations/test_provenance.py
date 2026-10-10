from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from latris.operations import provenance as ops
from latris.operations.init import init_project
from latris.repo import git
from latris.repo.yaml_io import load_model
from latris.schema import (
    AssumptionLog,
    DecisionLog,
    ExclusionLog,
    PredictionLog,
    QuestionLog,
    SessionLog,
    SignoffLog,
)


@pytest.fixture
def project(tmp_path: Path, git_identity):
    root = tmp_path / "demo"
    init_project(root, statement="Q?")
    return root


def _commit_count(root: Path) -> int:
    return int(git.run_git(["rev-list", "--count", "HEAD"], cwd=root).stdout.strip())


def test_add_assumption(project: Path, git_identity) -> None:
    before = _commit_count(project)
    entry, _ = ops.add_assumption(
        "Market is liquid.",
        rationale="Industry norm.",
        root=project,
    )
    assert entry.statement == "Market is liquid."
    assert entry.rationale == "Industry norm."
    assert entry.authored_by.name == git_identity[0]

    log = load_model(AssumptionLog, project / "provenance" / "assumptions.yaml")
    assert len(log.entries) == 1
    assert log.entries[0].id == entry.id
    assert _commit_count(project) == before + 1


def test_log_decision_requires_rationale(project: Path) -> None:
    # Our API requires rationale as a positional-kwarg with no default.
    entry, _ = ops.log_decision(
        "Excluded macro shocks.",
        "Out of scope for Q1 window.",
        root=project,
    )
    log = load_model(DecisionLog, project / "provenance" / "decisions.yaml")
    assert log.entries[0].id == entry.id
    assert log.entries[0].rationale == "Out of scope for Q1 window."


def test_record_signoff(project: Path, git_identity) -> None:
    entry, _ = ops.record_signoff(role="Senior reviewer", scope="Substrate v0.1", root=project)
    assert entry.reviewer.name == git_identity[0]
    assert entry.role == "Senior reviewer"
    assert entry.scope == "Substrate v0.1"

    log = load_model(SignoffLog, project / "provenance" / "signoffs.yaml")
    assert log.entries[0].id == entry.id


def test_record_session_requires_attendees(project: Path) -> None:
    with pytest.raises(ValueError, match="at least one attendee"):
        ops.record_session(date(2026, 4, 10), [], root=project)


def test_record_session_with_attendees(project: Path) -> None:
    entry, _ = ops.record_session(
        date(2026, 4, 10),
        ["Alice", "Bob"],
        notes="Kickoff.",
        root=project,
    )
    assert entry.held_at == date(2026, 4, 10)
    assert [a.name for a in entry.attendees] == ["Alice", "Bob"]

    log = load_model(SessionLog, project / "provenance" / "sessions.yaml")
    assert log.entries[0].id == entry.id


def test_add_question(project: Path, git_identity) -> None:
    entry, _ = ops.add_question("Does seasonality apply?", root=project)
    assert entry.raised_by.name == git_identity[0]
    assert entry.disposition == "open"

    log = load_model(QuestionLog, project / "provenance" / "questions.yaml")
    assert log.entries[0].id == entry.id


def test_add_exclusion(project: Path) -> None:
    entry, _ = ops.add_exclusion(
        "No cross-border effects.",
        "Scope of study.",
        root=project,
    )
    log = load_model(ExclusionLog, project / "provenance" / "exclusions.yaml")
    assert log.entries[0].id == entry.id
    assert log.entries[0].rationale == "Scope of study."


def test_add_prediction(project: Path) -> None:
    entry, _ = ops.add_prediction(
        "Demand drops 8%.",
        horizon="6 months",
        root=project,
    )
    assert entry.resolution == "pending"

    log = load_model(PredictionLog, project / "provenance" / "predictions.yaml")
    assert log.entries[0].id == entry.id
    assert log.entries[0].horizon == "6 months"


def test_multiple_entries_accumulate(project: Path) -> None:
    ops.add_assumption("A1", root=project)
    ops.add_assumption("A2", root=project)
    ops.add_assumption("A3", root=project)
    log = load_model(AssumptionLog, project / "provenance" / "assumptions.yaml")
    assert [e.statement for e in log.entries] == ["A1", "A2", "A3"]


def test_each_op_creates_exactly_one_commit(project: Path) -> None:
    before = _commit_count(project)
    ops.add_assumption("A", root=project)
    ops.log_decision("D", "because", root=project)
    ops.record_signoff(role="role", scope="scope", root=project)
    ops.record_session(date(2026, 4, 10), ["A"], root=project)
    ops.add_question("Q?", root=project)
    ops.add_exclusion("X", "reason", root=project)
    ops.add_prediction("P", "horizon", root=project)
    after = _commit_count(project)
    assert after == before + 7
