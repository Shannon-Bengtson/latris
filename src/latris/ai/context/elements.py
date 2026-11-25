"""Prompts about one element: explain it, challenge it, cite it, argue the other side, fill a field."""

from __future__ import annotations

from typing import Any

from latris.ai.context._shared import (
    SYSTEM_PREAMBLE,
    ContextPack,
    _attributes_for,
    _element_history_for,
    _existing_challenges_for_target,
    _format_block,
    _format_kv_block,
    _format_tier0_block,
    _foundation_summary,
    _load_foundation,
    _load_substrate,
    _neighbours_of_node,
    _past_interactions_for_target,
    _relevant_assumptions_exclusions,
    _resolve_target,
)
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model
from latris.schema import EvidenceLinkSet, ExclusionLog, ReferenceLibrary


def _build_explain(paths: ProjectPaths, inputs: dict[str, Any]) -> ContextPack:
    kind, target_id = _resolve_target(paths, inputs["target_id"])
    substrate = _load_substrate(paths)
    foundation = _load_foundation(paths)

    target_summary: dict[str, Any]
    neighbours: dict[str, list[dict[str, str]]] = {"inbound": [], "outbound": []}
    if kind == "node":
        entity = next(e for e in substrate.entities if e.id == target_id)
        target_summary = {
            "kind": kind,
            "id": entity.id,
            "label": entity.label,
            "entity_kind": entity.kind,
        }
        neighbours = _neighbours_of_node(substrate, target_id)
    else:
        edge = next(e for e in substrate.edges if e.id == target_id)
        src = next((e for e in substrate.entities if e.id == edge.from_id), None)
        dst = next((e for e in substrate.entities if e.id == edge.to_id), None)
        target_summary = {
            "kind": kind,
            "id": edge.id,
            "edge_kind": edge.kind,
            "from": f"{src.label if src else edge.from_id} ({edge.from_id})",
            "to": f"{dst.label if dst else edge.to_id} ({edge.to_id})",
        }

    attrs = _attributes_for(paths, target_id)
    past = _past_interactions_for_target(paths, target_id)
    asex = _relevant_assumptions_exclusions(paths)

    user_message = (
        f"# Project foundation\n"
        f"{_foundation_summary(foundation)}"
        f"# Target to explain\n"
        + "\n".join(f"- {k}: {v}" for k, v in target_summary.items())
        + "\n\n"
        + _format_kv_block("Inbound edges", neighbours["inbound"])
        + _format_kv_block("Outbound edges", neighbours["outbound"])
        + _format_block("Attributes", [f"{k} = {v!r}" for k, v in attrs.items()])
        + _format_kv_block("Prior interactions on this target", past)
        + _format_block("Relevant assumptions", asex["assumptions"])
        + _format_block("Relevant exclusions", asex["exclusions"])
        + "\n# Task\n"
        + "Produce an ExplanationResult: explain why this element is in "
        "the model, what it depends on, and how it links to the project "
        "foundation. Reference other node/edge IDs where appropriate in "
        "`referenced_ids`."
    )

    return ContextPack(
        system=SYSTEM_PREAMBLE,
        user=user_message,
        target_ids=[target_id],
        related_attributes=list(attrs.keys()),
    )


