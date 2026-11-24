"""Compose prompts: extract variables and claims from evidence, suggest variables and connections."""

from __future__ import annotations

from typing import Any

from latris.ai.context._shared import (
    ContextPack,
    _cld_loop_guidance,
    _format_block,
    _format_kv_block,
    _foundation_summary,
    _load_foundation,
    _load_substrate,
    compose_system,
)
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model
from latris.schema import ReferenceLibrary


def _build_extract_variables(paths: ProjectPaths, inputs: dict[str, Any]) -> ContextPack:
    foundation = _load_foundation(paths)
    substrate = _load_substrate(paths)
    references = load_model(ReferenceLibrary, paths.references_yaml).entries

    bibkeys = inputs.get("reference_bibkeys", [])
    matching = [r for r in references if r.bibkey in bibkeys] if bibkeys else references

    ref_items: list[dict[str, Any]] = []
    for r in matching[:30]:
        item: dict[str, Any] = {"bibkey": r.bibkey, "title": r.title}
        if r.abstract:
            item["abstract"] = r.abstract[:500]
        if r.notes:
            item["notes"] = r.notes[:200]
        ref_items.append(item)

    existing = [f'"{e.label}" ({e.kind})' for e in substrate.entities]

    from latris.ai import prompts as _prompts

    user_message = (
        f"# Project foundation\n{_foundation_summary(foundation)}"
        + _format_kv_block("References to extract from", ref_items)
        + _format_block("Existing entities (exclude these)", existing)
    )
    return ContextPack(system=compose_system(_prompts.get("ExtractVariablesFromEvidence")), user=user_message)


def _build_extract_claims(paths: ProjectPaths, inputs: dict[str, Any]) -> ContextPack:
    foundation = _load_foundation(paths)
    references = load_model(ReferenceLibrary, paths.references_yaml).entries

    node_labels = inputs.get("node_labels", [])
    bibkeys = inputs.get("reference_bibkeys", [])
    matching = [r for r in references if r.bibkey in bibkeys] if bibkeys else references

    ref_items: list[dict[str, Any]] = []
    for r in matching[:30]:
        item: dict[str, Any] = {"bibkey": r.bibkey, "title": r.title}
        if r.abstract:
            item["abstract"] = r.abstract[:500]
        if r.notes:
            item["notes"] = r.notes[:200]
        ref_items.append(item)

    from latris.ai import prompts as _prompts

    user_message = (
        f"# Project foundation\n{_foundation_summary(foundation)}"
        f"# Node labels to find claims between\n"
        + _format_block("Accepted nodes", node_labels)
        + _format_kv_block("References to extract from", ref_items)
    )
    return ContextPack(system=compose_system(_prompts.get("ExtractCausalClaims")), user=user_message)


def _build_suggest_variables(paths: ProjectPaths, inputs: dict[str, Any]) -> ContextPack:
    foundation = _load_foundation(paths)
    substrate = _load_substrate(paths)
    references = load_model(ReferenceLibrary, paths.references_yaml).entries

    exclude = set(inputs.get("exclude_labels", []))
    existing = [f'"{e.label}" ({e.kind})' for e in substrate.entities]
    focus = inputs.get("focus", "")

    from latris.ai import prompts as _prompts

    ref_titles = [f"- {r.bibkey}: {r.title}" for r in references[:20]]

    user_message = (
        f"# Project foundation\n{_foundation_summary(foundation)}"
        + (f"# Focus\n{focus}\n\n" if focus else "")
        + _format_block("Existing entities (do not repeat)", existing)
        + (_format_block("Also exclude (already accepted)", list(exclude)) if exclude else "")
        + _format_block("Reference titles (for context)", [t for t in ref_titles])
    )
    return ContextPack(system=compose_system(_prompts.get("SuggestVariables")), user=user_message)


def _build_suggest_connections(paths: ProjectPaths, inputs: dict[str, Any]) -> ContextPack:
    foundation = _load_foundation(paths)
    substrate = _load_substrate(paths)
    references = load_model(ReferenceLibrary, paths.references_yaml).entries

    node_labels = inputs.get("node_labels", [])
    focus = inputs.get("focus", "")
    existing_edges = [
        f'"{next((n.label for n in substrate.entities if n.id == e.from_id), e.from_id)}" '
        f'\u2192 "{next((n.label for n in substrate.entities if n.id == e.to_id), e.to_id)}" ({e.kind})'
        for e in substrate.edges
    ]

    ref_titles = [f"- {r.bibkey}: {r.title}" for r in references[:20]]

    loop_guidance = _cld_loop_guidance(foundation, substrate, paths)

    from latris.ai import prompts as _prompts

    user_message = (
        f"# Project foundation\n{_foundation_summary(foundation)}"
        + (f"# Focus\n{focus}\n\n" if focus else "")
        + _format_block("Accepted nodes", node_labels)
        + _format_block("Existing edges (do not repeat)", existing_edges)
        + _format_block("Reference titles (for context)", [t for t in ref_titles])
        + loop_guidance
    )
    return ContextPack(system=compose_system(_prompts.get("SuggestConnections")), user=user_message)
