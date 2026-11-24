"""Registering prompts from outside the library.

The built-in prompts are defined in ``prompts/`` and wired at import. A
server plugin (``latris.server_plugins``) that brings its own AI feature
registers its prompts here, once, when it loads. A registered prompt then
works like a built-in one: ``ai.call.run_call`` finds it by name, the
provider abstraction, credentials, mocking and ``ai/interactions.jsonl``
logging all apply, and the commit still records the responsible human.

The interaction log records a prompt's name and inputs, never its template,
so a plugin's prompt text stays with the plugin.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from pydantic import BaseModel

from latris.ai import call as _call
from latris.ai import context as _context
from latris.ai import prompts as _prompts
from latris.ai import render as _render
from latris.ai.context import SYSTEM_PREAMBLE, ContextPack
from latris.ai.prompts import PromptMode, PromptSpec
from latris.repo.layout import ProjectPaths

ContextBuilder = Callable[[ProjectPaths, dict[str, Any]], ContextPack]

_MODE_SETS: dict[str, set[str]] = {
    "read_only": _call.READ_ONLY_PROMPTS,
    "hybrid": _call.HYBRID_PROMPTS,
    "server_transformed": _call._SERVER_TRANSFORMED_PROMPTS,
}


def register_prompt(
    spec: PromptSpec,
    *,
    response_model: type[BaseModel],
    context_builder: ContextBuilder,
    mode: PromptMode = "read_only",
    renderer: Callable[[BaseModel], str] | None = None,
    temperature: float | None = None,
) -> PromptSpec:
    """Add a prompt to the library, as if it were built in.

    Registering the same name again replaces the earlier registration only if
    it was registered here too: a built-in prompt can't be replaced. Returns
    the wired spec.
    """
    name = spec.name
    if name in _prompts.PROMPT_LIBRARY and name not in _REGISTERED:
        raise ValueError(f"prompt {name!r} is built in and can't be replaced")
    wired = replace(spec, response_model=response_model, temperature=temperature, mode=mode)
    _prompts.PROMPT_LIBRARY[name] = wired
    _call.RESPONSE_MODELS[name] = response_model
    _context._BUILDERS[name] = context_builder
    if renderer is not None:
        _render.RENDERERS[name] = renderer
    else:
        _render.RENDERERS.pop(name, None)
    for mode_name, names in _MODE_SETS.items():
        if mode_name == mode:
            names.add(name)
        else:
            names.discard(name)
    _REGISTERED.add(name)
    return wired


def project_context(paths: ProjectPaths) -> str:
    """The project block every built-in prompt opens with: the question,
    background, boundary and scope. A plugin's context builder starts its user
    message with this so its prompts see the project the same way."""
    return _context._foundation_summary(_context._load_foundation(paths))


def registered_prompts() -> frozenset[str]:
    """Names of the prompts added through :func:`register_prompt`."""
    return frozenset(_REGISTERED)


_REGISTERED: set[str] = set()

__all__ = [
    "SYSTEM_PREAMBLE",
    "ContextBuilder",
    "ContextPack",
    "project_context",
    "register_prompt",
    "registered_prompts",
]
