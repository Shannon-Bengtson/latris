"""Per-formalism scoping of the review pack (export + import)."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from latris.exporters import review_html
from latris.operations import edges as edge_ops
from latris.operations import findings as finding_ops
from latris.operations import mappings as mapping_ops
from latris.operations import nodes as node_ops
from latris.operations.init import init_project
from latris.operations.review import import_review
from latris.repo import git
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model
from latris.schema import HumanActor, SignoffLog
from latris.schema.review import (
    ReviewerInfo,
    ReviewFeedbackItem,
    ReviewManifest,
    ReviewSessionLog,
)

FIXED_DT = datetime(2026, 6, 27, 12, 0, 0, tzinfo=UTC)
ALICE = HumanActor(name="Alice Example", email="alice@example.com")


@pytest.fixture
def two_formalism_project(tmp_path: Path, git_identity, monkeypatch):
    root = tmp_path / "demo"
    init_project(root, statement="Does X cause Y?")
    cld_a, _ = node_ops.add_node("Nutrients", kind="variable", root=root)
    cld_b, _ = node_ops.add_node("Algae", kind="variable", root=root)
    dag_c, _ = node_ops.add_node("Rainfall", kind="variable", root=root)
    e_cld, _ = edge_ops.add_edge(cld_a.id, cld_b.id, kind="causal", root=root)
    mapping_ops.map_to_view(cld_a.id, "cld", root=root)
    mapping_ops.map_to_view(cld_b.id, "cld", root=root)
    mapping_ops.map_to_view(e_cld.id, "cld", root=root)
    mapping_ops.map_to_view(dag_c.id, "dag", root=root)
    finding_ops.record_new_finding("Nutrients drive algae blooms", "structure", "cld", root=root)
    finding_ops.record_new_finding("Rainfall is exogenous", "structure", "dag", root=root)
    monkeypatch.chdir(root)
    return root, cld_a, cld_b, dag_c


def test_export_scopes_to_formalism_and_stamps_manifest(two_formalism_project):
    root, cld_a, cld_b, dag_c = two_formalism_project
    html = review_html.render(ProjectPaths(root), pack="review", model_type="cld")
    assert "Nutrients" in html
    assert "Algae" in html
    assert "Rainfall" not in html  # dag-only node excluded
    assert "Nutrients drive algae blooms" in html
    assert "Rainfall is exogenous" not in html

    # Manifest records the formalism.
    m = re.search(r'<script type="application/json" id="review-manifest">\s*(\{.*?\})\s*</script>', html, re.DOTALL)
    assert m
    manifest = json.loads(m.group(1))
    assert manifest["model_type"] == "cld"


def _build_html(manifest: ReviewManifest) -> str:
    return (
        '<!DOCTYPE html><html><body>'
        '<script type="application/json" id="review-manifest">\n'
        f"{manifest.model_dump_json(indent=2)}\n"
        "</script></body></html>"
    )


def test_import_records_model_type_on_session_and_signoff(two_formalism_project):
    root, cld_a, _cld_b, _dag_c = two_formalism_project
    sha = git.head_sha(root)
    manifest = ReviewManifest(
        review_session_id="review-session_01EXAMPLE0000000000000000",
        project_name="demo",
        export_commit_sha=sha,
        exported_at=FIXED_DT,
        exported_by=ALICE,
        pack="review",
        model_type="cld",
        sections=["nodes"],
        reviewer=ReviewerInfo(name="Bob", role="Expert"),
        items=[
            ReviewFeedbackItem(target_id=cld_a.id, feedback_type="signoff", text="Looks right."),
        ],
        completed_at=FIXED_DT,
    )
    result = import_review(_build_html(manifest), root=root)
    assert result.session.model_type == "cld"

    sessions = load_model(ReviewSessionLog, ProjectPaths(root).review_sessions_yaml).entries
    assert sessions[-1].model_type == "cld"

    signoffs = load_model(SignoffLog, ProjectPaths(root).signoffs_yaml).entries
    assert any("cld view" in s.scope for s in signoffs)
