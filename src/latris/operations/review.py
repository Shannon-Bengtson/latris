"""Review pack import — parse annotated HTML, map feedback to provenance objects.

The import operation extracts the ReviewManifest from the returned HTML,
creates provenance objects (challenges, questions, signoffs) attributed to
the external reviewer, records a ReviewSession, and commits atomically.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from latris.operations._logs import append_entry as _append
from latris.operations.batch import batch
from latris.operations.commit import auto_commit
from latris.repo import git
from latris.repo.project import require_project
from latris.repo.yaml_io import load_model
from latris.schema import (
    Challenge,
    ChallengeLog,
    HumanActor,
    Question,
    QuestionLog,
    Signoff,
    SignoffLog,
    Substrate,
    new_id,
)
from latris.schema.common import now_utc
from latris.schema.review import (
    ReviewManifest,
    ReviewSession,
    ReviewSessionLog,
)


def _extract_manifest(html: str) -> ReviewManifest:
    """Extract the ReviewManifest JSON from the HTML file."""
    pattern = r'<script\s+type="application/json"\s+id="review-manifest">\s*(.*?)\s*</script>'
    match = re.search(pattern, html, re.DOTALL)
    if not match:
        raise ValueError("No review manifest found in the uploaded HTML")
    return ReviewManifest.model_validate_json(match.group(1))


@dataclass
class ReviewImportResult:
    """Summary of what was imported from a review pack."""

    session: ReviewSession
    commit_sha: str
    version_drift: bool
    items_imported: int
    challenges_created: int = 0
    questions_created: int = 0
    signoffs_created: int = 0
    warnings: list[str] = field(default_factory=list)


def import_review(
    html_content: str,
    *,
    root: Path | None = None,
) -> ReviewImportResult:
    """Parse a returned review HTML and import feedback as provenance objects.

    All feedback items are committed atomically via a single batch commit.
    """
    paths = require_project(root)

    # Extract and validate manifest
    manifest = _extract_manifest(html_content)

    if not manifest.reviewer or not manifest.reviewer.name.strip():
        raise ValueError("Review file has no reviewer name — was it filled in?")

    if not manifest.items:
        raise ValueError("Review file has no feedback items")

    # Build reviewer actor
    reviewer = HumanActor(
        name=manifest.reviewer.name.strip(),
        email=manifest.reviewer.email,
    )

    # Version drift detection
    current_sha = git.head_sha(paths.root)
    version_drift = current_sha != manifest.export_commit_sha

    # Check which target_ids still exist
    substrate = load_model(Substrate, paths.conceptual_yaml)
    existing_ids = {n.id for n in substrate.entities} | {e.id for e in substrate.edges}

    warnings: list[str] = []
    if version_drift:
        warnings.append(
            f"Model has changed since this review was exported "
            f"(exported at {manifest.export_commit_sha[:12]}, "
            f"now at {current_sha[:12]})"
        )

    # Import feedback items inside a batch for atomic commit
    challenges_created = 0
    questions_created = 0
    signoffs_created = 0

    reviewer_name = manifest.reviewer.name.strip()
    item_count = len(manifest.items)

    with batch(
        paths.root,
        subject=f"Imported review feedback from {reviewer_name} ({item_count} items)",
    ):
        now = now_utc()

        for item in manifest.items:
            # Validate target_id still exists
            target_id = item.target_id
            if target_id and target_id not in existing_ids:
                label = manifest.element_ids.get(target_id, target_id[:15])
                warnings.append(f"Element '{label}' no longer exists — feedback moved to project level")
                target_id = None

            if item.feedback_type == "challenge":
                challenge = Challenge(
                    id=new_id("challenge"),
                    target_id=target_id,
                    argument=item.text,
                    state="open",
                    opened_by=reviewer,
                )
                _append(ChallengeLog, paths.challenges_yaml, challenge)
                auto_commit(
                    paths.root,
                    subject=f"Review challenge from {reviewer_name}",
                    paths=[paths.challenges_yaml],
                )
                challenges_created += 1

            elif item.feedback_type == "question":
                question = Question(
                    id=new_id("question"),
                    question=item.text,
                    target_id=target_id,
                    raised_by=reviewer,
                    disposition="open",
                )
                _append(QuestionLog, paths.questions_yaml, question)
                auto_commit(
                    paths.root,
                    subject=f"Review question from {reviewer_name}",
                    paths=[paths.questions_yaml],
                )
                questions_created += 1

            elif item.feedback_type == "signoff":
                scope = f"Review session {manifest.review_session_id[:20]}"
                if manifest.model_type:
                    scope += f" ({manifest.model_type} view)"
                signoff = Signoff(
                    id=new_id("signoff"),
                    reviewer=reviewer,
                    role=manifest.reviewer.role,
                    scope=scope,
                    target_id=target_id,
                    signed_at=now,
                    notes=item.text,
                )
                _append(SignoffLog, paths.signoffs_yaml, signoff)
                auto_commit(
                    paths.root,
                    subject=f"Review signoff from {reviewer_name}",
                    paths=[paths.signoffs_yaml],
                )
                signoffs_created += 1

        # Record the review session
        session = ReviewSession(
            id=manifest.review_session_id,
            export_commit_sha=manifest.export_commit_sha,
            import_commit_sha=current_sha,
            exported_at=manifest.exported_at,
            imported_at=now,
            exported_by=manifest.exported_by,
            reviewer=manifest.reviewer,
            pack=manifest.pack,
            model_type=manifest.model_type,
            sections=manifest.sections,
            item_count=item_count,
            phase="imported",
        )
        _append(ReviewSessionLog, paths.review_sessions_yaml, session)
        auto_commit(
            paths.root,
            subject="Recorded review session",
            paths=[paths.review_sessions_yaml],
        )

    # The batch committed — get the actual SHA
    commit_sha = git.head_sha(paths.root)

    return ReviewImportResult(
        session=session,
        commit_sha=commit_sha,
        version_drift=version_drift,
        items_imported=item_count,
        challenges_created=challenges_created,
        questions_created=questions_created,
        signoffs_created=signoffs_created,
        warnings=warnings,
    )
