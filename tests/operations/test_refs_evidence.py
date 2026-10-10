from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import edges as edge_ops
from latris.operations import evidence as evidence_ops
from latris.operations import nodes as node_ops
from latris.operations import references as ref_ops
from latris.operations.init import init_project


@pytest.fixture
def project_with_edge(tmp_path: Path, git_identity):
    root = tmp_path / "demo"
    init_project(root, statement="Q?")
    a, _ = node_ops.add_node("Price", root=root)
    b, _ = node_ops.add_node("Demand", root=root)
    edge, _ = edge_ops.add_edge(a.id, b.id, root=root)
    return root, a, b, edge


def test_add_and_list_reference(project_with_edge) -> None:
    root, *_ = project_with_edge
    ref, _ = ref_ops.add_reference(
        "smith2023",
        title="Pricing studies",
        authors=["Smith, J."],
        year=2023,
        doi="10.1000/x",
        root=root,
    )
    assert ref.bibkey == "smith2023"
    listed = ref_ops.list_references(root)
    assert [r.bibkey for r in listed] == ["smith2023"]


def test_add_reference_refuses_duplicate(project_with_edge) -> None:
    root, *_ = project_with_edge
    ref_ops.add_reference("smith2023", title="A", root=root)
    with pytest.raises(ValueError, match="already exists"):
        ref_ops.add_reference("smith2023", title="B", root=root)


def test_add_evidence_requires_known_reference(project_with_edge) -> None:
    root, _, _, edge = project_with_edge
    with pytest.raises(ValueError, match="unknown reference"):
        evidence_ops.add_evidence(edge.id, "polarity", "smith2023", root=root)


def test_add_evidence_attaches_and_commits(project_with_edge) -> None:
    root, _, _, edge = project_with_edge
    ref_ops.add_reference("smith2023", title="Pricing studies", root=root)
    link, _ = evidence_ops.add_evidence(
        edge.id,
        "polarity",
        "smith2023",
        verified_by="human",
        root=root,
    )
    assert link.target_id == edge.id
    assert link.attribute == "polarity"
    assert link.bibkey == "smith2023"
    # Phase 1 audit axes: human proposer, but no source-access or
    # claim-level verification claimed at attach time. Promotion
    # happens via Phase 2 (source snapshots) and Phase 4 (verbatim
    # quote validation), not at the original add_evidence call.
    assert link.verified_by == "human"
    assert link.source_access == "title_only"
    assert link.support_verdict == "unverified"
    assert link.quote is None
    assert link.quote_location is None


def test_add_evidence_refuses_duplicate(project_with_edge) -> None:
    root, _, _, edge = project_with_edge
    ref_ops.add_reference("smith2023", title="X", root=root)
    evidence_ops.add_evidence(edge.id, "polarity", "smith2023", root=root)
    with pytest.raises(ValueError, match="already attached"):
        evidence_ops.add_evidence(edge.id, "polarity", "smith2023", root=root)


def test_evidence_works_on_node_and_by_label(project_with_edge) -> None:
    root, a, _, _ = project_with_edge
    ref_ops.add_reference("doe2024", title="Y", root=root)
    link, _ = evidence_ops.add_evidence("Price", "description", "doe2024", root=root)
    assert link.target_id == a.id


# ── Phase 3a: support_verdict mutator + remove evidence ──────────────


def test_set_support_verdict_changes_state_and_commits(project_with_edge) -> None:
    """EvidenceDemote backend: a verdict change mutates the link,
    appends rationale to notes, and writes a Demoted commit."""
    from latris.repo import git

    root, _, _, edge = project_with_edge
    ref_ops.add_reference("smith2023", title="Pricing studies", root=root)
    evidence_ops.add_evidence(edge.id, "polarity", "smith2023", root=root)

    updated, _ = evidence_ops.set_evidence_support_verdict(
        edge.id,
        "polarity",
        "smith2023",
        new_verdict="orthogonal",
        rationale="paper discusses elasticity, not the polarity claim",
        root=root,
    )
    assert updated.support_verdict == "orthogonal"
    assert updated.notes is not None
    assert "verdict unverified → orthogonal" in updated.notes

    body = git.run_git(["log", "-1", "--format=%B"], cwd=root).stdout
    assert "Demoted evidence" in body
    assert "rationale: paper discusses elasticity" in body


def test_set_support_verdict_rejects_noop(project_with_edge) -> None:
    root, _, _, edge = project_with_edge
    ref_ops.add_reference("smith2023", title="X", root=root)
    evidence_ops.add_evidence(edge.id, "polarity", "smith2023", root=root)

    with pytest.raises(ValueError, match="already has support_verdict"):
        evidence_ops.set_evidence_support_verdict(
            edge.id,
            "polarity",
            "smith2023",
            new_verdict="unverified",  # already unverified — no-op
            rationale="...",
            root=root,
        )


def test_set_support_verdict_rejects_missing_link(project_with_edge) -> None:
    root, _, _, edge = project_with_edge
    ref_ops.add_reference("smith2023", title="X", root=root)
    # No add_evidence — link does not exist.
    with pytest.raises(ValueError, match="no evidence link"):
        evidence_ops.set_evidence_support_verdict(
            edge.id,
            "polarity",
            "smith2023",
            new_verdict="orthogonal",
            rationale="...",
            root=root,
        )


def test_remove_evidence_records_rationale(project_with_edge) -> None:
    from latris.repo import git

    root, _, _, edge = project_with_edge
    ref_ops.add_reference("smith2023", title="X", root=root)
    evidence_ops.add_evidence(edge.id, "polarity", "smith2023", root=root)

    evidence_ops.remove_evidence(
        edge.id,
        "polarity",
        "smith2023",
        rationale="topic-overlap only, not load-bearing",
        root=root,
    )
    body = git.run_git(["log", "-1", "--format=%B"], cwd=root).stdout
    assert "Detached evidence" in body
    assert "rationale: topic-overlap only" in body
