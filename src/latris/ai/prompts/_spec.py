"""What a prompt is: ``PromptSpec``, and the types its fields and its inputs are written in."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel

from latris.schema.model_types import get_model_type

PromptMode = Literal["mutating", "read_only", "hybrid", "server_transformed"]


def _validate_model_type(value: str) -> str:
    """Validate against the model-type registry; raises ValueError on unknown ID.

    Mirrors the pattern used by ``View.kind`` in ``schema/views.py`` so prompt
    inputs reject typos at construction time rather than at downstream
    string-comparison sites.
    """
    get_model_type(value)
    return value


ModelTypeStr = Annotated[str, AfterValidator(_validate_model_type)]
"""A model-type identifier validated against ``MODEL_TYPE_REGISTRY``."""


PackName = Literal["client", "audit", "review", "workshop", "publication"]
"""Pack names mirroring the keys of ``exporters/packs.py:PACKS``."""


ViewKind = Literal["cld", "dag"]
"""Stable formal-view kinds the projector supports."""


class PromptScope(StrEnum):
    """Whether the prompt operates on the whole model or a selected element."""

    model = "model"
    element = "element"


class PromptIntent(StrEnum):
    """What kind of result the prompt produces."""

    insight = "insight"  # read-only analysis — displayed inline
    action = "action"  # mutating proposal — preview → approve/reject → apply
    workflow = "workflow"  # special multi-turn interaction (e.g. elicitation)


@dataclass(frozen=True)
class PromptSpec:
    name: str
    title: str
    description: str
    inputs: type[BaseModel]
    template: str
    output_hint: str
    scope: PromptScope = PromptScope.model
    intent: PromptIntent = PromptIntent.insight
    # The structured-output schema this prompt returns. Attached below via
    # ``_wire`` so a prompt is defined in ONE place (the spec) rather than
    # smeared across a separate ``RESPONSE_MODELS`` dict. Optional only so the
    # per-prompt literals can omit it; ``_wire`` guarantees every live spec
    # carries one (guard test: tests/ai/test_prompt_contract.py).
    response_model: type[BaseModel] | None = None
    # Per-operation temperature override. ``None`` → use the project/config
    # default. Extraction/transformation ops run cool for consistent
    # granularity; generative critique keeps the default.
    temperature: float | None = None
    # How a call's result is used: "mutating" (its proposal is applied),
    # "read_only" (shown, never applied), "hybrid" (prose plus a bounded
    # proposal) or "server_transformed" (the server turns it into the real
    # proposal). Attached by ``_wire`` from ``_MODES``.
    mode: PromptMode = "mutating"
