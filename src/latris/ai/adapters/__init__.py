"""Chat adapters — how we get a typed proposal out of an LLM.

The rest of the codebase only ever imports ``get_adapter()`` from here.
Selection is environment-driven so tests and CI can run without network.
"""

from __future__ import annotations

import os

from latris.ai.adapters.base import ChatAdapter, ChatResult
from latris.ai.adapters.mock_adapter import MockAdapter

MOCK_ENV_VAR = "LATRIS_AI_MOCK"
# One-release back-compat: environments exported before the rename (and the
# private app repo's CI during the transition) may still set the old name.
_LEGACY_MOCK_ENV_VAR = "GRAPH_TOOLING_AI_MOCK"


def mock_enabled() -> bool:
    """True when AI mocking is requested via env: ``LATRIS_AI_MOCK``, falling
    back to the pre-rename ``GRAPH_TOOLING_AI_MOCK`` for one release."""
    value = os.environ.get(MOCK_ENV_VAR) or os.environ.get(_LEGACY_MOCK_ENV_VAR) or ""
    return value.lower() in ("1", "true", "yes")


def get_adapter() -> ChatAdapter:
    """Return the active chat adapter.

    If ``LATRIS_AI_MOCK`` is truthy, return a ``MockAdapter`` — zero
    network, deterministic responses from whatever's been registered via
    ``MockAdapter.register(...)``. Otherwise return the ``LiteLLMAdapter``.
    """
    if mock_enabled():
        return MockAdapter.shared()
    # Lazy import: litellm is heavy and pulls in several transitive deps on
    # first import. No reason to pay that cost in mock mode.
    from latris.ai.adapters.litellm_adapter import LiteLLMAdapter

    return LiteLLMAdapter()


__all__ = ["ChatAdapter", "ChatResult", "MockAdapter", "get_adapter", "mock_enabled"]
