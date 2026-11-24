"""Prompts that propose provenance records: assumptions, decisions, exclusions, questions."""

from __future__ import annotations

from typing import Any

from latris.ai.context._shared import (
    SYSTEM_PREAMBLE,
    ContextPack,
    _attributes_for,
    _format_block,
    _format_kv_block,
    _foundation_summary,
    _load_foundation,
    _load_substrate,
    _neighbours_of_node,
    _past_interactions_for_target,
    _relevant_assumptions_exclusions,
    _resolve_target,
)
from latris.repo.layout import ProjectPaths


def _build_generate_assumptions(paths: ProjectPaths, inputs: dict[str, Any]) -> ContextPack:
    kind, target_id = _resolve_target(paths, inputs["target_id"])
    substrate = _load_substrate(paths)
    foundation = _load_foundation(paths)

    if kind == "node":
        entity = next(e for e in substrate.entities if e.id == target_id)
        target_summary = {"kind": "node", "id": entity.id, "label": entity.label, "entity_kind": entity.kind}
        neighbours = _neighbours_of_node(substrate, target_id)
    else:
        edge = next(e for e in substrate.edges if e.id == target_id)
        src = next((e for e in substrate.entities if e.id == edge.from_id), None)
        dst = next((e for e in substrate.entities if e.id == edge.to_id), None)
        target_summary = {
            "kind": "edge",
            "id": edge.id,
            "edge_kind": edge.kind,
            "from": src.label if src else edge.from_id,
            "to": dst.label if dst else edge.to_id,
        }
        neighbours = {"inbound": [], "outbound": []}

    attrs = _attributes_for(paths, target_id)
    asex = _relevant_assumptions_exclusions(paths)

    user_message = (
        f"# Project foundation\n"
        f"{_foundation_summary(foundation)}"
        f"# Target element\n"
        + "\n".join(f"- {k}: {v}" for k, v in target_summary.items())
        + "\n\n"
        + _format_block("Attributes", [f"{k} = {v!r}" for k, v in attrs.items()])
        + _format_kv_block("Inbound edges", neighbours.get("inbound", []))
        + _format_kv_block("Outbound edges", neighbours.get("outbound", []))
        + _format_block("Existing assumptions (avoid duplicates)", asex["assumptions"])
        + "\n# Task\n"
        "Identify 2–5 key assumptions underlying this element. Each "
        "assumption should be specific, falsifiable, and relevant to the "
        "modelling question. Include a rationale explaining why the "
        "assumption is necessary. Do NOT duplicate existing assumptions. "
        "Return an AssumptionsProposal."
    )

    return ContextPack(
        system=SYSTEM_PREAMBLE,
        user=user_message,
        target_ids=[target_id],
        related_attributes=list(attrs.keys()),
    )


def _build_suggest_decisions(paths: ProjectPaths, inputs: dict[str, Any]) -> ContextPack:
    kind, target_id = _resolve_target(paths, inputs["target_id"])
    substrate = _load_substrate(paths)
    foundation = _load_foundation(paths)

    if kind == "node":
        entity = next(e for e in substrate.entities if e.id == target_id)
        target_summary = {"kind": "node", "id": entity.id, "label": entity.label, "entity_kind": entity.kind}
        neighbours = _neighbours_of_node(substrate, target_id)
    else:
        edge = next(e for e in substrate.edges if e.id == target_id)
        src = next((e for e in substrate.entities if e.id == edge.from_id), None)
        dst = next((e for e in substrate.entities if e.id == edge.to_id), None)
        target_summary = {
            "kind": "edge",
            "id": edge.id,
            "edge_kind": edge.kind,
            "from": src.label if src else edge.from_id,
            "to": dst.label if dst else edge.to_id,
        }
        neighbours = {"inbound": [], "outbound": []}

    attrs = _attributes_for(paths, target_id)
    asex = _relevant_assumptions_exclusions(paths)

    user_message = (
        f"# Project foundation\n"
        f"{_foundation_summary(foundation)}"
        f"# Target element\n"
        + "\n".join(f"- {k}: {v}" for k, v in target_summary.items())
        + "\n\n"
        + _format_block("Attributes", [f"{k} = {v!r}" for k, v in attrs.items()])
        + _format_kv_block("Inbound edges", neighbours.get("inbound", []))
        + _format_kv_block("Outbound edges", neighbours.get("outbound", []))
        + _format_block("Existing assumptions", asex["assumptions"])
        + _format_block("Existing exclusions", asex["exclusions"])
        + "\n# Task\n"
        "Identify 1–4 key modelling decisions embedded in this element. "
        "Focus on why this representation was chosen over alternatives, "
        "what trade-offs were accepted, and what scope boundaries apply. "
        "Each decision must have a clear rationale. "
        "Return a DecisionsProposal."
    )

    return ContextPack(
        system=SYSTEM_PREAMBLE,
        user=user_message,
        target_ids=[target_id],
        related_attributes=list(attrs.keys()),
    )


