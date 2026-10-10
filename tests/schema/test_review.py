"""Round-trip and validation tests for the review pack schema."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from latris.repo.yaml_io import dump_model, load_model
from latris.schema.common import HumanActor
from latris.schema.ids import new_id
from latris.schema.review import (
    ReviewerInfo,
    ReviewFeedbackItem,
    ReviewManifest,
    ReviewSession,
    ReviewSessionLog,
)

FIXED_DT = datetime(2026, 5, 4, 12, 0, 0, tzinfo=UTC)
ALICE = HumanActor(name="Alice Example", email="alice@example.com")


class TestReviewerInfo:
    def test_defaults(self):
        info = ReviewerInfo(name="Bob")
        assert info.role == "Reviewer"
        assert info.email is None

    def test_full(self):
        info = ReviewerInfo(name="Bob", email="bob@example.com", role="Domain Expert")
        assert info.role == "Domain Expert"


class TestReviewFeedbackItem:
    def test_challenge(self):
        item = ReviewFeedbackItem(
            target_id="node_01ARZ3NDEKTSV4RRFFQ69G5FAV",
            feedback_type="challenge",
            text="This edge direction seems wrong.",
        )
        assert item.feedback_type == "challenge"
        assert item.target_id is not None

    def test_project_level(self):
        item = ReviewFeedbackItem(
            feedback_type="question",
            text="What is the time horizon for this model?",
        )
        assert item.target_id is None

    def test_signoff(self):
        item = ReviewFeedbackItem(
            feedback_type="signoff",
            text="Looks good to me.",
        )
        assert item.feedback_type == "signoff"

    def test_invalid_type_rejected(self):
        with pytest.raises(ValidationError):
            ReviewFeedbackItem(
                feedback_type="comment",  # type: ignore[arg-type]
                text="hello",
            )


class TestReviewManifest:
    def test_empty_at_export(self):
        m = ReviewManifest(
            review_session_id=new_id("review-session"),
            project_name="demo",
            export_commit_sha="abc123def456",
            exported_at=FIXED_DT,
            exported_by=ALICE,
            pack="review",
            sections=["foundation", "nodes", "edges"],
        )
        assert m.reviewer is None
        assert m.items == []
        assert m.completed_at is None

    def test_filled_after_review(self):
        m = ReviewManifest(
            review_session_id=new_id("review-session"),
            project_name="demo",
            export_commit_sha="abc123def456",
            exported_at=FIXED_DT,
            exported_by=ALICE,
            pack="review",
            sections=["foundation", "nodes"],
            reviewer=ReviewerInfo(name="Bob", role="Auditor"),
            items=[
                ReviewFeedbackItem(feedback_type="challenge", text="Disagree"),
                ReviewFeedbackItem(feedback_type="signoff", text="LGTM"),
            ],
            completed_at=FIXED_DT,
        )
        assert m.reviewer is not None
        assert len(m.items) == 2

    def test_element_ids(self):
        m = ReviewManifest(
            review_session_id=new_id("review-session"),
            project_name="demo",
            export_commit_sha="abc",
            exported_by=ALICE,
            pack="review",
            sections=[],
            element_ids={"node_01": "Price", "node_02": "Demand"},
        )
        assert m.element_ids["node_01"] == "Price"


class TestReviewSession:
    def test_defaults(self):
        s = ReviewSession(
            id=new_id("review-session"),
            export_commit_sha="abc123",
            exported_by=ALICE,
            pack="review",
            sections=["foundation", "nodes"],
        )
        assert s.phase == "exported"
        assert s.import_commit_sha is None
        assert s.imported_at is None
        assert s.item_count == 0

    def test_id_prefix(self):
        s = ReviewSession(
            id=new_id("review-session"),
            export_commit_sha="abc123",
            exported_by=ALICE,
            pack="review",
            sections=[],
        )
        assert s.id.startswith("review-session_")


class TestReviewSessionLog:
    def test_empty(self):
        log = ReviewSessionLog()
        assert log.entries == []

    def test_round_trip(self, tmp_path):
        path = tmp_path / "review-sessions.yaml"
        session = ReviewSession(
            id=new_id("review-session"),
            export_commit_sha="abc123",
            exported_at=FIXED_DT,
            exported_by=ALICE,
            pack="review",
            sections=["foundation", "nodes", "edges"],
            item_count=3,
        )
        log = ReviewSessionLog(entries=[session])
        dump_model(log, path)
        loaded = load_model(ReviewSessionLog, path)
        assert len(loaded.entries) == 1
        assert loaded.entries[0].id == session.id
        assert loaded.entries[0].export_commit_sha == "abc123"
        assert loaded.entries[0].pack == "review"

    def test_round_trip_with_reviewer(self, tmp_path):
        path = tmp_path / "review-sessions.yaml"
        session = ReviewSession(
            id=new_id("review-session"),
            export_commit_sha="abc",
            exported_at=FIXED_DT,
            imported_at=FIXED_DT,
            exported_by=ALICE,
            reviewer=ReviewerInfo(name="Bob", email="bob@x.com", role="Expert"),
            pack="audit",
            sections=["foundation"],
            item_count=5,
            phase="imported",
            import_commit_sha="def456",
        )
        log = ReviewSessionLog(entries=[session])
        dump_model(log, path)
        loaded = load_model(ReviewSessionLog, path)
        entry = loaded.entries[0]
        assert entry.phase == "imported"
        assert entry.reviewer is not None
        assert entry.reviewer.name == "Bob"
        assert entry.import_commit_sha == "def456"
