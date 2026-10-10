"""Tests for the AI call orchestrator (ai/call.py).

This exercises run_call() end-to-end using the mock adapter, and tests
_provider_for() in isolation. The mock adapter is activated via
LATRIS_AI_MOCK=1.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.ai.adapters.base import ChatResult
from latris.ai.adapters.mock_adapter import MockAdapter
from latris.ai.call import (
    _provider_for,
    run_call,
)
from latris.ai.proposals import ExplanationResult
from latris.operations import nodes as node_ops
from latris.operations.init import init_project
from latris.schema.common import HumanActor


@pytest.fixture(autouse=True)
def _mock_mode(monkeypatch):
    monkeypatch.setenv("LATRIS_AI_MOCK", "1")


@pytest.fixture
def project(tmp_path: Path, git_identity, monkeypatch) -> Path:
    root = tmp_path / "proj"
    init_project(root, statement="Test question?")
    node_ops.add_node("Price", kind="variable", root=root)
    # run_call() discovers project from cwd
    monkeypatch.chdir(root)
    return root


@pytest.fixture(autouse=True)
def _clean_mock():
    """Reset mock adapter state before each test."""
    MockAdapter.reset_shared()
    yield
    MockAdapter.reset_shared()


def _register_explain_mock() -> None:
    """Register a canned ExplanationResult for the mock adapter."""
    mock = MockAdapter.shared()
    result = ChatResult(
        parsed=ExplanationResult(
            explanation="Price is the cost paid by consumers.",
            referenced_ids=[],
        ),
        raw="Price is the cost paid by consumers.",
        model_id="mock-model",
        token_usage={"input_tokens": 100, "output_tokens": 50},
        cost_usd=0.001,
    )
    mock.register_default(response_cls=ExplanationResult, result=result)


def _approver() -> HumanActor:
    return HumanActor(name="Test User")


def _noop_render(parsed) -> str:
    return str(parsed)


# ── _provider_for ───────────────────────────────────────────────────


class TestProviderFor:
    def test_claude_model(self) -> None:
        assert _provider_for("claude-3-opus") == "anthropic"

    def test_anthropic_model(self) -> None:
        assert _provider_for("anthropic/claude-3") == "anthropic"

    def test_gpt_model(self) -> None:
        assert _provider_for("gpt-4o") == "openai"

    def test_openai_prefix(self) -> None:
        assert _provider_for("openai/gpt-4") == "openai"

    def test_gemini_model(self) -> None:
        assert _provider_for("gemini-1.5-pro") == "gemini"

    def test_groq_model(self) -> None:
        assert _provider_for("groq/llama") == "groq"

    def test_mistral_model(self) -> None:
        assert _provider_for("mistral-large") == "mistral"

    def test_deepseek_model(self) -> None:
        assert _provider_for("deepseek-chat") == "deepseek"

    def test_unknown_defaults_anthropic(self) -> None:
        assert _provider_for("some-unknown-model") == "anthropic"

    def test_env_override(self, monkeypatch) -> None:
        monkeypatch.setenv("LATRIS_AI_PROVIDER", "custom")
        assert _provider_for("anything") == "custom"

    def test_slash_prefix_extraction(self) -> None:
        assert _provider_for("myhost/custom-model") == "myhost"


# ── run_call — unknown prompt ───────────────────────────────────────


def test_unknown_prompt_raises(project: Path) -> None:
    with pytest.raises(ValueError, match="unknown prompt"):
        run_call(
            prompt_name="NoSuchPrompt",
            inputs={},
            approver=_approver(),
            confirm=lambda *_: True,
            render=_noop_render,
        )


# ── run_call — dry run ──────────────────────────────────────────────


def test_dry_run_returns_without_calling_adapter(project: Path) -> None:
    # Don't register anything — dry_run should never call the adapter
    node = node_ops.list_nodes(project)[0]
    outcome = run_call(
        prompt_name="ExplainThisElement",
        inputs={"target_id": node.id},
        approver=_approver(),
        confirm=lambda *_: True,
        render=_noop_render,
        dry_run=True,
    )
    assert outcome.adoption == "dry-run"
    assert outcome.interaction_id == "(dry-run)"
    assert outcome.cost_usd is None


# ── run_call — read-only prompt ─────────────────────────────────────


def test_read_only_prompt_logs_as_approved(project: Path) -> None:
    _register_explain_mock()
    node = node_ops.list_nodes(project)[0]
    outcome = run_call(
        prompt_name="ExplainThisElement",
        inputs={"target_id": node.id},
        approver=_approver(),
        confirm=lambda *_: True,
        render=_noop_render,
    )
    assert outcome.adoption == "approved"
    assert outcome.applied_ids == []  # read-only — nothing applied
    assert outcome.prompt_name == "ExplainThisElement"
    assert len(outcome.interaction_id) > 0


# ── run_call — preview only ─────────────────────────────────────────


def test_preview_only_returns_pending(project: Path) -> None:
    from latris.ai.proposals import ChallengeProposal

    node = node_ops.list_nodes(project)[0]
    mock = MockAdapter.shared()
    mock.register_default(
        response_cls=ChallengeProposal,
        result=ChatResult(
            parsed=ChallengeProposal(
                target_id=node.id,
                argument="Questionable link.",
            ),
            raw="challenge text",
            model_id="mock",
        ),
    )
    outcome = run_call(
        prompt_name="ChallengeThisConnection",
        inputs={"target_id": node.id},
        approver=_approver(),
        confirm=lambda *_: True,
        render=_noop_render,
        preview_only=True,
    )
    assert outcome.adoption == "pending"
    assert outcome.proposal_json is not None
    assert outcome.applied_ids == []


# ── run_call — mutation rejected ────────────────────────────────────


def test_mutation_rejected_logs_and_returns(project: Path) -> None:
    from latris.ai.proposals import ChallengeProposal

    node = node_ops.list_nodes(project)[0]
    mock = MockAdapter.shared()
    mock.register_default(
        response_cls=ChallengeProposal,
        result=ChatResult(
            parsed=ChallengeProposal(
                target_id=node.id,
                argument="Bad link.",
            ),
            raw="challenge text",
            model_id="mock",
        ),
    )
    outcome = run_call(
        prompt_name="ChallengeThisConnection",
        inputs={"target_id": node.id},
        approver=_approver(),
        confirm=lambda *_: False,  # user rejects
        render=_noop_render,
    )
    assert outcome.adoption == "rejected"
    assert outcome.applied_ids == []


# ── run_call — mutation approved ────────────────────────────────────


def test_mutation_approved_applies_and_returns_ids(project: Path) -> None:
    from latris.ai.proposals import ChallengeProposal

    node = node_ops.list_nodes(project)[0]
    mock = MockAdapter.shared()
    mock.register_default(
        response_cls=ChallengeProposal,
        result=ChatResult(
            parsed=ChallengeProposal(
                target_id=node.id,
                argument="Questionable.",
            ),
            raw="challenge",
            model_id="mock",
        ),
    )
    outcome = run_call(
        prompt_name="ChallengeThisConnection",
        inputs={"target_id": node.id},
        approver=_approver(),
        confirm=lambda *_: True,
        render=_noop_render,
    )
    assert outcome.adoption == "approved"
    assert len(outcome.applied_ids) >= 1


# ── run_call — adapter failure path (Layer 1) ───────────────────────


def test_adapter_failure_records_interaction_and_reraises(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """LLMCallError from the adapter is recorded with adoption=failed,
    error fields populated, and re-raised so CLI error handling is
    unchanged. Without this, failed calls vanished from the audit trail."""
    from latris.ai import interactions as inter_ops
    from latris.ai.adapters.base import LLMCallError

    node = node_ops.list_nodes(project)[0]

    def _raise(**_kwargs):
        raise LLMCallError(
            "ValidationError from gemini/gemini-2.5-flash: 1 validation "
            "error for ExplanationResult\nInvalid JSON: expected `,` or `}`",
            raw_response='{"explanation": "this is a truncated payl',
        )

    # Patch the mock adapter's chat method to raise; the orchestrator
    # path must catch + record + re-raise.
    mock = MockAdapter.shared()
    monkeypatch.setattr(mock, "chat", _raise)

    with pytest.raises(LLMCallError):
        run_call(
            prompt_name="ExplainThisElement",
            inputs={"target_id": node.id},
            approver=_approver(),
            confirm=lambda *_: True,
            render=_noop_render,
        )

    records = list(inter_ops.iter_interactions(root=project))
    failed = [r for r in records if r.adoption == "failed"]
    assert len(failed) == 1, (
        f"expected exactly one failed interaction, got {len(failed)} of "
        f"{len(records)} total"
    )
    record = failed[0]
    assert record.prompt_name == "ExplainThisElement"
    assert record.error_class == "LLMCallError"
    assert "Invalid JSON" in (record.error_message or "")
    assert record.raw_response_excerpt is not None
    assert "truncated" in record.raw_response_excerpt


def test_adapter_failure_truncates_raw_response_excerpt(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Raw responses can be arbitrarily large; the audit field is bounded
    so the JSONL doesn't blow up from one runaway model output."""
    from latris.ai import interactions as inter_ops
    from latris.ai.adapters.base import LLMCallError

    node = node_ops.list_nodes(project)[0]
    huge_raw = "x" * 20_000  # well past the 4 KB cap

    def _raise(**_kwargs):
        raise LLMCallError("boom", raw_response=huge_raw)

    mock = MockAdapter.shared()
    monkeypatch.setattr(mock, "chat", _raise)

    with pytest.raises(LLMCallError):
        run_call(
            prompt_name="ExplainThisElement",
            inputs={"target_id": node.id},
            approver=_approver(),
            confirm=lambda *_: True,
            render=_noop_render,
        )

    failed = [
        r for r in inter_ops.iter_interactions(root=project) if r.adoption == "failed"
    ]
    assert len(failed) == 1
    excerpt = failed[0].raw_response_excerpt
    assert excerpt is not None
    assert len(excerpt) == 4096
    assert excerpt == "x" * 4096