def _build_challenge(paths: ProjectPaths, inputs: dict[str, Any]) -> ContextPack:
    kind, target_id = _resolve_target(paths, inputs["target_id"])
    substrate = _load_substrate(paths)
    foundation = _load_foundation(paths)
    target_attr = inputs.get("target_attribute")

    if kind == "edge":
        edge = next(e for e in substrate.edges if e.id == target_id)
        src = next((e for e in substrate.entities if e.id == edge.from_id), None)
        dst = next((e for e in substrate.entities if e.id == edge.to_id), None)
        target_summary = {
            "kind": "edge",
            "id": edge.id,
            "edge_kind": edge.kind,
            "from": f"{src.label if src else edge.from_id}",
            "to": f"{dst.label if dst else edge.to_id}",
        }
    else:
        entity = next(e for e in substrate.entities if e.id == target_id)
        target_summary = {
            "kind": "node",
            "id": entity.id,
            "entity_kind": entity.kind,
            "label": entity.label,
        }

    attrs = _attributes_for(paths, target_id)
    challenges_here = _existing_challenges_for_target(paths, target_id)
    past = _past_interactions_for_target(paths, target_id)
    asex = _relevant_assumptions_exclusions(paths)
    history = _element_history_for(paths, target_id)

    attribute_line = f" (attribute: {target_attr})" if target_attr else ""
    user_message = (
        f"# Project foundation\n"
        f"{_foundation_summary(foundation)}"
        f"# Target to challenge{attribute_line}\n"
        + "\n".join(f"- {k}: {v}" for k, v in target_summary.items())
        + "\n\n"
        + _format_block("Current attributes on target", [f"{k} = {v!r}" for k, v in attrs.items()])
        + _format_kv_block("Existing challenges on this target", challenges_here)
        + _format_kv_block("Prior interactions on this target", past)
        + (history if history else "")
        + _format_block("Relevant assumptions", asex["assumptions"])
        + _format_block("Relevant exclusions", asex["exclusions"])
        + "\n# Task\n"
        + "Produce a ChallengeProposal arguing against this target. Focus on "
        "mechanism, confounding, directionality, and scope — not vibes. "
        "Set target_id and target_attribute to the values above. Suggest a "
        "recommended_state from: retained-unchanged, retained-with-caveat, "
        "modified, split, removed, unresolved. Include an opening_turn that "
        "a thoughtful human would engage with."
    )

    target_ids = [target_id]
    if kind == "edge":
        edge = next(e for e in substrate.edges if e.id == target_id)
        target_ids.extend([edge.from_id, edge.to_id])

    return ContextPack(
        system=SYSTEM_PREAMBLE,
        user=user_message,
        target_ids=target_ids,
        related_attributes=[target_attr] if target_attr else list(attrs.keys()),
    )


def _build_suggest_citations(paths: ProjectPaths, inputs: dict[str, Any]) -> ContextPack:
    kind, target_id = _resolve_target(paths, inputs["target_id"])
    substrate = _load_substrate(paths)
    foundation = _load_foundation(paths)
    attribute = inputs["target_attribute"]

    label = None
    if kind == "node":
        entity = next(e for e in substrate.entities if e.id == target_id)
        label = entity.label
    attrs = _attributes_for(paths, target_id)

    references = load_model(ReferenceLibrary, paths.references_yaml).entries
    existing_evidence = load_model(EvidenceLinkSet, paths.evidence_links_yaml).entries
    existing_for_target = [e for e in existing_evidence if e.target_id == target_id and e.attribute == attribute]
    exclusions = load_model(ExclusionLog, paths.exclusions_yaml).entries

    user_message = (
        f"# Project foundation\n"
        f"{_foundation_summary(foundation)}"
        f"# Target\nid: {target_id}\nattribute: {attribute}"
        + (f"\nlabel: {label}" if label else "")
        + "\n\n"
        + _format_block(
            "Current value of this attribute",
            [f"{k} = {v!r}" for k, v in attrs.items() if k == attribute],
        )
        + _format_kv_block(
            "Existing reference library (bibkey + title)",
            [{"bibkey": r.bibkey, "title": r.title, "year": r.year} for r in references],
        )
        + _format_tier0_block(references)
        + _format_kv_block(
            "Evidence already attached to this (target, attribute)",
            [{"bibkey": e.bibkey, "rationale": e.notes} for e in existing_for_target],
        )
        + _format_block("Scope exclusions (avoid out-of-scope sources)", [e.statement for e in exclusions])
        + "\n# Task\n"
        + "Produce a CitationsProposal. HARD RULES:\n"
        + "- Prefer existing references in the library. Mark them with "
        "`already_in_library=true` and DO NOT repeat their metadata in "
        "`new_references`.\n" + "- Only propose net-new references when the existing library is "
        "insufficient. For each new one include title, authors, year, "
        "and a `url` field with a real working URL to the paper (from "
        "publisher sites like sciencedirect.com, springer.com, wiley.com, "
        "tandfonline.com, mdpi.com, or government/institutional sites). "
        "References without a URL will be discarded.\n" + "- Only suggest references you are confident actually exist. "
        "Do NOT fabricate titles, authors, or URLs.\n" + "- Every bibkey in `evidence_links` MUST appear in either the "
        "existing library or `new_references`. Citation fabrication is "
        "refused by the apply layer.\n"
        + "- The Tier-0 source content block above shows what the system "
        "actually has on file for each reference. When citing a reference, "
        "ground your rationale in the abstract or full_text_excerpt content "
        "shown there. Do NOT invent claims a paper makes; if the Tier-0 "
        "block does not include enough to support the citation, omit it."
    )

    return ContextPack(
        system=SYSTEM_PREAMBLE,
        user=user_message,
        target_ids=[target_id],
        related_attributes=[attribute],
    )


