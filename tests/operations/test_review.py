"""Tests for the review pack import operation."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from latris.exporters import review_html
from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations.init import init_project
from latris.operations.review import import_review
from latris.repo import git
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model
from latris.schema import (
    ChallengeLog,
    HumanActor,
    QuestionLog,
    SignoffLog,
)
from latris.schema.review import (
    ReviewerInfo,
    ReviewFeedbackItem,
    ReviewManifest,
    ReviewSessionLog,
)

FIXED_DT = datetime(2026, 5, 4, 12, 0, 0, tzinfo=UTC)
ALICE = HumanActor(name="Alice Example", email="alice@example.com")


def _build_review_html(
    manifest: ReviewManifest,
) -> str:
    """Build a minimal valid HTML string with embedded manifest."""
    manifest_json = manifest.model_dump_json(indent=2)
    return f"""\
<!DOCTYPE html>
<html><head><title>Test Review</title></head>
<body>
<script type="application/json" id="review-manifest">
{manifest_json}
</script>
</body></html>"""


@pytest.fixture
def project(tmp_path: Path, git_identity, monkeypatch):
    root = tmp_path / "demo"
    init_project(root, statement="Does X cause Y?")
    monkeypatch.chdir(root)
    return root


@pytest.fixture
def project_with_nodes(project):
    a, _ = node_ops.add_node("Price", kind="variable", root=project)
    b, _ = node_ops.add_node("Demand", kind="variable", root=project)
    edge_ops.add_edge(a.id, b.id, kind="causal", root=project)
    return project, a.id, b.id


class TestImportReview:
    def test_creates_challenge(self, project_with_nodes):
        root, node_a, node_b = project_with_nodes
        sha = git.head_sha(root)

        manifest = ReviewManifest(
            review_session_id="review-session_01EXAMPLE0000000000000000",
            project_name="demo",
            export_commit_sha=sha,
            exported_at=FIXED_DT,
            exported_by=ALICE,
            pack="review",
            sections=["nodes"],
            reviewer=ReviewerInfo(name="Bob", role="Expert"),
            items=[
                ReviewFeedbackItem(
                    target_id=node_a,
                    feedback_type="challenge",
                    text="I disagree with this node.",
                ),
            ],
            completed_at=FIXED_DT,
        )

        result = import_review(_build_review_html(manifest), root=root)
        assert result.challenges_created == 1
        assert result.questions_created == 0
        assert result.signoffs_created == 0

        # Verify the challenge was written
        paths = ProjectPaths(root)
        challenges = load_model(ChallengeLog, paths.challenges_yaml)
        assert len(challenges.entries) == 1
        c = challenges.entries[0]
        assert c.argument == "I disagree with this node."
        assert c.target_id == node_a
        assert c.opened_by.name == "Bob"
        assert c.state == "open"

    def test_creates_question(self, project_with_nodes):
        root, node_a, _ = project_with_nodes
        sha = git.head_sha(root)

        manifest = ReviewManifest(
            review_session_id="review-session_01EXAMPLE0000000000000001",
            project_name="demo",
            export_commit_sha=sha,
            exported_at=FIXED_DT,
            exported_by=ALICE,
            pack="review",
            sections=[],
            reviewer=ReviewerInfo(name="Carol"),
            items=[
                ReviewFeedbackItem(
                    feedback_type="question",
                    text="What about seasonality?",
                ),
            ],
            completed_at=FIXED_DT,
        )

        result = import_review(_build_review_html(manifest), root=root)
        assert result.questions_created == 1

        paths = ProjectPaths(root)
        questions = load_model(QuestionLog, paths.questions_yaml)
        matching = [q for q in questions.entries if q.question == "What about seasonality?"]
        assert len(matching) == 1
        assert matching[0].raised_by.name == "Carol"

    def test_creates_signoff(self, project_with_nodes):
        root, _, _ = project_with_nodes
        sha = git.head_sha(root)

        manifest = ReviewManifest(
            review_session_id="review-session_01EXAMPLE0000000000000002",
            project_name="demo",
            export_commit_sha=sha,
            exported_at=FIXED_DT,
            exported_by=ALICE,
            pack="review",
            sections=[],
            reviewer=ReviewerInfo(name="Dan", role="Auditor"),
            items=[
                ReviewFeedbackItem(
                    feedback_type="signoff",
                    text="Approved after review.",
                ),
            ],
            completed_at=FIXED_DT,
        )

        result = import_review(_build_review_html(manifest), root=root)
        assert result.signoffs_created == 1

        paths = ProjectPaths(root)
        signoffs = load_model(SignoffLog, paths.signoffs_yaml)
        matching = [s for s in signoffs.entries if s.notes == "Approved after review."]
        assert len(matching) == 1
        assert matching[0].reviewer.name == "Dan"
        assert matching[0].role == "Auditor"

    def test_multiple_items_atomic_commit(self, project_with_nodes):
        root, node_a, node_b = project_with_nodes
        sha_before = git.head_sha(root)

        manifest = ReviewManifest(
            review_session_id="review-session_01EXAMPLE0000000000000003",
            project_name="demo",
            export_commit_sha=sha_before,
            exported_at=FIXED_DT,
            exported_by=ALICE,
            pack="review",
            sections=[],
            reviewer=ReviewerInfo(name="Eve"),
            items=[
                ReviewFeedbackItem(target_id=node_a, feedback_type="challenge", text="Wrong"),
                ReviewFeedbackItem(feedback_type="question", text="Why?"),
                ReviewFeedbackItem(feedback_type="signoff", text="OK overall"),
            ],
            completed_at=FIXED_DT,
        )

        result = import_review(_build_review_html(manifest), root=root)
        assert result.items_imported == 3
        assert result.challenges_created == 1
        assert result.questions_created == 1
        assert result.signoffs_created == 1

        # Should be exactly 1 commit from the batch
        sha_after = git.head_sha(root)
        assert sha_after != sha_before
        # Verify only one new commit (batch)
        log_output = git.run_git(
            ["log", "--oneline", f"{sha_before}..{sha_after}"],
            cwd=root,
        ).stdout.strip()
        commits = [line for line in log_output.split("\n") if line.strip()]
        assert len(commits) == 1
        assert "Eve" in commits[0]

    def test_creates_review_session(self, project_with_nodes):
        root, _, _ = project_with_nodes
        sha = git.head_sha(root)

        manifest = ReviewManifest(
            review_session_id="review-session_01EXAMPLE0000000000000004",
            project_name="demo",
            export_commit_sha=sha,
            exported_at=FIXED_DT,
            exported_by=ALICE,
            pack="review",
            sections=["nodes"],
            reviewer=ReviewerInfo(name="Frank"),
            items=[
                ReviewFeedbackItem(feedback_type="question", text="Really?"),
            ],
            completed_at=FIXED_DT,
        )

        import_review(_build_review_html(manifest), root=root)

        paths = ProjectPaths(root)
        sessions = load_model(ReviewSessionLog, paths.review_sessions_yaml)
        assert len(sessions.entries) == 1
        s = sessions.entries[0]
        assert s.phase == "imported"
        assert s.reviewer.name == "Frank"
        assert s.item_count == 1

    def test_version_drift_detected(self, project_with_nodes):
        root, _, _ = project_with_nodes
        old_sha = git.head_sha(root)

        # Make a change to advance HEAD
        node_ops.add_node("Supply", kind="variable", root=root)
        new_sha = git.head_sha(root)
        assert old_sha != new_sha

        manifest = ReviewManifest(
            review_session_id="review-session_01EXAMPLE0000000000000005",
            project_name="demo",
            export_commit_sha=old_sha,
            exported_at=FIXED_DT,
            exported_by=ALICE,
            pack="review",
            sections=[],
            reviewer=ReviewerInfo(name="Grace"),
            items=[
                ReviewFeedbackItem(feedback_type="signoff", text="OK"),
            ],
            completed_at=FIXED_DT,
        )

        result = import_review(_build_review_html(manifest), root=root)
        assert result.version_drift is True
        assert any("changed" in w.lower() for w in result.warnings)

    def test_deleted_target_becomes_project_level(self, project):
        """Feedback targeting a deleted element is moved to project level."""
        root = project
        node_ops.add_node("TempNode", kind="variable", root=root)
        sha = git.head_sha(root)

        # Remove the node (by adding another and simulating removal isn't easy,
        # so just use a non-existent ID)
        fake_id = "node_00000000000000000000000000"

        manifest = ReviewManifest(
            review_session_id="review-session_01EXAMPLE0000000000000006",
            project_name="demo",
            export_commit_sha=sha,
            exported_at=FIXED_DT,
            exported_by=ALICE,
            pack="review",
            sections=[],
            element_ids={fake_id: "DeletedNode"},
            reviewer=ReviewerInfo(name="Hank"),
            items=[
                ReviewFeedbackItem(
                    target_id=fake_id,
                    feedback_type="challenge",
                    text="This node is wrong.",
                ),
            ],
            completed_at=FIXED_DT,
        )

        result = import_review(_build_review_html(manifest), root=root)
        assert result.challenges_created == 1
        assert any("no longer exists" in w for w in result.warnings)

        # Challenge should be project-level (target_id=None)
        paths = ProjectPaths(root)
        challenges = load_model(ChallengeLog, paths.challenges_yaml)
        assert challenges.entries[-1].target_id is None


class TestImportValidation:
    def test_rejects_missing_reviewer(self, project):
        manifest = ReviewManifest(
            review_session_id="review-session_01EXAMPLE0000000000000007",
            project_name="demo",
            export_commit_sha="abc",
            exported_at=FIXED_DT,
            exported_by=ALICE,
            pack="review",
            sections=[],
            items=[
                ReviewFeedbackItem(feedback_type="question", text="Test"),
            ],
        )
        with pytest.raises(ValueError, match="no reviewer name"):
            import_review(_build_review_html(manifest), root=project)

    def test_rejects_empty_items(self, project):
        manifest = ReviewManifest(
            review_session_id="review-session_01EXAMPLE0000000000000008",
            project_name="demo",
            export_commit_sha="abc",
            exported_at=FIXED_DT,
            exported_by=ALICE,
            pack="review",
            sections=[],
            reviewer=ReviewerInfo(name="Ivan"),
            items=[],
        )
        with pytest.raises(ValueError, match="no feedback items"):
            import_review(_build_review_html(manifest), root=project)

    def test_rejects_invalid_html(self, project):
        with pytest.raises(ValueError, match="No review manifest"):
            import_review("<html><body>Not a review</body></html>", root=project)


class TestRoundTrip:
    def test_export_then_import(self, project_with_nodes):
        """Full round-trip: export HTML, inject feedback, import."""
        root, node_a, _ = project_with_nodes
        paths = ProjectPaths(root)

        # Export
        html = review_html.render(paths)

        # Simulate reviewer filling in feedback by modifying the manifest
        pattern = r'<script\s+type="application/json"\s+id="review-manifest">\s*(.*?)\s*</script>'
        match = re.search(pattern, html, re.DOTALL)
        assert match
        manifest_data = json.loads(match.group(1))

        # Add reviewer info and feedback
        manifest_data["reviewer"] = {"name": "Test Reviewer", "role": "Expert"}
        manifest_data["items"] = [
            {"target_id": node_a, "feedback_type": "challenge", "text": "Needs justification"},
            {"feedback_type": "question", "text": "What scope?"},
        ]
        manifest_data["completed_at"] = "2026-05-04T12:00:00Z"

        # Replace the manifest in the HTML
        updated_json = json.dumps(manifest_data, indent=2)
        updated_html = re.sub(
            pattern,
            f'<script type="application/json" id="review-manifest">\n{updated_json}\n</script>',
            html,
            flags=re.DOTALL,
        )

        # Import
        result = import_review(updated_html, root=root)
        assert result.items_imported == 2
        assert result.challenges_created == 1
        assert result.questions_created == 1
        assert not result.version_drift
