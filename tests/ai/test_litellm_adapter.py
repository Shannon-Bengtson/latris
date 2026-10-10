"""Tests for the LiteLLM adapter — Layer 2 JSON-repair retry path.

These tests avoid a real network call by patching the adapter's
``_call`` method directly. The interesting behavior to verify lives
in the orchestration around the instructor call (parse-error detection,
repair-pass message construction, raw-response capture), not inside
instructor itself.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from latris.ai.adapters.base import LLMCallError
from latris.ai.adapters.litellm_adapter import (
    LiteLLMAdapter,
    _build_repair_messages,
    _is_json_parse_error,
)


class _Reply(BaseModel):
    message: str


class _FakeCompletion:
    """Mimic the shape of a litellm chat completion object enough for
    ``_first_text_content`` / ``_extract_token_usage`` to read it."""

    class _Msg:
        def __init__(self, content: str) -> None:
            self.content = content

    class _Choice:
        def __init__(self, content: str) -> None:
            self.message = _FakeCompletion._Msg(content)

    def __init__(self, content: str = "(mock)") -> None:
        self.choices = [self._Choice(content)]
        self.usage = None


# ── _is_json_parse_error ─────────────────────────────────────────────


class TestIsJsonParseError:
    def test_invalid_json_substring_matches(self) -> None:
        exc = ValueError("1 validation error for X\nInvalid JSON: expected `,`")
        assert _is_json_parse_error(exc)

    def test_jsondecodeerror_class_matches(self) -> None:
        import json

        try:
            json.loads("{not json")
        except json.JSONDecodeError as exc:
            assert _is_json_parse_error(exc)
        else:
            pytest.fail("expected JSONDecodeError")

    def test_unrelated_error_does_not_match(self) -> None:
        assert not _is_json_parse_error(TimeoutError("connection timed out"))
        assert not _is_json_parse_error(RuntimeError("rate limit exceeded"))

    def test_case_insensitive(self) -> None:
        assert _is_json_parse_error(ValueError("INVALID JSON: foo"))


# ── _build_repair_messages ───────────────────────────────────────────


class TestBuildRepairMessages:
    def test_includes_failed_response_and_parser_error(self) -> None:
        messages = _build_repair_messages(
            system="be helpful",
            user="explain price",
            raw_response='{"explanation": "the value is \\\\\\\\"high\\""',
            parser_error="Invalid JSON: expected `,` at line 1 col 30",
            response_model=_Reply,
        )
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "be helpful"
        assert messages[1]["role"] == "user"
        body = messages[1]["content"]
        assert "explain price" in body  # original task preserved
        assert "<failed_response>" in body
        assert "_Reply schema" in body
        assert "Invalid JSON" in body  # parser complaint visible

    def test_truncates_oversize_raw_response(self) -> None:
        huge = "x" * 10_000
        messages = _build_repair_messages(
            system="s", user="u", raw_response=huge, parser_error="e", response_model=_Reply
        )
        body = messages[1]["content"]
        # 4000 char cap; verify the original 10K wasn't passed through.
        assert "x" * 4001 not in body


# ── LiteLLMAdapter.chat — repair flow ────────────────────────────────


@pytest.fixture
def adapter() -> LiteLLMAdapter:
    """Real adapter instance. Tests patch `_call` so no network is touched."""
    return LiteLLMAdapter()


def _good_call(parsed: BaseModel, raw_text: str = "(mock raw)"):
    """Helper: build a `_call` return value that mimics a successful instructor call."""
    return parsed, _FakeCompletion(raw_text)


def test_chat_succeeds_on_first_call(
    adapter: LiteLLMAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, Any]] = []

    def _call(**kwargs):
        calls.append(kwargs)
        return _good_call(_Reply(message="hi"))

    monkeypatch.setattr(adapter, "_call", _call)
    result = adapter.chat(
        model="claude-sonnet-4-6",
        system="s",
        user="u",
        response_model=_Reply,
    )
    assert result.parsed.message == "hi"
    assert len(calls) == 1  # no repair pass needed


def test_chat_runs_repair_pass_on_json_parse_failure(
    adapter: LiteLLMAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `_call` that raises Invalid JSON on first attempt should
    trigger one repair pass with a follow-up user message that contains
    the failed response. The repair attempt's parsed result is returned."""
    bad_raw = '{"message": "tru' + 'ncated payload'

    class _ParseError(ValueError):
        """Mimics instructor's wrapped pydantic validation error.

        Exposes `last_completion` so `_extract_last_raw_response` can
        pull the raw output — mirrors instructor's
        ``InstructorRetryException`` shape.
        """

        def __init__(self, msg: str, completion: Any) -> None:
            super().__init__(msg)
            self.last_completion = completion

    attempts: list[list[dict[str, str]]] = []

    def _call(**kwargs):
        attempts.append(kwargs["messages"])
        if len(attempts) == 1:
            raise _ParseError(
                "1 validation error for _Reply\nInvalid JSON: expected `,` or `}` "
                "at line 1 column 30",
                _FakeCompletion(bad_raw),
            )
        return _good_call(_Reply(message="recovered"))

    monkeypatch.setattr(adapter, "_call", _call)

    result = adapter.chat(
        model="gemini/gemini-2.5-flash",
        system="be helpful",
        user="explain X",
        response_model=_Reply,
    )

    assert result.parsed.message == "recovered"
    assert len(attempts) == 2, "expected exactly one repair pass"
    repair_user = attempts[1][1]["content"]
    assert "explain X" in repair_user  # original task preserved
    assert "<failed_response>" in repair_user
    assert "truncated payload" in repair_user
    assert "Invalid JSON" in repair_user


