from __future__ import annotations

from pathlib import Path

import pytest

from latris.ai import interactions as inter_ops
from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations.init import init_project
from latris.repo import git
from latris.schema import HumanActor


@pytest.fixture
def project(tmp_path: Path, git_identity):
    root = tmp_path / "demo"
    init_project(root, statement="Q?")
    a, _ = node_ops.add_node("A", root=root)
    b, _ = node_ops.add_node("B", root=root)
    edge, _ = edge_ops.add_edge(a.id, b.id, root=root)
    return root, a, b, edge


def test_record_interaction_appends_to_jsonl(project) -> None:
    root, a, _, _ = project
    record, sha = inter_ops.record_interaction(
        prompt_name="ExplainThisElement",
        prompt_inputs={"target_id": a.id},
        model_id="claude-opus-4-6",
        response_summary="Explained the price node.",
        target_ids=[a.id],
        root=root,
    )
    assert record.id.startswith("interaction_")
    assert record.adoption == "pending"
    assert sha is not None

    # JSONL has exactly one line with the right id.
    jsonl = (root / "ai" / "interactions.jsonl").read_text(encoding="utf-8")
    lines = [line for line in jsonl.splitlines() if line]
    assert len(lines) == 1
    assert record.id in lines[0]


def test_record_interaction_creates_commit(project) -> None:
    root, a, *_ = project
    before = int(git.run_git(["rev-list", "--count", "HEAD"], cwd=root).stdout.strip())
    inter_ops.record_interaction(
        prompt_name="ExplainThisElement",
        prompt_inputs={"target_id": a.id},
        model_id="x",
        response_summary="y",
        target_ids=[a.id],
        root=root,
    )
    after = int(git.run_git(["rev-list", "--count", "HEAD"], cwd=root).stdout.strip())
    assert after == before + 1


def test_record_interaction_without_commit(project) -> None:
    root, a, *_ = project
    before = int(git.run_git(["rev-list", "--count", "HEAD"], cwd=root).stdout.strip())
    _, sha = inter_ops.record_interaction(
        prompt_name="ExplainThisElement",
        prompt_inputs={},
        model_id="x",
        response_summary="y",
        target_ids=[a.id],
        commit=False,
        root=root,
    )
    assert sha is None
    after = int(git.run_git(["rev-list", "--count", "HEAD"], cwd=root).stdout.strip())
    assert after == before


def test_list_interactions_filters_by_target(project) -> None:
    root, a, b, edge = project
    inter_ops.record_interaction(
        prompt_name="ExplainThisElement",
        prompt_inputs={},
        model_id="x",
        response_summary="about A",
        target_ids=[a.id],
        root=root,
    )
    inter_ops.record_interaction(
        prompt_name="ChallengeThisConnection",
        prompt_inputs={},
        model_id="x",
        response_summary="about edge",
        target_ids=[edge.id],
        root=root,
    )
    inter_ops.record_interaction(
        prompt_name="ExplainThisElement",
        prompt_inputs={},
        model_id="x",
        response_summary="about B",
        target_ids=[b.id],
        root=root,
    )
    a_only = inter_ops.list_interactions(target_id=a.id, root=root)
    assert len(a_only) == 1
    assert a_only[0].response_summary == "about A"

    edge_only = inter_ops.list_interactions(target_id=edge.id, root=root)
    assert len(edge_only) == 1


def test_list_interactions_newest_first_and_limit(project) -> None:
    root, a, *_ = project
    for i in range(5):
        inter_ops.record_interaction(
            prompt_name="ExplainThisElement",
            prompt_inputs={},
            model_id="x",
            response_summary=f"turn {i}",
            target_ids=[a.id],
            root=root,
        )
    records = inter_ops.list_interactions(limit=3, root=root)
    assert len(records) == 3
    # Newest first
    assert records[0].response_summary == "turn 4"
    assert records[1].response_summary == "turn 3"
    assert records[2].response_summary == "turn 2"


def test_list_interactions_filters_by_adoption(project) -> None:
    root, a, *_ = project
    r1, _ = inter_ops.record_interaction(
        prompt_name="P",
        prompt_inputs={},
        model_id="x",
        response_summary="a",
        target_ids=[a.id],
        root=root,
    )
    r2, _ = inter_ops.record_interaction(
        prompt_name="P",
        prompt_inputs={},
        model_id="x",
        response_summary="b",
        target_ids=[a.id],
        root=root,
    )
    approver = HumanActor(name="Reviewer")
    inter_ops.set_adoption(r1.id, adoption="approved", approved_by=approver, root=root)
    inter_ops.set_adoption(r2.id, adoption="rejected", approved_by=approver, root=root)

    approved = inter_ops.list_interactions(adoption="approved", root=root)
    assert len(approved) == 1 and approved[0].id == r1.id

    rejected = inter_ops.list_interactions(adoption="rejected", root=root)
    assert len(rejected) == 1 and rejected[0].id == r2.id

    pending = inter_ops.list_interactions(adoption="pending", root=root)
    assert pending == []


def test_set_adoption_rewrites_log(project) -> None:
    root, a, *_ = project
    record, _ = inter_ops.record_interaction(
        prompt_name="P",
        prompt_inputs={},
        model_id="x",
        response_summary="s",
        target_ids=[a.id],
        root=root,
    )
    approver = HumanActor(name="Reviewer", email="r@example.com")
    updated, sha = inter_ops.set_adoption(
        record.id,
        adoption="approved",
        approved_by=approver,
        root=root,
    )
    assert updated.adoption == "approved"
    assert updated.approved_by is not None
    assert updated.approved_by.name == "Reviewer"

    # Reading back confirms persistence.
    reloaded = inter_ops.get_interaction(record.id, root=root)
    assert reloaded.adoption == "approved"

    # And a commit was made.
    subject = git.run_git(["log", "-1", "--format=%s"], cwd=root).stdout.strip()
    assert "approved" in subject.lower()


def test_get_interaction_by_prefix(project) -> None:
    root, a, *_ = project
    record, _ = inter_ops.record_interaction(
        prompt_name="P",
        prompt_inputs={},
        model_id="x",
        response_summary="s",
        target_ids=[a.id],
        root=root,
    )
    prefix = record.id[:30]
    fetched = inter_ops.get_interaction(prefix, root=root)
    assert fetched.id == record.id


def test_get_interaction_not_found(project) -> None:
    root, *_ = project
    with pytest.raises(ValueError, match="no interaction matches"):
        inter_ops.get_interaction("interaction_NOPE", root=root)


def test_response_full_roundtrips(project) -> None:
    root, a, *_ = project
    body = "Long multi-paragraph response.\n\nWith newlines and — unicode."
    record, _ = inter_ops.record_interaction(
        prompt_name="P",
        prompt_inputs={},
        model_id="x",
        response_summary="summary only",
        response_full=body,
        target_ids=[a.id],
        root=root,
    )
    fetched = inter_ops.get_interaction(record.id, root=root)
    assert fetched.response_full == body
