"""Real LLM calls via litellm + instructor.

litellm normalises the chat-completion API across Anthropic / OpenAI /
Gemini / Groq / Ollama / etc. Instructor wraps it with pydantic-native
structured output (JSON schema + validation + retry on bad output).

We never store keys here — litellm reads them from env vars, which the
call orchestrator populates from keyring just before each call and unsets
after.
"""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel

from latris.ai import config as ai_config
from latris.ai.adapters.base import ChatResult, LLMCallError, redact_secrets
from latris.perf import span

T = TypeVar("T", bound=BaseModel)


def _is_json_parse_error(exc: BaseException) -> bool:
    """Heuristic: did this exception come from a malformed-JSON response?

    Pydantic's ValidationError for JSON-mode structured output surfaces
    the message ``"Invalid JSON: ..."`` (see
    https://errors.pydantic.dev/2.12/v/json_invalid). Instructor wraps
    the validation error and propagates it; the substring match here is
    deliberately broad — false positives just spend one extra call,
    false negatives leak through to fail-loud where Layer 1 records
    them. Both error message and class name are searched because
    instructor's wrapper sometimes obscures the inner message.
    """
    text = f"{type(exc).__name__}: {exc}".lower()
    return "invalid json" in text or "jsondecodeerror" in text


def _build_repair_messages(
    *,
    system: str,
    user: str,
    raw_response: str,
    parser_error: str,
    response_model: type[BaseModel],
) -> list[dict[str, str]]:
    """Construct the message list for a self-correction retry.

    The model gets to see what it produced and the parser's complaint,
    so it can fix the structural issue (typically an unescaped quote
    or newline inside a string value) rather than re-generating
    blindly. We cap the embedded raw response and parser error to
    keep the repair prompt from approaching the context window in
    pathological cases.
    """
    raw_excerpt = raw_response[:4000]
    err_excerpt = parser_error[:1000]
    repair_user = (
        f"{user}\n\n"
        "Your previous response could not be parsed as a valid JSON "
        f"object matching the {response_model.__name__} schema:\n\n"
        f"<failed_response>\n{raw_excerpt}\n</failed_response>\n\n"
        "Parser error:\n"
        f"<parser_error>\n{err_excerpt}\n</parser_error>\n\n"
        "Re-emit the same intent as a valid JSON object. Common "
        "issues to check: unescaped double quotes inside string "
        'values (use \\"), literal newlines inside string values '
        "(use \\n), stray backslashes (use \\\\), and trailing "
        "commas. Output only the JSON object, no prose around it."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": repair_user},
    ]