def test_chat_raises_when_repair_also_fails(
    adapter: LiteLLMAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the repair pass also fails, the adapter raises LLMCallError
    with the repair-pass error wrapped — the failure surfaces, and
    Layer 1 records it from there."""

    class _ParseError(ValueError):
        def __init__(self, msg: str) -> None:
            super().__init__(msg)
            self.last_completion = _FakeCompletion('{"bad": ')

    def _call(**_kwargs):
        raise _ParseError("Invalid JSON: still broken")

    monkeypatch.setattr(adapter, "_call", _call)

    with pytest.raises(LLMCallError) as exc_info:
        adapter.chat(
            model="gemini/gemini-2.5-flash",
            system="s",
            user="u",
            response_model=_Reply,
        )
    assert "repair pass" in str(exc_info.value)
    # Raw response is still attached so Layer 1's audit trail captures it.
    assert getattr(exc_info.value, "raw_response", None) is not None


def test_chat_does_not_repair_on_non_parse_error(
    adapter: LiteLLMAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Network / auth / rate-limit errors are NOT recoverable by JSON
    repair, so the adapter raises immediately without the extra call."""
    attempts: list[Any] = []

    def _call(**kwargs):
        attempts.append(kwargs)
        raise TimeoutError("connection timed out")

    monkeypatch.setattr(adapter, "_call", _call)

    with pytest.raises(LLMCallError) as exc_info:
        adapter.chat(
            model="claude-sonnet-4-6",
            system="s",
            user="u",
            response_model=_Reply,
        )
    assert "TimeoutError" in str(exc_info.value)
    assert len(attempts) == 1, "should not retry on non-parse errors"


def test_chat_uses_max_retries_three() -> None:
    """The single-attempt instructor retry budget was too tight; we
    bumped it to 3 alongside the Layer 2 repair pass. Source-level
    check because the value is hard-coded inside ``_call`` and not
    surfaced as a keyword arg."""
    import inspect

    source = inspect.getsource(LiteLLMAdapter._call)
    assert '"max_retries": 3' in source, "max_retries should be bumped to 3"


def _capture_call_kwargs(adapter: LiteLLMAdapter, model: str) -> dict:
    """Run ``_call`` against a fake instructor client and return the kwargs
    the client was invoked with."""
    captured: dict = {}

    class _FakeCompletions:
        def create_with_completion(self, **kwargs):
            captured.update(kwargs)
            return None, None

    fake_client = type(
        "FakeClient",
        (),
        {"chat": type("chat", (), {"completions": _FakeCompletions()})},
    )

    class _Spec(BaseModel):
        label: str

    adapter._call(
        client=fake_client(),
        model=model,
        messages=[],
        response_model=_Spec,
        temperature=0.3,
        max_tokens=None,
    )
    return captured


def test_call_sends_thinking_disabled_for_moonshot(adapter: LiteLLMAdapter) -> None:
    kwargs = _capture_call_kwargs(adapter, "moonshot/kimi-k2.6")
    assert kwargs.get("extra_body") == {"thinking": {"type": "disabled"}}


def test_call_omits_extra_body_for_other_providers(adapter: LiteLLMAdapter) -> None:
    kwargs = _capture_call_kwargs(adapter, "gemini/gemini-2.5-flash")
    assert "extra_body" not in kwargs
