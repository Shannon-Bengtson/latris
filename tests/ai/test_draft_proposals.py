"""Tests for M12 AI proposal models: DraftModelProposal, NewConnectionsProposal,
AttackResult, ScopeCheckResult.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.ai.proposals import (
    AttackResult,
    CounterPathwayResult,
    DraftEdge,
    DraftEntity,
    DraftFraming,
    DraftModelProposal,
    EdgeProposal,
    NewConnectionsProposal,
    ScopeCheckResult,
)
from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations.init import init_project
from latris.repo.layout import ProjectPaths


@pytest.fixture
def project(tmp_path: Path, git_identity):
    root = tmp_path / "demo"
    init_project(root, statement="Does X cause Y?")
    a, _ = node_ops.add_node("Price", kind="variable", root=root)
    b, _ = node_ops.add_node("Demand", kind="variable", root=root)
    return root, a, b


# ---------- DraftModelProposal ----------


def test_draft_apply_creates_nodes_and_edges(project):
    root, _, _ = project
    paths = ProjectPaths(root)
    proposal = DraftModelProposal(
        framings=[
            DraftFraming(
                name="Framing A",
                entities=[
                    DraftEntity(label="Supply", kind="variable"),
                    DraftEntity(label="Cost", kind="variable"),
                ],
                edges=[
                    DraftEdge(from_label="Cost", to_label="Supply", kind="causal"),
                ],
                rationale="Supply-side model.",
            ),
            DraftFraming(
                name="Framing B",
                entities=[DraftEntity(label="Revenue", kind="variable")],
                edges=[],
                rationale="Revenue model.",
            ),
        ],
        selected_index=0,
    )
    created = proposal.apply(paths)
    # 2 new nodes + 1 edge
    assert len(created) == 3

    nodes = node_ops.list_nodes(root)
    labels = {n.label for n in nodes}
    assert "Supply" in labels
    assert "Cost" in labels

    edges = edge_ops.list_edges(root)
    # Original edge + new edge
    assert len(edges) == 1  # no original edge was created in project fixture


def test_draft_apply_skips_duplicate_labels(project):
    root, _, _ = project
    paths = ProjectPaths(root)
    proposal = DraftModelProposal(
        framings=[
            DraftFraming(
                name="Overlap",
                entities=[
                    DraftEntity(label="Price", kind="variable"),  # already exists
                    DraftEntity(label="New", kind="concept"),
                ],
                edges=[],
            ),
        ],
        selected_index=0,
    )
    created = proposal.apply(paths)
    # Only "New" is created; "Price" already exists
    assert len(created) == 1
    nodes = node_ops.list_nodes(root)
    labels = [n.label for n in nodes]
    assert labels.count("Price") == 1


def test_draft_apply_without_selected_index_raises(project):
    root, _, _ = project
    paths = ProjectPaths(root)
    proposal = DraftModelProposal(
        framings=[DraftFraming(name="A", entities=[], edges=[])],
        selected_index=None,
    )
    with pytest.raises(ValueError, match="No framing selected"):
        proposal.apply(paths)


def test_draft_apply_out_of_range_index_raises(project):
    root, _, _ = project
    paths = ProjectPaths(root)
    proposal = DraftModelProposal(
        framings=[DraftFraming(name="A", entities=[], edges=[])],
        selected_index=5,
    )
    with pytest.raises(ValueError, match="out of range"):
        proposal.apply(paths)


# ---------- NewConnectionsProposal ----------


def test_new_connections_apply_creates_approved_edges(project):
    root, a, b = project
    paths = ProjectPaths(root)
    proposal = NewConnectionsProposal(
        proposals=[
            EdgeProposal(from_id=a.id, to_id=b.id, kind="causal", rationale="Price drives demand."),
            EdgeProposal(from_id=b.id, to_id=a.id, kind="causal", rationale="Demand feeds back."),
        ],
        approved_indices=[0],  # only approve the first
    )
    created = proposal.apply(paths)
    assert len(created) == 1
    edges = edge_ops.list_edges(root)
    assert len(edges) == 1


def test_new_connections_apply_without_approved_raises(project):
    root, a, b = project
    paths = ProjectPaths(root)
    proposal = NewConnectionsProposal(
        proposals=[EdgeProposal(from_id=a.id, to_id=b.id, kind="causal")],
        approved_indices=None,
    )
    with pytest.raises(ValueError, match="No proposals approved"):
        proposal.apply(paths)


# ---------- Hybrid results (prose + bounded mutation) ----------


def test_attack_result_apply_is_bounded(tmp_path, git_identity):
    """AttackResult.apply() records at most 1 assumption + 1 question.
    With record_assumption=False and no follow-up, apply() is a no-op."""
    from latris.operations.init import init_project
    from latris.repo.layout import ProjectPaths

    root = tmp_path / "demo"
    init_project(root, statement="Q?")
    paths = ProjectPaths(root)

    # Default: records assumption + (no question because none provided).
    result = AttackResult(
        weakest_assumption="Market is liquid",
        argument="Evidence from 2008 crisis suggests this breaks.",
        affected_node_ids=[],
    )
    ids = result.apply(paths)
    assert len(ids) == 1  # one assumption, no question

    # No mutation when record_assumption is False and no follow-up question.
    result2 = AttackResult(
        weakest_assumption="X",
        argument="Y",
        affected_node_ids=[],
        record_assumption=False,
    )
    ids2 = result2.apply(paths)
    assert ids2 == []


def test_counter_pathway_apply_logs_one_question_by_default(tmp_path, git_identity):
    """CounterPathwayResult.apply() logs exactly one Open Question naming
    the missing mechanism, when record_question=True. No nodes/edges are
    auto-created — those would be too risky without human review."""
    from latris.operations.init import init_project
    from latris.repo.layout import ProjectPaths
    from latris.repo.yaml_io import load_model
    from latris.schema import QuestionLog

    root = tmp_path / "counter_default"
    init_project(root, statement="Q?")
    paths = ProjectPaths(root)

    result = CounterPathwayResult(
        missing_mechanism="Workload intensification",
        argument="Compressed weeks raise intensity, eroding the productivity gain.",
        supporting_bibkey="delaney2018productivity",
    )
    ids = result.apply(paths)
    assert len(ids) == 1

    log = load_model(QuestionLog, paths.questions_yaml)
    assert len(log.entries) == 1
    text = log.entries[0].question
    assert "Workload intensification" in text
    assert "Compressed weeks" in text


def test_counter_pathway_apply_skips_when_disabled(tmp_path, git_identity):
    """record_question=False → no Open Question logged. apply() returns []."""
    from latris.operations.init import init_project
    from latris.repo.layout import ProjectPaths
    from latris.repo.yaml_io import load_model
    from latris.schema import QuestionLog

    root = tmp_path / "counter_silenced"
    init_project(root, statement="Q?")
    paths = ProjectPaths(root)

    result = CounterPathwayResult(
        missing_mechanism="Speculative pathway",
        argument="Probably not worth tracking.",
        record_question=False,
    )
    assert result.apply(paths) == []

    log = load_model(QuestionLog, paths.questions_yaml)
    assert log.entries == []


def test_scope_check_result_apply_records_proposed_entries(tmp_path, git_identity):
    """ScopeCheckResult.apply() commits proposed_exclusions and
    proposed_questions, leaving prose-only fields untouched."""
    from latris.ai.proposals import ExclusionEntry, QuestionEntry
    from latris.operations.init import init_project
    from latris.repo.layout import ProjectPaths

    root = tmp_path / "demo"
    init_project(root, statement="Q?")
    paths = ProjectPaths(root)

    # Empty proposals → no mutation (well-matched verdict case).
    result = ScopeCheckResult(
        verdict="well-matched",
        suggestions=[],
        reasoning="Model is well-scoped.",
    )
    assert result.apply(paths) == []

    # Populated proposals → entries created.
    result2 = ScopeCheckResult(
        verdict="too-broad",
        proposed_exclusions=[
            ExclusionEntry(statement="Macro effects", rationale="Out of scope."),
        ],
        proposed_questions=[
            QuestionEntry(question="Should supply-side enter scope?"),
        ],
    )
    ids = result2.apply(paths)
    assert len(ids) == 2
