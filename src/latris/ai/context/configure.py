"""Configure prompts: link polarities, and which modelling approach suits the question."""

from __future__ import annotations

from typing import Any

from latris.ai.context._shared import (
    SYSTEM_PREAMBLE,
    ContextPack,
    _format_block,
    _foundation_summary,
    _load_foundation,
    _load_substrate,
)
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model, load_model_or_default
from latris.schema import AssumptionLog, DescriptionSet, EvidenceLinkSet, PolaritySet, ReferenceLibrary


def _build_suggest_edge_polarities(paths: ProjectPaths, inputs: dict[str, Any]) -> ContextPack:
    foundation = _load_foundation(paths)
    substrate = _load_substrate(paths)
    model_type = inputs.get("model_type", "cld")
    edges_in = inputs.get("edges", [])
    source_hint = inputs.get("source_hint", "ai")

    # Existing polarity/weight assignments — let the LLM see what's already set.
    from latris.operations import formalisms

    plugin = formalisms.get(model_type)
    attr_name, attr_label = (plugin.link_attribute if plugin and plugin.link_attribute
                             else ("weight", "weight (float in [-1, +1])"))
    attr_path = paths.view_attribute_path(model_type, attr_name)
    existing_attrs = load_model_or_default(PolaritySet, attr_path)
    existing_lines = [f"  - {e.target_id}: {e.value}" for e in existing_attrs.entries]

    # Entity AND edge descriptions for richer context. Including the
    # edge's own description (previously omitted) lets the LLM align its
    # polarity rationale with the mechanism described on the edge —
    # preventing the polarity-description contradiction surfaced in the
    # 4DWW capability run, where two prompts wrote opposite causal
    # stories for the same edge.
    descs = load_model(DescriptionSet, paths.descriptions_yaml)
    desc_by_target = {d.target_id: d.value for d in descs.entries if d.attribute == "description"}
    # Node kinds, existing polarity, and per-edge provenance so the model sees
    # the full picture and can knowingly agree or disagree with an existing value
    # (disagreements are recorded, not silently overwritten, at apply time).
    kind_by_id = {en.id: en.kind for en in substrate.entities}
    existing_by_target = {e.target_id: str(e.value) for e in existing_attrs.entries}
    assumptions = load_model(AssumptionLog, paths.assumptions_yaml).entries
    assumptions_by_target: dict[str, list[str]] = {}
    for a in assumptions:
        if a.target_id:
            assumptions_by_target.setdefault(a.target_id, []).append(a.statement)
    all_evidence = load_model(EvidenceLinkSet, paths.evidence_links_yaml).entries
    bibkeys_by_target: dict[str, list[str]] = {}
    for ev in all_evidence:
        if ev.target_id:
            bibkeys_by_target.setdefault(ev.target_id, []).append(ev.bibkey)

    # Build rich edge lines with variable descriptions when available.
    edge_lines: list[str] = []
    target_ids: list[str] = []
    for e in edges_in:
        eid = e.get("edge_id", "")
        fl = e.get("from_label", "")
        tl = e.get("to_label", "")
        target_ids.append(eid)
        # Find entity IDs for descriptions.
        edge_obj = next((ed for ed in substrate.edges if ed.id == eid), None)
        from_kind = kind_by_id.get(edge_obj.from_id, "") if edge_obj else ""
        to_kind = kind_by_id.get(edge_obj.to_id, "") if edge_obj else ""
        head = f"edge_id={eid}: {fl}" + (f" ({from_kind})" if from_kind else "")
        head += f" → {tl}" + (f" ({to_kind})" if to_kind else "")
        parts = [head]
        current = existing_by_target.get(eid)
        if current is not None:
            parts.append(f"  current {attr_name}: {current} (already set — do not restate unless you disagree)")
        if edge_obj:
            from_desc = desc_by_target.get(edge_obj.from_id)
            to_desc = desc_by_target.get(edge_obj.to_id)
            if from_desc:
                parts.append(f"  from desc: {from_desc[:120]}")
            if to_desc:
                parts.append(f"  to desc: {to_desc[:120]}")
        # The edge's own description is the authoritative mechanism
        # statement; the polarity rationale must agree with it.
        edge_desc = desc_by_target.get(eid)
        if edge_desc:
            parts.append(f"  edge description: {edge_desc[:200]}")
        edge_assumptions = assumptions_by_target.get(eid, [])
        if edge_assumptions:
            parts.append("  assumptions: " + "; ".join(a[:120] for a in edge_assumptions[:3]))
        edge_bibkeys = bibkeys_by_target.get(eid, [])
        if edge_bibkeys:
            parts.append("  evidence: " + ", ".join(sorted(set(edge_bibkeys))[:6]))
        edge_lines.append("\n".join(parts))

    # Include evidence/references if source is references.
    evidence_block = ""
    if source_hint == "references":
        evidence = load_model(EvidenceLinkSet, paths.evidence_links_yaml)
        refs = load_model(ReferenceLibrary, paths.references_yaml)
        ref_by_key = {r.bibkey: r.title for r in refs.entries}
        ev_lines = []
        for ev in evidence.entries:
            if ev.target_id in target_ids:
                title = ref_by_key.get(ev.bibkey, "")
                ev_lines.append(f"  - {ev.bibkey} → {ev.target_id}/{ev.attribute}" + (f" ({title})" if title else ""))
        if ev_lines:
            evidence_block = _format_block("Evidence attached to these edges", ev_lines)

    user_message = (
        f"# Project foundation\n"
        f"{_foundation_summary(foundation)}"
        + _format_block(f"Already-set {attr_name} values (for consistency)", existing_lines)
        + f"# Edges to analyse ({len(edge_lines)})\n"
        + "\n".join(f"- {ln}" for ln in edge_lines)
        + "\n\n"
        + evidence_block
        + f"# Task\n"
        f"For each edge above, determine the {attr_label} based on the "
        "causal relationship between the from and to variables. "
        "Consider the variable names, descriptions, and any attached evidence. "
        "For each edge, return: edge_id, value, rationale, and confidence "
        "(high/medium/low). Return an AttributeSuggestionsResult."
    )

    return ContextPack(
        system=SYSTEM_PREAMBLE,
        user=user_message,
        target_ids=target_ids,
        related_attributes=[attr_name],
    )


