"""The chat adapter interface — one chokepoint for every LLM call."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMCallError(RuntimeError):
    """Provider-error wrapper with API keys scrubbed from the message.

    Raised by adapters instead of propagating provider-specific exceptions
    that may contain keys in URLs or headers. The CLI error handler catches
    this and prints a clean, safe message.

    ``raw_response`` carries the model's last raw output when the adapter
    can extract it (e.g. instructor's ``InstructorRetryException`` exposes
    the failed completion under ``last_completion``). It exists so the
    interaction logger can persist the malformed payload for diagnosis
    rather than throwing it away with the exception.
    """

    def __init__(self, message: str, *, raw_response: str | None = None) -> None:
        super().__init__(message)
        self.raw_response = raw_response


# Known API-key shapes. Order matters — the generic ``sk-`` must come last.
_KEY_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z_-]{20,}"),  # Google AI Studio / Gemini
    re.compile(r"sk-ant-(?:api\d+-)?[0-9A-Za-z_-]{20,}"),  # Anthropic
    re.compile(r"sk-proj-[0-9A-Za-z_-]{20,}"),  # OpenAI project keys
    re.compile(r"sk-svcacct-[0-9A-Za-z_-]{20,}"),  # OpenAI service accounts
    re.compile(r"gsk_[0-9A-Za-z_-]{20,}"),  # Groq
    re.compile(r"xai-[0-9A-Za-z_-]{20,}"),  # xAI
    re.compile(r"[?&]key=[0-9A-Za-z_-]{20,}"),  # any ?key=... in URLs
    re.compile(r"sk-[0-9A-Za-z_-]{20,}"),  # OpenAI legacy (keep last)
]


def redact_secrets(text: str) -> str:
    """Scrub anything that looks like an API key. Safe to call on tracebacks."""
    if not text:
        return text
    for pat in _KEY_PATTERNS:
        text = pat.sub("<REDACTED>", text)
    return text


@dataclass
class ChatResult:
    """What every adapter returns.

    - ``parsed`` is the pydantic-validated structured output (what the caller
      actually wanted — e.g. a ``ChallengeProposal``).
    - ``raw`` is the model's full text response, stashed for the interaction
      log so a future retrieval layer has verbatim memory.
    - ``token_usage`` is provider-reported token counts; shape is free-form
      but we standardise on ``input_tokens`` / ``output_tokens`` /
      ``cache_read_tokens`` / ``cache_write_tokens`` where applicable.
    - ``cost_usd`` is the estimated dollar cost for this call, if available.
    """

    parsed: BaseModel
    raw: str
    model_id: str
    token_usage: dict[str, Any] = field(default_factory=dict)
    cost_usd: float | None = None


class ChatAdapter(Protocol):
    """Minimum contract: ask a model for a typed response."""

    def chat(
        self,
        *,
        model: str,
        system: str,
        user: str,
        response_model: type[T],
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> ChatResult: ...