def _build_suggest_exclusions(paths: ProjectPaths, inputs: dict[str, Any]) -> ContextPack:
    substrate = _load_substrate(paths)
    foundation = _load_foundation(paths)
    asex = _relevant_assumptions_exclusions(paths)

    entity_lines = [f"  - {e.id}: {e.label} ({e.kind})" for e in substrate.entities]
    edge_lines = []
    by_id = {e.id: e for e in substrate.entities}
    for edge in substrate.edges:
        src = by_id.get(edge.from_id)
        dst = by_id.get(edge.to_id)
        edge_lines.append(
            f"  - {edge.id}: {src.label if src else edge.from_id} → {dst.label if dst else edge.to_id} ({edge.kind})"
        )

    user_message = (
        f"# Project foundation\n"
        f"{_foundation_summary(foundation)}"
        f"# Current model entities\n" + "\n".join(entity_lines) + "\n\n"
        "# Current model edges\n"
        + "\n".join(edge_lines)
        + "\n\n"
        + _format_block("Existing exclusions (avoid duplicates)", asex["exclusions"])
        + _format_block("Existing assumptions", asex["assumptions"])
        + "\n# Task\n"
        "Identify 2–5 scope exclusions for this model. Focus on: adjacent "
        "phenomena intentionally not modelled, temporal/spatial boundaries, "
        "simplifications that omit complexity, and validity limits. "
        "Each exclusion must have a rationale. Do NOT duplicate existing "
        "exclusions. Return an ExclusionsProposal."
    )

    return ContextPack(
        system=SYSTEM_PREAMBLE,
        user=user_message,
    )


def _build_raise_questions(paths: ProjectPaths, inputs: dict[str, Any]) -> ContextPack:
    kind, target_id = _resolve_target(paths, inputs["target_id"])
    substrate = _load_substrate(paths)
    foundation = _load_foundation(paths)

    if kind == "node":
        entity = next(e for e in substrate.entities if e.id == target_id)
        target_summary = {"kind": "node", "id": entity.id, "label": entity.label, "entity_kind": entity.kind}
        neighbours = _neighbours_of_node(substrate, target_id)
    else:
        edge = next(e for e in substrate.edges if e.id == target_id)
        src = next((e for e in substrate.entities if e.id == edge.from_id), None)
        dst = next((e for e in substrate.entities if e.id == edge.to_id), None)
        target_summary = {
            "kind": "edge",
            "id": edge.id,
            "edge_kind": edge.kind,
            "from": src.label if src else edge.from_id,
            "to": dst.label if dst else edge.to_id,
        }
        neighbours = {"inbound": [], "outbound": []}

    attrs = _attributes_for(paths, target_id)
    past = _past_interactions_for_target(paths, target_id)

    user_message = (
        f"# Project foundation\n"
        f"{_foundation_summary(foundation)}"
        f"# Target element\n"
        + "\n".join(f"- {k}: {v}" for k, v in target_summary.items())
        + "\n\n"
        + _format_block("Attributes", [f"{k} = {v!r}" for k, v in attrs.items()])
        + _format_kv_block("Inbound edges", neighbours.get("inbound", []))
        + _format_kv_block("Outbound edges", neighbours.get("outbound", []))
        + _format_kv_block("Prior interactions on this target", past)
        + "\n# Task\n"
        "Identify 2–5 unresolved structural questions about this element. "
        "Focus on: uncertain mechanisms, missing evidence, contested "
        "relationships, and areas where expert input is needed. "
        "Questions should be specific and actionable. "
        "Return a QuestionsProposal."
    )

    return ContextPack(
        system=SYSTEM_PREAMBLE,
        user=user_message,
        target_ids=[target_id],
        related_attributes=list(attrs.keys()),
    )
