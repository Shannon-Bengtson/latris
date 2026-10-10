"""Deterministic mock adapter — hermetic for tests and demos.

Tests or dev sessions pre-register canned ``ChatResult``s keyed by prompt
signature; ``chat()`` looks the key up and returns the canned result.
Falls through to a generic stub if nothing is registered for the key —
useful for smoke runs where we just want no-network behaviour.
"""

from __future__ import annotations

import hashlib
from typing import TypeVar

from pydantic import BaseModel

from latris.ai.adapters.base import ChatResult

T = TypeVar("T", bound=BaseModel)

_SHARED: MockAdapter | None = None


def _signature(model: str, system: str, user: str, response_cls: type[BaseModel]) -> str:
    hasher = hashlib.sha256()
    hasher.update(model.encode("utf-8"))
    hasher.update(b"\x00")
    hasher.update(system.encode("utf-8"))
    hasher.update(b"\x00")
    hasher.update(user.encode("utf-8"))
    hasher.update(b"\x00")
    hasher.update(response_cls.__name__.encode("utf-8"))
    return hasher.hexdigest()


class MockAdapter:
    """In-memory fake. Not thread-safe; tests serialise their own state."""

    def __init__(self) -> None:
        self._registry: dict[str, ChatResult] = {}
        self._default_by_response_cls: dict[str, ChatResult] = {}

    # ---- registration ----

    def register(
        self,
        *,
        model: str,
        system: str,
        user: str,
        response_cls: type[BaseModel],
        result: ChatResult,
    ) -> None:
        """Bind an exact ``(model, system, user, response_cls)`` to a canned result."""
        self._registry[_signature(model, system, user, response_cls)] = result

    def register_default(
        self,
        *,
        response_cls: type[BaseModel],
        result: ChatResult,
    ) -> None:
        """Fallback for any call whose response_cls matches, regardless of prompt."""
        self._default_by_response_cls[response_cls.__name__] = result

    def clear(self) -> None:
        self._registry.clear()
        self._default_by_response_cls.clear()

    # ---- adapter protocol ----

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
        key = _signature(model, system, user, response_model)
        if key in self._registry:
            return self._registry[key]
        fallback = self._default_by_response_cls.get(response_model.__name__)
        if fallback is not None:
            return fallback
        raise LookupError(
            f"MockAdapter: no canned response registered for response_model="
            f"{response_model.__name__} (model={model!r}). Register one via "
            "MockAdapter.shared().register(...) / register_default(...)."
        )

    # ---- process-wide singleton ----

    @classmethod
    def shared(cls) -> MockAdapter:
        global _SHARED
        if _SHARED is None:
            _SHARED = cls()
        return _SHARED

    @classmethod
    def reset_shared(cls) -> None:
        global _SHARED
        _SHARED = None
