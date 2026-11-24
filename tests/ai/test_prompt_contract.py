"""Structural guard tests for the prompt contract — "one prompt per button".

A prompt is defined by a ``PromptSpec`` (prompts/) that now owns its
response model and per-op temperature. These tests enforce that the spec
registry, the derived response-model map, and the context builders stay in
bijection, and that the behaviour-classification sets in call.py reference only
real prompts. They are pure introspection (no project fixture, no adapter), so
they run instantly and fail loudly the moment a new prompt lands half-wired.
"""

from __future__ import annotations

import pytest

from latris.ai import call as call_mod
from latris.ai import prompts as prompt_lib
from latris.ai.context import _BUILDERS
from latris.ai.prompts import _In


def test_every_spec_has_a_response_model() -> None:
    """``_wire`` should attach a response model to every spec."""
    missing = [name for name, spec in prompt_lib.PROMPT_LIBRARY.items() if spec.response_model is None]
    assert not missing, f"prompts with no response_model on their spec: {missing}"


def test_tri_registry_bijection() -> None:
    """The spec registry, the derived RESPONSE_MODELS alias, and the context
    builders must cover exactly the same set of prompt names — the enforceable
    form of "one prompt, one definition."""
    lib = set(prompt_lib.PROMPT_LIBRARY)
    resp = set(call_mod.RESPONSE_MODELS)
    builders = set(_BUILDERS)
    assert lib == resp == builders, (
        "prompt registries out of bijection:\n"
        f"  in lib not resp:      {sorted(lib - resp)}\n"
        f"  in resp not lib:      {sorted(resp - lib)}\n"
        f"  in lib not builders:  {sorted(lib - builders)}\n"
        f"  in builders not lib:  {sorted(builders - lib)}"
    )


def test_derived_response_models_match_specs() -> None:
    """The call.py alias must be exactly the specs' response models (it is a
    derived view; this pins that it was not hand-edited to diverge)."""
    for name, spec in prompt_lib.PROMPT_LIBRARY.items():
        assert call_mod.RESPONSE_MODELS[name] is spec.response_model


def test_behaviour_is_one_mode_per_spec() -> None:
    """Each prompt's behaviour is a single ``mode`` on its spec, so a prompt
    can't be both read-only and hybrid; call.py's name sets are views of it."""
    by_mode: dict[str, set[str]] = {}
    for name, spec in prompt_lib.PROMPT_LIBRARY.items():
        by_mode.setdefault(spec.mode, set()).add(name)
    assert by_mode.get("read_only", set()) == call_mod.READ_ONLY_PROMPTS
    assert by_mode.get("hybrid", set()) == call_mod.HYBRID_PROMPTS
    assert by_mode.get("server_transformed", set()) == call_mod._SERVER_TRANSFORMED_PROMPTS


def test_renderers_name_real_prompts() -> None:
    """A renderer under a typo'd or deleted name would silently never run."""
    from latris.ai.render import RENDERERS

    stray = set(RENDERERS) - set(prompt_lib.PROMPT_LIBRARY)
    assert not stray, f"renderers for unknown prompts: {sorted(stray)}"


@pytest.mark.parametrize("spec", prompt_lib.list_all(), ids=lambda s: s.name)
def test_input_schemas_forbid_extra_fields(spec: prompt_lib.PromptSpec) -> None:
    """Every prompt's input schema subclasses the shared ``_In`` base and
    forbids extra fields, so a mistyped input is rejected rather than silently
    dropped. (The one exception intentionally allowed through is the internal
    ``steer`` / ``_prompt_name`` side-channel, injected below the schema.)"""
    assert issubclass(spec.inputs, _In), f"{spec.name}: inputs must subclass _In"
    assert spec.inputs.model_config.get("extra") == "forbid", (
        f"{spec.name}: input schema must set extra='forbid'"
    )
