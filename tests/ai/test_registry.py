"""Prompts registered by a plugin behave like built-in ones."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from latris.ai import call, context, prompts, registry, render
from latris.ai.context import ContextPack
from latris.ai.prompts import PromptSpec


class _Inputs(BaseModel):
    topic: str = ""


class _Result(BaseModel):
    text: str


def _spec(name: str) -> PromptSpec:
    return PromptSpec(
        name=name,
        title="Plugin prompt",
        description="A prompt a plugin brings.",
        inputs=_Inputs,
        template="Say something about {topic}.",
        output_hint="text",
    )


def _builder(paths, inputs) -> ContextPack:  # noqa: ANN001
    return ContextPack(system="sys", user=f"about {inputs.get('topic', '')}")


@pytest.fixture
def cleanup():
    names: list[str] = []
    yield names
    for name in names:
        prompts.PROMPT_LIBRARY.pop(name, None)
        call.RESPONSE_MODELS.pop(name, None)
        context._BUILDERS.pop(name, None)
        render.RENDERERS.pop(name, None)
        for s in (call.READ_ONLY_PROMPTS, call.HYBRID_PROMPTS, call._SERVER_TRANSFORMED_PROMPTS):
            s.discard(name)
        registry._REGISTERED.discard(name)


def test_registered_prompt_is_wired_everywhere(cleanup, tmp_path):
    cleanup.append("PluginSay")
    spec = registry.register_prompt(
        _spec("PluginSay"),
        response_model=_Result,
        context_builder=_builder,
        renderer=lambda parsed: parsed.text.upper(),
        temperature=0.2,
    )
    assert spec.response_model is _Result and spec.mode == "read_only" and spec.temperature == 0.2
    assert prompts.get("PluginSay") is spec
    assert call.RESPONSE_MODELS["PluginSay"] is _Result
    assert "PluginSay" in call.READ_ONLY_PROMPTS
    assert render.render("PluginSay", _Result(text="hi")) == "HI"
    pack = context.build_context("PluginSay", {"topic": "rivers"}, paths=None)  # type: ignore[arg-type]
    assert pack.user == "about rivers"
    assert "PluginSay" in registry.registered_prompts()


def test_reregistering_replaces_mode(cleanup):
    cleanup.append("PluginMode")
    registry.register_prompt(_spec("PluginMode"), response_model=_Result, context_builder=_builder)
    registry.register_prompt(_spec("PluginMode"), response_model=_Result, context_builder=_builder, mode="hybrid")
    assert "PluginMode" in call.HYBRID_PROMPTS
    assert "PluginMode" not in call.READ_ONLY_PROMPTS


def test_built_in_prompt_cannot_be_replaced():
    with pytest.raises(ValueError, match="built in"):
        registry.register_prompt(
            _spec("ExplainThisElement"), response_model=_Result, context_builder=_builder
        )


def test_project_context_opens_with_the_question(tmp_path, git_identity):
    from latris.operations.init import init_project
    from latris.repo.layout import ProjectPaths

    init_project(tmp_path, name="River", statement="Is the river getting sick?")
    text = registry.project_context(ProjectPaths(tmp_path))
    assert text.startswith("Modelling question: Is the river getting sick?")