def _build_recommend_approach(paths: ProjectPaths, inputs: dict[str, Any]) -> ContextPack:
    """Context for RecommendApproach — rank candidate formalisms against this
    project's question, evidence, AND the structure already built. Whether the
    causal structure contains feedback loops is decisive: acyclic formalisms
    (DAG, BN, ...) cannot represent loops, while a CLD is built around them.
    Each candidate's structural fit is derived from the registry. Read-only.
    """
    from latris.ai import prompts as prompt_mod
    from latris.operations.graph_analysis import causal_edges, find_all_loops
    from latris.schema.model_types import get_model_type

    foundation = _load_foundation(paths)
    substrate = _load_substrate(paths)
    loops = find_all_loops(causal_edges(substrate.edges)) if substrate.edges else []
    has_loops = len(loops) > 0
    structure = (
        f"Current model structure: {len(substrate.entities)} node(s), "
        f"{len(substrate.edges)} edge(s); "
        + (
            f"the causal structure contains {len(loops)} feedback loop(s)."
            if has_loops
            else "the causal structure is acyclic (no feedback loops)."
        )
    )

    cand_lines: list[str] = []
    for c in inputs.get("candidates", []) or []:
        cid = c.get("id", "")
        try:
            validators = get_model_type(cid).structural_validators
        except ValueError:
            validators = ()
        if "acyclicity" in validators:
            fit = (
                "REQUIRES AN ACYCLIC GRAPH — cannot represent the current feedback loops"
                if has_loops
                else "requires an acyclic graph (the current structure is acyclic, so this fits)"
            )
        elif "loops_present" in validators:
            fit = (
                "is built around feedback loops (the current structure has them)"
                if has_loops
                else "is built around feedback loops (the current structure has none yet)"
            )
        else:
            fit = "handles feedback loops"
        cand_lines.append(
            f"- {cid}: {c.get('name', cid)} — best for: {c.get('best_for', '')}; structural fit: {fit}"
        )
    cand_block = "\n".join(cand_lines) or "(no candidate formalisms supplied)"

    evidence_summary = inputs.get("evidence_summary", "") or "(no evidence summarised)"
    template = prompt_mod.get("RecommendApproach").template.format(
        candidates=cand_block, evidence_summary=evidence_summary
    )
    # Structure facts are computed here (not an input field), so they are
    # injected into the message rather than via a template placeholder.
    user = _foundation_summary(foundation) + structure + "\n\n" + template
    return ContextPack(system=SYSTEM_PREAMBLE, user=user)