def _build_steelman(paths: ProjectPaths, inputs: dict[str, Any]) -> ContextPack:
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
    challenges_here = _existing_challenges_for_target(paths, target_id)
    past = _past_interactions_for_target(paths, target_id)
    history = _element_history_for(paths, target_id)

    user_message = (
        f"# Project foundation\n"
        f"{_foundation_summary(foundation)}"
        f"# Target element\n"
        + "\n".join(f"- {k}: {v}" for k, v in target_summary.items())
        + "\n\n"
        + _format_block("Attributes", [f"{k} = {v!r}" for k, v in attrs.items()])
        + _format_kv_block("Existing challenges", challenges_here)
        + _format_kv_block("Inbound edges", neighbours.get("inbound", []))
        + _format_kv_block("Outbound edges", neighbours.get("outbound", []))
        + _format_kv_block("Prior AI interactions on this target", past)
        + ("_The interactions above are for context only — make your own "
           "judgment of the strongest opposing position._\n\n"
           if past else "")
        + (history if history else "")
        + "\n# Task\n"
        "Steelman the strongest version of the position opposing this "
        "element. This is not a replacement framing — it is a contested-view "
        "annotation. Return a SteelmanProposal with the target_id, the "
        "opposing_view text, and a rationale."
    )

    return ContextPack(
        system=SYSTEM_PREAMBLE,
        user=user_message,
        target_ids=[target_id],
        related_attributes=list(attrs.keys()),
    )


def _build_fill_provenance_field(paths: ProjectPaths, inputs: dict[str, Any]) -> ContextPack:
    """Context for the parameterized FillProvenanceField prompt.

    Threads project foundation + relevant element/row context + per-field
    guidance into the user message. The prompt is read-only from the
    orchestrator's perspective; the GUI inserts the value into the
    editable field and the user saves through the normal mutation path.
    """
    from latris.ai.prompts import field_guidance

    foundation = _load_foundation(paths)
    target_kind = inputs.get("target_kind", "entity")
    target_id = inputs.get("target_id", "")
    field_path = inputs["field_path"]
    row_id = inputs.get("row_id", "")
    current_value = inputs.get("current_value", "")

    target_block = ""
    related_attrs: list[str] = [field_path]
    if target_kind == "entity" and target_id:
        substrate = _load_substrate(paths)
        entity = next((e for e in substrate.entities if e.id == target_id), None)
        if entity is not None:
            neighbours = _neighbours_of_node(substrate, target_id)
            attrs = _attributes_for(paths, target_id)
            target_block = (
                f"# Target node\n"
                f"- label: {entity.label}\n"
                f"- kind: {entity.kind}\n"
                f"- id: {entity.id}\n\n"
                + _format_kv_block("Inbound edges", neighbours["inbound"])
                + _format_kv_block("Outbound edges", neighbours["outbound"])
                + _format_block("Existing attributes", [f"{k} = {v!r}" for k, v in attrs.items()])
            )
            related_attrs.extend(attrs.keys())
    elif target_kind == "edge" and target_id:
        substrate = _load_substrate(paths)
        edge = next((e for e in substrate.edges if e.id == target_id), None)
        if edge is not None:
            src = next((e for e in substrate.entities if e.id == edge.from_id), None)
            dst = next((e for e in substrate.entities if e.id == edge.to_id), None)
            attrs = _attributes_for(paths, target_id)
            target_block = (
                f"# Target edge\n"
                f"- from: {src.label if src else edge.from_id}\n"
                f"- to: {dst.label if dst else edge.to_id}\n"
                f"- kind: {edge.kind}\n"
                f"- id: {edge.id}\n\n"
                + _format_block("Existing attributes", [f"{k} = {v!r}" for k, v in attrs.items()])
            )
            related_attrs.extend(attrs.keys())
    else:
        target_block = "# Target\nProject-level field.\n\n"

    row_block = ""
    if row_id:
        row_block = f"# Provenance row\n- row_id: {row_id}\n\n"

    guidance = field_guidance(target_kind, field_path)
    current_block = f"Current value: {current_value!r}\n\n" if current_value else ""

    user_message = (
        f"{_foundation_summary(foundation)}"
        + target_block
        + row_block
        + current_block
        + f"# Field to fill\n{field_path}\n\n"
        + f"# Guidance\n{guidance}\n\n"
        + "# Task\n"
        + "Suggest a value for this field. Return a FillFieldProposal "
        + "with `value`, `rationale` (one-sentence reasoning), and "
        + "`confidence` (low/medium/high)."
    )

    return ContextPack(
        system=SYSTEM_PREAMBLE,
        user=user_message,
        target_ids=[target_id] if target_id else [],
        related_attributes=related_attrs,
    )
