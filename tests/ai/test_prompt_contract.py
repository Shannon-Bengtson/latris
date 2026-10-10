"""Structural guard tests for the prompt contract — "one prompt per button".

A prompt is defined by a ``PromptSpec`` (prompts.py) that now owns its
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


def test_behaviour_sets_are_subsets_of_the_library() -> None:
    """READ_ONLY / HYBRID / server-transformed sets must reference only real
    prompts — a typo'd or deleted name here silently mis-routes a prompt."""
    lib = set(prompt_lib.PROMPT_LIBRARY)
    for label, names in (
        ("READ_ONLY_PROMPTS", call_mod.READ_ONLY_PROMPTS),
        ("HYBRID_PROMPTS", call_mod.HYBRID_PROMPTS),
        ("_SERVER_TRANSFORMED_PROMPTS", call_mod._SERVER_TRANSFORMED_PROMPTS),
    ):
        stray = set(names) - lib
        assert not stray, f"{label} references unknown prompts: {sorted(stray)}"


def test_read_only_and_hybrid_are_disjoint() -> None:
    """A prompt is either read-only or hybrid (prose + bounded proposal), never
    classified as both — the two sets must not overlap."""
    overlap = set(call_mod.READ_ONLY_PROMPTS) & set(call_mod.HYBRID_PROMPTS)
    assert not overlap, f"prompts classified as both read-only and hybrid: {sorted(overlap)}"


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
