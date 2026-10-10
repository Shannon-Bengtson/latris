from __future__ import annotations

import pytest
from pydantic import BaseModel

from latris.ai.adapters import get_adapter
from latris.ai.adapters.base import ChatAdapter, ChatResult
from latris.ai.adapters.mock_adapter import MockAdapter


class DemoOutput(BaseModel):
    reply: str
    confidence: float


@pytest.fixture(autouse=True)
def reset_mock():
    MockAdapter.reset_shared()
    yield
    MockAdapter.reset_shared()


def test_mock_registered_exact_signature() -> None:
    adapter = MockAdapter()
    canned = ChatResult(
        parsed=DemoOutput(reply="hi", confidence=0.9),
        raw="hi",
        model_id="claude-opus-4-6",
        token_usage={"input_tokens": 10, "output_tokens": 2},
        cost_usd=0.0001,
    )
    adapter.register(
        model="claude-opus-4-6",
        system="sys",
        user="usr",
        response_cls=DemoOutput,
        result=canned,
    )
    result = adapter.chat(
        model="claude-opus-4-6",
        system="sys",
        user="usr",
        response_model=DemoOutput,
    )
    assert result is canned
    assert isinstance(result.parsed, DemoOutput)
    assert result.token_usage["input_tokens"] == 10


def test_mock_default_by_response_cls() -> None:
    adapter = MockAdapter()
    canned = ChatResult(
        parsed=DemoOutput(reply="default", confidence=0.5),
        raw="default",
        model_id="x",
    )
    adapter.register_default(response_cls=DemoOutput, result=canned)

    # Any (model, system, user) falls through to the default.
    result = adapter.chat(
        model="any-model",
        system="whatever",
        user="whatever",
        response_model=DemoOutput,
    )
    assert result.parsed.reply == "default"


def test_mock_raises_when_nothing_registered() -> None:
    adapter = MockAdapter()
    with pytest.raises(LookupError, match="no canned response"):
        adapter.chat(
            model="m",
            system="s",
            user="u",
            response_model=DemoOutput,
        )


def test_mock_signature_distinguishes_response_cls() -> None:
    class OtherOutput(BaseModel):
        value: int

    adapter = MockAdapter()
    adapter.register(
        model="m",
        system="s",
        user="u",
        response_cls=DemoOutput,
        result=ChatResult(parsed=DemoOutput(reply="a", confidence=0.1), raw="a", model_id="m"),
    )
    # Same prompt, different response class → not a match.
    with pytest.raises(LookupError):
        adapter.chat(
            model="m",
            system="s",
            user="u",
            response_model=OtherOutput,
        )


def test_get_adapter_returns_mock_when_env_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LATRIS_AI_MOCK", "1")
    adapter = get_adapter()
    assert isinstance(adapter, MockAdapter)


def test_adapter_satisfies_protocol() -> None:
    # Structural check — MockAdapter satisfies the ChatAdapter Protocol.
    adapter: ChatAdapter = MockAdapter()
    assert hasattr(adapter, "chat")
