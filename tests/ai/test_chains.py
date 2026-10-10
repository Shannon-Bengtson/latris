"""Tests for prompt chain definitions and chain runner."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.ai.chains import CHAIN_LIBRARY, get_chain, list_chains

# ---------- Chain library ----------


def test_chain_library_has_expected_chains():
    assert "draft-model" in CHAIN_LIBRARY
    assert "find-connections" in CHAIN_LIBRARY


def test_list_chains_returns_sorted():
    chains = list_chains()
    assert len(chains) == 2
    assert chains[0].name == "draft-model"
    assert chains[1].name == "find-connections"


def test_get_chain_valid():
    spec = get_chain("draft-model")
    assert spec.name == "draft-model"
    assert spec.step_count == 3
    assert spec.steps[0].prompt_name == "DraftConceptualModel"
    assert spec.steps[1].prompt_name == "GenerateAssumptions"
    assert spec.steps[2].prompt_name == "SuggestCitations"


def test_get_chain_invalid_raises():
    with pytest.raises(KeyError, match="unknown chain"):
        get_chain("nonexistent")


def test_find_connections_chain_structure():
    spec = get_chain("find-connections")
    assert spec.step_count == 2
    assert spec.steps[0].prompt_name == "FindNewConnections"
    assert spec.steps[1].prompt_name == "GenerateAssumptions"


# ---------- Input builders ----------


def test_draft_inputs_passthrough():
    from latris.ai.chains import _draft_inputs

    trigger = {"focus": "air quality", "candidate_count": 3}
    result = _draft_inputs(trigger, [])
    assert result == trigger


def test_assumptions_from_draft_uses_first_applied_id():
    from latris.ai.call import CallOutcome
    from latris.ai.chains import _assumptions_from_draft

    outcome = CallOutcome(
        prompt_name="DraftConceptualModel",
        model="test",
        interaction_id="int_123",
        adoption="approved",
        applied_ids=["node_ABC", "node_DEF", "edge_GHI"],
        cost_usd=0.01,
        token_usage={},
    )
    result = _assumptions_from_draft({"focus": "test"}, [outcome])
    assert result == {"target_id": "node_ABC"}


def test_assumptions_from_draft_fallback_on_empty():
    from latris.ai.chains import _assumptions_from_draft

    result = _assumptions_from_draft({"focus": "water quality"}, [])
    assert result == {"target_id": "water quality"}


# ---------- Chain runner ----------


def test_chain_session_lifecycle(tmp_path: Path, git_identity, monkeypatch):
    """Start a chain, verify session state, abort it."""
    from latris.ai import chain_runner
    from latris.ai.adapters.base import ChatResult
    from latris.ai.adapters.mock_adapter import MockAdapter
    from latris.ai.chain_runner import _sessions
    from latris.ai.proposals import DraftFraming, DraftModelProposal
    from latris.operations.init import init_project
    from latris.operations.nodes import add_node

    monkeypatch.setenv("LATRIS_AI_MOCK", "1")

    root = tmp_path / "proj"
    init_project(root, statement="Test question")
    add_node("NodeA", kind="concept", root=root)

    # Register mock response for the first step
    MockAdapter.shared().register_default(
        response_cls=DraftModelProposal,
        result=ChatResult(
            parsed=DraftModelProposal(
                framings=[DraftFraming(name="F1", entities=[], edges=[], rationale="test")],
            ),
            raw="{}",
            model_id="test-model",
            token_usage={"input_tokens": 10, "output_tokens": 10},
            cost_usd=0.001,
        ),
    )

    import os

    orig = os.getcwd()
    os.chdir(str(root))
    try:
        from latris.schema import HumanActor

        approver = HumanActor(name="Test", email="test@test.com")

        session, outcome = chain_runner.start_chain(
            "draft-model",
            {"focus": "test phenomenon"},
            approver=approver,
            render=lambda p: p.model_dump_json(indent=2),
        )

        assert session.status == "active"
        assert session.current_step == 0
        assert session.total_steps == 3
        assert session.chain_name == "draft-model"
        assert outcome.prompt_name == "DraftConceptualModel"
        assert outcome.adoption == "pending"
        assert session.id in _sessions

        # Abort
        aborted = chain_runner.abort_chain(session.id)
        assert aborted.status == "aborted"
    finally:
        os.chdir(orig)
        MockAdapter.shared().clear()


def test_abort_nonexistent_session_raises():
    from latris.ai.chain_runner import get_session

    with pytest.raises(KeyError, match="No active chain session"):
        get_session("chain_NONEXISTENT")
