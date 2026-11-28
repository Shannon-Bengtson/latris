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
from latris.schema.ids import IDKind, parse_id


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


def _first_element(prior: list[CallOutcome], kinds: tuple[IDKind, ...]) -> str | None:
    """The first id of the earliest-preferred kind among the first step's applied ids.

    A step's ``applied_ids`` mixes the elements it created with the provenance it
    bound to them (assumption ids among them), and a reused node is not listed at
    all, so the first id is not always an element.
    """
    if not prior:
        return None
    by_kind: dict[str, str] = {}
    for applied in prior[0].applied_ids:
        try:
            kind, _ = parse_id(applied)
        except ValueError:
            continue
        by_kind.setdefault(kind, applied)
    return next((by_kind[k] for k in kinds if k in by_kind), None)


def _draft_inputs(trigger: dict[str, Any], _prior: list[CallOutcome]) -> dict[str, Any]:
    """Pass trigger inputs directly to DraftConceptualModel."""
    return trigger


def _assumptions_from_draft(
    trigger: dict[str, Any],
    prior: list[CallOutcome],
) -> dict[str, Any]:
    """After a draft is applied, generate assumptions for the first created node (else edge)."""
    target_id = _first_element(prior, ("node", "edge"))
    if target_id is not None:
        return {"target_id": target_id}
    # Fallback: use focus as a search hint (won't resolve, but context builder
    # will surface the error clearly)
    return {"target_id": trigger.get("focus", "")}


def _citations_from_draft(
    trigger: dict[str, Any],
    prior: list[CallOutcome],
) -> dict[str, Any]:
    """After assumptions, suggest citations for the first created node (else edge)."""
    target_id = _first_element(prior, ("node", "edge")) or ""
    return {"target_id": target_id, "target_attribute": "description"}


def _connections_inputs(trigger: dict[str, Any], _prior: list[CallOutcome]) -> dict[str, Any]:
    """Pass trigger inputs directly to FindNewConnections."""
    return trigger


def _assumptions_from_connections(
    trigger: dict[str, Any],
    prior: list[CallOutcome],
) -> dict[str, Any]:
    """After connections are applied, generate assumptions for the first new edge."""
    return {"target_id": _first_element(prior, ("edge",)) or ""}


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
