"""Tests for provenance-generating AI proposals: AssumptionsProposal,
DecisionsProposal, ExclusionsProposal, QuestionsProposal.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.ai.proposals import (
    AssumptionsProposal,
    DecisionEntry,
    DecisionsProposal,
    DraftAssumption,
    ExclusionEntry,
    ExclusionsProposal,
    QuestionEntry,
    QuestionsProposal,
)
from latris.operations import nodes as node_ops
from latris.operations.init import init_project
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model
from latris.schema import AssumptionLog, DecisionLog, ExclusionLog, QuestionLog


@pytest.fixture
def project(tmp_path: Path, git_identity):
    root = tmp_path / "demo"
    init_project(root, statement="Does X cause Y?")
    node, _ = node_ops.add_node("Exposure", kind="variable", root=root)
    return root, node


# ---------- AssumptionsProposal ----------


def test_assumptions_proposal_creates_entries(project):
    root, node = project
    paths = ProjectPaths(root)
    proposal = AssumptionsProposal(
        target_id=node.id,
        assumptions=[
            DraftAssumption(statement="Linear relationship", rationale="Simplification"),
            DraftAssumption(statement="No confounders", rationale="Scoping decision"),
        ],
    )
    created = proposal.apply(paths)
    assert len(created) == 2

    log = load_model(AssumptionLog, paths.assumptions_yaml)
    statements = [a.statement for a in log.entries]
    assert "Linear relationship" in statements
    assert "No confounders" in statements
    # All entries target the same element
    for entry in log.entries:
        assert entry.target_id == node.id


def test_assumptions_proposal_empty_list(project):
    root, node = project
    paths = ProjectPaths(root)
    proposal = AssumptionsProposal(target_id=node.id, assumptions=[])
    created = proposal.apply(paths)
    assert created == []


# ---------- DecisionsProposal ----------


def test_decisions_proposal_creates_entries(project):
    root, node = project
    paths = ProjectPaths(root)
    proposal = DecisionsProposal(
        target_id=node.id,
        decisions=[
            DecisionEntry(
                statement="Chose variable over concept",
                rationale="Need measurable quantity for downstream quantification",
            ),
        ],
    )
    created = proposal.apply(paths)
    assert len(created) == 1

    log = load_model(DecisionLog, paths.decisions_yaml)
    assert len(log.entries) == 1
    assert log.entries[0].statement == "Chose variable over concept"
    assert log.entries[0].target_id == node.id


def test_decisions_proposal_empty_list(project):
    root, node = project
    paths = ProjectPaths(root)
    proposal = DecisionsProposal(target_id=node.id, decisions=[])
    created = proposal.apply(paths)
    assert created == []


# ---------- ExclusionsProposal ----------


def test_exclusions_proposal_creates_entries(project):
    root, node = project
    paths = ProjectPaths(root)
    proposal = ExclusionsProposal(
        exclusions=[
            ExclusionEntry(
                statement="Temporal dynamics not modelled",
                rationale="Scope limited to steady-state",
            ),
            ExclusionEntry(
                statement="Economic feedback loops excluded",
                rationale="Outside research question boundary",
            ),
        ],
    )
    created = proposal.apply(paths)
    assert len(created) == 2

    log = load_model(ExclusionLog, paths.exclusions_yaml)
    statements = [e.statement for e in log.entries]
    assert "Temporal dynamics not modelled" in statements
    assert "Economic feedback loops excluded" in statements


def test_exclusions_proposal_empty_list(project):
    root, _ = project
    paths = ProjectPaths(root)
    proposal = ExclusionsProposal(exclusions=[])
    created = proposal.apply(paths)
    assert created == []


# ---------- QuestionsProposal ----------


def test_questions_proposal_creates_entries(project):
    root, node = project
    paths = ProjectPaths(root)
    proposal = QuestionsProposal(
        target_id=node.id,
        questions=[
            QuestionEntry(question="What is the dose-response curve shape?"),
            QuestionEntry(question="Is there a threshold effect?"),
        ],
    )
    created = proposal.apply(paths)
    assert len(created) == 2

    log = load_model(QuestionLog, paths.questions_yaml)
    questions = [q.question for q in log.entries]
    assert "What is the dose-response curve shape?" in questions
    assert "Is there a threshold effect?" in questions
    for entry in log.entries:
        assert entry.target_id == node.id


def test_questions_proposal_empty_list(project):
    root, node = project
    paths = ProjectPaths(root)
    proposal = QuestionsProposal(target_id=node.id, questions=[])
    created = proposal.apply(paths)
    assert created == []


# ---------- ProvenanceBundle on existing mutations ----------


def test_challenge_with_bundled_provenance(project):
    """ChallengeProposal with provenance bundle creates both challenge + provenance."""
    from latris.ai.proposals import ChallengeProposal, ProvenanceBundle

    root, node = project
    paths = ProjectPaths(root)
    proposal = ChallengeProposal(
        target_id=node.id,
        argument="Exposure might be a mediator, not a root cause",
        provenance=ProvenanceBundle(
            assumptions=[DraftAssumption(statement="Root-cause assumption", rationale="Model treats it as exogenous")],
            questions=[QuestionEntry(question="Is there an upstream driver?")],
        ),
    )
    created = proposal.apply(paths)
    # 1 challenge + 1 assumption + 1 question = 3
    assert len(created) == 3

    log = load_model(AssumptionLog, paths.assumptions_yaml)
    assert any(a.statement == "Root-cause assumption" for a in log.entries)

    qlog = load_model(QuestionLog, paths.questions_yaml)
    assert any(q.question == "Is there an upstream driver?" for q in qlog.entries)


def test_connections_with_bundled_provenance(project):
    """NewConnectionsProposal with provenance bundle creates edges + provenance."""
    from latris.ai.proposals import EdgeProposal, NewConnectionsProposal, ProvenanceBundle

    root, node = project
    paths = ProjectPaths(root)
    # Add a second node so we can create an edge
    b, _ = node_ops.add_node("Outcome", kind="variable", root=root)
    proposal = NewConnectionsProposal(
        proposals=[EdgeProposal(from_id=node.id, to_id=b.id, kind="causal", rationale="test")],
        approved_indices=[0],
        provenance=ProvenanceBundle(
            assumptions=[DraftAssumption(statement="Causal direction assumed", rationale="Temporal ordering")],
        ),
    )
    created = proposal.apply(paths)
    # 1 edge + 1 assumption = 2
    assert len(created) == 2

    log = load_model(AssumptionLog, paths.assumptions_yaml)
    assert any(a.statement == "Causal direction assumed" for a in log.entries)


def test_empty_provenance_bundle_is_backwards_compatible(project):
    """Proposals without provenance field still work (defaults to empty bundle)."""
    from latris.ai.proposals import ChallengeProposal

    root, node = project
    paths = ProjectPaths(root)
    # No provenance argument at all — defaults to empty
    proposal = ChallengeProposal(target_id=node.id, argument="Some argument")
    created = proposal.apply(paths)
    # Only 1 challenge, no provenance entries
    assert len(created) == 1
