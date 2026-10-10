"""Fixed prompt-chain definitions.

A chain is an ordered sequence of prompts that execute one after another.
Each step's inputs can depend on the trigger inputs and prior step outcomes.
The frontend drives advancement step-by-step (pull, not push).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from latris.ai.call import CallOutcome


@dataclass(frozen=True)
class ChainStep:
    """One step in a prompt chain."""

    prompt_name: str
    input_builder: Callable[[dict[str, Any], list[CallOutcome]], dict[str, Any]]


@dataclass(frozen=True)
class ChainSpec:
    """A fixed sequence of prompt steps."""

    name: str
    title: str
    description: str
    steps: tuple[ChainStep, ...]

    @property
    def step_count(self) -> int:
        return len(self.steps)


# ---------- input builders ----------


def _draft_inputs(trigger: dict[str, Any], _prior: list[CallOutcome]) -> dict[str, Any]:
    """Pass trigger inputs directly to DraftConceptualModel."""
    return trigger


def _assumptions_from_draft(
    trigger: dict[str, Any],
    prior: list[CallOutcome],
) -> dict[str, Any]:
    """After a draft is applied, generate assumptions for the first created entity."""
    # Use the first applied ID from the draft step as the target
    if prior and prior[0].applied_ids:
        return {"target_id": prior[0].applied_ids[0]}
    # Fallback: use focus as a search hint (won't resolve, but context builder
    # will surface the error clearly)
    return {"target_id": trigger.get("focus", "")}


def _citations_from_draft(
    trigger: dict[str, Any],
    prior: list[CallOutcome],
) -> dict[str, Any]:
    """After assumptions, suggest citations for the first created entity."""
    # Find the first entity ID from the draft step
    target_id = ""
    if prior and prior[0].applied_ids:
        target_id = prior[0].applied_ids[0]
    return {"target_id": target_id, "target_attribute": "description"}


def _connections_inputs(trigger: dict[str, Any], _prior: list[CallOutcome]) -> dict[str, Any]:
    """Pass trigger inputs directly to FindNewConnections."""
    return trigger


def _assumptions_from_connections(
    trigger: dict[str, Any],
    prior: list[CallOutcome],
) -> dict[str, Any]:
    """After connections are applied, generate assumptions for the first new edge."""
    if prior and prior[0].applied_ids:
        return {"target_id": prior[0].applied_ids[0]}
    return {"target_id": ""}


# ---------- chain library ----------


CHAIN_LIBRARY: dict[str, ChainSpec] = {
    "draft-model": ChainSpec(
        name="draft-model",
        title="Draft Conceptual Model",
        description="Draft a model, then generate assumptions and suggest citations.",
        steps=(
            ChainStep("DraftConceptualModel", _draft_inputs),
            ChainStep("GenerateAssumptions", _assumptions_from_draft),
            ChainStep("SuggestCitations", _citations_from_draft),
        ),
    ),
    "find-connections": ChainSpec(
        name="find-connections",
        title="Find & Document Connections",
        description="Find new connections, then generate assumptions for them.",
        steps=(
            ChainStep("FindNewConnections", _connections_inputs),
            ChainStep("GenerateAssumptions", _assumptions_from_connections),
        ),
    ),
}


def get_chain(name: str) -> ChainSpec:
    if name not in CHAIN_LIBRARY:
        known = ", ".join(sorted(CHAIN_LIBRARY.keys()))
        raise KeyError(f"unknown chain {name!r}. Known chains: {known}")
    return CHAIN_LIBRARY[name]


def list_chains() -> list[ChainSpec]:
    return sorted(CHAIN_LIBRARY.values(), key=lambda c: c.name)