class LiteLLMAdapter:
    """Lazy-imported litellm+instructor. Constructed once per process."""

    def __init__(self) -> None:
        # Import lazily so mock-mode runs don't pay the litellm import cost.
        import instructor  # type: ignore[import-untyped]
        import litellm  # type: ignore[import-untyped]

        self._instructor = instructor
        self._instructor_client_tools = instructor.from_litellm(litellm.completion)
        self._instructor_client_json = instructor.from_litellm(
            litellm.completion,
            mode=instructor.Mode.JSON,
        )
        self._litellm = litellm

    def chat(
        self,
        *,
        model: str,
        system: str,
        user: str,
        response_model: type[T],
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> ChatResult:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        # `create_with_completion` returns (parsed_model, raw_completion) so we
        # can keep the verbatim response for the interaction log. Any provider
        # error is re-wrapped as an ``LLMCallError`` with API keys scrubbed.
        #
        # Gemini models fail with Mode.TOOLS on complex schemas (optional/union
        # fields return empty completions); Moonshot's thinking models reject
        # the explicit tool_choice TOOLS mode sends ("tool_choice 'specified'
        # is incompatible with thinking enabled"). Both use Mode.JSON.
        lowered = model.lower()
        uses_json_mode = lowered.startswith("gemini") or lowered.startswith("moonshot")
        client = self._instructor_client_json if uses_json_mode else self._instructor_client_tools

        try:
            with span("adapter.chat", model=model):
                parsed, raw_completion = self._call(
                    client=client,
                    model=model,
                    messages=messages,
                    response_model=response_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
        except Exception as exc:
            raw_response = self._extract_last_raw_response(exc)
            # On parse failure, do one self-correction pass: feed the malformed
            # output back to the model with the parser error and ask for valid
            # JSON. Instructor's own retry doesn't show the model what it
            # produced — that's the meaningful step-up.
            if raw_response and _is_json_parse_error(exc):
                try:
                    with span("adapter.chat.repair", model=model):
                        parsed, raw_completion = self._call(
                            client=client,
                            model=model,
                            messages=_build_repair_messages(
                                system=system,
                                user=user,
                                raw_response=raw_response,
                                parser_error=str(exc),
                                response_model=response_model,
                            ),
                            response_model=response_model,
                            temperature=temperature,
                            max_tokens=max_tokens,
                        )
                except Exception as repair_exc:
                    # Repair pass also failed — raise wrapping the *repair*
                    # error since that's the most recent (still safe — both
                    # error messages and raw response are scrubbed).
                    safe_message = redact_secrets(str(repair_exc))
                    repair_raw = self._extract_last_raw_response(repair_exc) or raw_response
                    raise LLMCallError(
                        f"{type(repair_exc).__name__} from {model} (repair pass): {safe_message}",
                        raw_response=redact_secrets(repair_raw) or None,
                    ) from None
            else:
                safe_message = redact_secrets(str(exc))
                raise LLMCallError(
                    f"{type(exc).__name__} from {model}: {safe_message}",
                    raw_response=redact_secrets(raw_response or "") or None,
                ) from None

        token_usage = self._extract_token_usage(raw_completion)
        cost_usd = self._try_completion_cost(raw_completion)
        raw_text = self._first_text_content(raw_completion)

        return ChatResult(
            parsed=parsed,
            raw=raw_text,
            model_id=model,
            token_usage=token_usage,
            cost_usd=cost_usd,
        )

    def _call(
        self,
        *,
        client: Any,
        model: str,
        messages: list[dict[str, str]],
        response_model: type[T],
        temperature: float,
        max_tokens: int | None,
    ) -> tuple[T, Any]:
        """Single instructor invocation. Extracted so the repair pass can
        reuse the same code path with different messages."""
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "response_model": response_model,
            "temperature": temperature,
            # Bumped from 1 → 3 alongside Layer 2's repair pass. Instructor
            # retries on validation error (missing field, wrong type) — a
            # higher budget helps with transient hiccups before we burn the
            # one repair attempt below on actual JSON-parse failures.
            "max_retries": 3,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        extra_body = ai_config.resolve_extra_body(model)
        if extra_body:
            kwargs["extra_body"] = extra_body
        return client.chat.completions.create_with_completion(**kwargs)

    # ---- helpers ----

    @staticmethod
    def _extract_token_usage(completion: Any) -> dict[str, Any]:
        usage = getattr(completion, "usage", None)
        if usage is None:
            return {}
        # Usage fields vary per provider; collect the standard ones.
        out: dict[str, Any] = {}
        for src_key, dst_key in (
            ("prompt_tokens", "input_tokens"),
            ("completion_tokens", "output_tokens"),
            ("total_tokens", "total_tokens"),
            ("cache_read_input_tokens", "cache_read_tokens"),
            ("cache_creation_input_tokens", "cache_write_tokens"),
        ):
            value = getattr(usage, src_key, None)
            if value is not None:
                out[dst_key] = value
        return out

    def _try_completion_cost(self, completion: Any) -> float | None:
        try:
            return float(self._litellm.completion_cost(completion_response=completion))
        except Exception:
            return None

    @staticmethod
    def _first_text_content(completion: Any) -> str:
        try:
            choices = getattr(completion, "choices", None) or []
            if not choices:
                return ""
            msg = getattr(choices[0], "message", None)
            return getattr(msg, "content", "") or ""
        except Exception:
            return ""

    @classmethod
    def _extract_last_raw_response(cls, exc: BaseException) -> str | None:
        """Best-effort pull of the failed model output from instructor's exception.

        Instructor's ``InstructorRetryException`` exposes the last completion
        under ``last_completion`` (a chat-completion-shaped object). When
        retries are exhausted on a parse failure, this is the malformed
        payload we need for diagnosis. Falls back to ``messages`` /
        ``raw_response`` attribute names other instructor versions use.
        """
        for attr in ("last_completion", "raw_response", "completion"):
            completion = getattr(exc, attr, None)
            if completion is None:
                continue
            text = cls._first_text_content(completion)
            if text:
                return text
        # InstructorRetryException stores the rendered prompt under `messages`
        # and the parser failure under `n_attempts` / `total_usage`; the raw
        # text we want isn't always reachable. Last resort: stringify the
        # exception's traceback tail.
        return None
