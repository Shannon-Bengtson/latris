"""AI interrogation prompts: the completeness gate, adversarial edge checks, source verification."""

from __future__ import annotations

from typing import Any

from latris.ai.context._shared import (
    SYSTEM_PREAMBLE,
    ContextPack,
    _element_history_for,
    _format_block,
    _format_kv_block,
    _foundation_summary,
    _load_foundation,
    _load_substrate,
    _past_interactions_for_target,
    _project_activity_summary,
)
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model, load_model_or_default
from latris.schema import DescriptionSet, EvidenceLinkSet, PolaritySet, ReferenceLibrary


def _load_reference_for_verify(bibkey: str, paths: ProjectPaths):
    """Helper used by both `_build_verify_claim_against_source` and
    `VerifyClaimAgainstSourceProposal.apply` to fetch the Reference by
    bibkey. Raises ValueError if missing.
    """
    refs = load_model(ReferenceLibrary, paths.references_yaml)
    ref = next((r for r in refs.entries if r.bibkey == bibkey), None)
    if ref is None:
        raise ValueError(f"unknown reference {bibkey!r}")
    return ref


def _build_verify_claim_against_source(paths: ProjectPaths, inputs: dict[str, Any]) -> ContextPack:
    """Context for the AI interrogation Phase 4a VerifyClaimAgainstSource prompt.

    Element-scope: pulls the EvidenceLink, the Reference's source
    snapshot extract (must be present — otherwise we raise before
    paying for an LLM call), and the claim text. The user message
    instructs the model to find a verbatim quote in the extract or
    return a non-supports verdict.
    """
    foundation = _load_foundation(paths)
    substrate = _load_substrate(paths)
    target_id = inputs.get("target_id")
    attribute = inputs.get("attribute", "")
    bibkey = inputs.get("bibkey", "")
    claim = inputs.get("claim", "")

    evidence = load_model(EvidenceLinkSet, paths.evidence_links_yaml)
    link = next(
        (
            e
            for e in evidence.entries
            if e.target_id == target_id and e.attribute == attribute and e.bibkey == bibkey
        ),
        None,
    )
    if link is None:
        raise ValueError(
            f"no evidence link {bibkey!r} on {target_id or 'model'}/{attribute}"
        )

    ref = _load_reference_for_verify(bibkey, paths)
    snapshot = ref.source_snapshot

    label_by_id = {e.id: e.label for e in substrate.entities}
    target_label = (
        label_by_id.get(target_id, target_id) if target_id else "(model-level)"
    )

    # Phase 4b: prefer the per-bibkey full-text artefact when present;
    # fall back to source_snapshot.extract (Phase 4a path). The model
    # gets the top-k chunks scored by keyword overlap with the claim.
    extract_path = paths.references_extract_path(bibkey)
    if extract_path.exists():
        from latris.operations._chunking import chunk_text, top_k

        full_text = extract_path.read_text(encoding="utf-8")
        chunks = chunk_text(full_text)
        top = top_k(chunks, claim, k=3)
        chunk_block = "\n\n".join(
            f"[chunk {i+1} chunk_hash={c.content_hash} offset={c.offset}]\n"
            f">>>\n{c.text}\n<<<"
            for i, c in enumerate(top)
        )
        text_block = (
            "# Source chunks (the ONLY text you may quote from — the apply-time "
            "validator will check the verbatim quote against the chunk whose "
            "chunk_hash matches what you reference)\n"
            + chunk_block
        )
        snapshot_meta = (
            f"  snapshot kind: full_text_excerpt (chunked from {extract_path.name})\n"
            f"  total chunks: {len(chunks)}, sent: {len(top)}\n"
        )
    else:
        if snapshot is None or not snapshot.extract:
            raise ValueError(
                f"reference {bibkey!r} has no source_snapshot.extract — fetch "
                "or paste a source snapshot before running VerifyClaimAgainstSource"
            )
        text_block = (
            "# Source-snapshot extract (the ONLY text you may quote from)\n"
            ">>>\n" + snapshot.extract + "\n<<<"
        )
        snapshot_meta = (
            f"  snapshot kind: {snapshot.kind}\n"
            f"  snapshot retrieval_url: {snapshot.retrieval_url}\n"
        )

    past = _past_interactions_for_target(paths, target_id) if target_id else []
    history = _element_history_for(paths, target_id)

    user_message = (
        f"# Project foundation\n"
        f"{_foundation_summary(foundation)}"
        + "# Evidence link\n"
        + f"  target: {target_label} ({target_id or 'model'})\n"
        + f"  attribute: {attribute}\n"
        + f"  bibkey: {bibkey}\n"
        + f"  current verdict: {link.support_verdict}\n"
        + f"  source_access: {link.source_access}\n"
        + "\n"
        + f"# Claim being verified\n{claim}\n\n"
        + f"# Reference: {ref.title}"
        + (f" ({ref.year})" if ref.year else "")
        + "\n"
        + f"  bibkey: {bibkey}\n"
        + snapshot_meta
        + "\n"
        + text_block
        + "\n\n"
        + _format_kv_block("Prior AI interactions on this target", past)
        + ("_The interactions above are for context only — reviewers have "
           "already adopted or rejected past proposals. You are not bound by "
           "those framings; the verbatim-quote check is the apply-time "
           "audit invariant._\n\n"
           if past else "")
        + (history if history else "")
        + "# Task\n"
        "Decide one of supports / contradicts / orthogonal / "
        "insufficient_extract. On `supports`, include a verbatim quote "
        "drawn from the source above (the apply-time validator will "
        "check character-for-character). Return a "
        "VerifyClaimAgainstSourceProposal."
    )

    return ContextPack(
        system=SYSTEM_PREAMBLE,
        user=user_message,
        target_ids=[target_id] if target_id else [],
        related_attributes=[attribute],
    )


def _build_challenge_edge(paths: ProjectPaths, inputs: dict[str, Any]) -> ContextPack:
    """Context for the AI interrogation Phase 3b ChallengeEdge prompt.

    Element-scope: pulls one edge plus its source/target labels and
    descriptions, current polarity (CLD), evidence coverage, and the
    edge's own description (mechanism). The AI's job is to argue
    against the edge and pick a single repair action.
    """
    foundation = _load_foundation(paths)
    substrate = _load_substrate(paths)
    edge_id = inputs.get("edge_id", "")
    model_type = inputs.get("model_type", "cld")
    edge = next((e for e in substrate.edges if e.id == edge_id), None)
    if edge is None:
        raise ValueError(f"unknown edge_id {edge_id!r}")

    label_by_id = {e.id: e.label for e in substrate.entities}
    descs = load_model(DescriptionSet, paths.descriptions_yaml)
    desc_by_target = {d.target_id: d.value for d in descs.entries if d.attribute == "description"}
    polarity_path = paths.view_attribute_path(model_type, "polarity")
    polarities = load_model_or_default(PolaritySet, polarity_path)
    polarity_by_target = {p.target_id: p.value for p in polarities.entries}

    src_label = label_by_id.get(edge.from_id, edge.from_id)
    dst_label = label_by_id.get(edge.to_id, edge.to_id)
    polarity = polarity_by_target.get(edge.id, "")
    edge_desc = desc_by_target.get(edge.id, "")
    src_desc = desc_by_target.get(edge.from_id, "")
    dst_desc = desc_by_target.get(edge.to_id, "")

    evidence_lines: list[str] = []
    refs = load_model(ReferenceLibrary, paths.references_yaml)
    ref_titles = {r.bibkey: r.title for r in refs.entries}
    evidence = load_model(EvidenceLinkSet, paths.evidence_links_yaml)
    for ev in evidence.entries:
        if ev.target_id == edge.id:
            title = ref_titles.get(ev.bibkey, "")
            evidence_lines.append(
                f"- {ev.bibkey} ({title}) → attribute={ev.attribute} "
                f"verdict={ev.support_verdict} access={ev.source_access}"
            )

    edge_block = (
        f"edge_id={edge.id}\n"
        f'  "{src_label}" → "{dst_label}" (kind={edge.kind})'
        + (f"\n  polarity: {polarity}" if polarity else "")
        + (f"\n  description: {edge_desc[:300]}" if edge_desc else "")
        + (f"\n  source desc: {src_desc[:200]}" if src_desc else "")
        + (f"\n  target desc: {dst_desc[:200]}" if dst_desc else "")
    )

    past = _past_interactions_for_target(paths, edge.id)
    history = _element_history_for(paths, edge.id)

    user_message = (
        f"# Project foundation\n"
        f"{_foundation_summary(foundation)}"
        + f"# Edge under challenge\n{edge_block}\n\n"
        + _format_block(
            f"Evidence attached to this edge ({len(evidence_lines)})",
            evidence_lines or ["(no evidence attached)"],
        )
        + _format_kv_block("Prior AI interactions on this edge", past)
        + ("_The interactions above are for context only — reviewers have "
           "already adopted or rejected past proposals. You are not bound by "
           "those framings; make your own judgment from the current state._\n\n"
           if past else "")
        + (history if history else "")
        + "# Task\n"
        "Argue against the edge as encoded. Pick ONE action — "
        "evidence_search / polarity_flip / remove — with rationale and "
        "confidence. The summary field is the critique prose itself. "
        "Return a ChallengeEdgeProposal."
    )

    return ContextPack(
        system=SYSTEM_PREAMBLE,
        user=user_message,
        target_ids=[edge.id],
        related_attributes=["polarity", "description"],
    )


def _build_evidence_demote(paths: ProjectPaths, inputs: dict[str, Any]) -> ContextPack:
    """Context for the AI interrogation Phase 3b EvidenceDemote prompt.

    Element-scope: pulls one (target, attribute, bibkey) link plus the
    reference's title / abstract / source_snapshot (when present) so
    the AI can reason about whether the source actually supports the
    specific claim.
    """
    foundation = _load_foundation(paths)
    substrate = _load_substrate(paths)
    target_id = inputs.get("target_id")
    attribute = inputs.get("attribute", "")
    bibkey = inputs.get("bibkey", "")

    refs = load_model(ReferenceLibrary, paths.references_yaml)
    ref = next((r for r in refs.entries if r.bibkey == bibkey), None)
    evidence = load_model(EvidenceLinkSet, paths.evidence_links_yaml)
    link = next(
        (
            e
            for e in evidence.entries
            if e.target_id == target_id and e.attribute == attribute and e.bibkey == bibkey
        ),
        None,
    )
    if link is None:
        raise ValueError(
            f"no evidence link {bibkey!r} on {target_id or 'model'}/{attribute}"
        )

    label_by_id = {e.id: e.label for e in substrate.entities}
    target_label = label_by_id.get(target_id, target_id) if target_id else "(model-level)"

    ref_lines: list[str] = []
    if ref is None:
        ref_lines.append(f"(no Reference record for {bibkey!r} — title-only)")
    else:
        ref_lines.append(f"title: {ref.title}")
        if ref.year:
            ref_lines.append(f"year: {ref.year}")
        if ref.abstract:
            ref_lines.append(f"abstract:\n{ref.abstract[:800]}")
        snapshot = getattr(ref, "source_snapshot", None)
        if snapshot is not None and snapshot.extract:
            label = "landing-page" if snapshot.kind == "landing_page_text" else "abstract / chunk"
            ref_lines.append(f"source_snapshot ({label}):\n{snapshot.extract[:1000]}")

    past = _past_interactions_for_target(paths, target_id) if target_id else []
    history = _element_history_for(paths, target_id)

    user_message = (
        f"# Project foundation\n"
        f"{_foundation_summary(foundation)}"
        + "# Evidence link\n"
        + f"  target: {target_label} ({target_id or 'model'})\n"
        + f"  attribute: {attribute}\n"
        + f"  bibkey: {bibkey}\n"
        + f"  current verdict: {link.support_verdict}\n"
        + f"  source_access: {link.source_access}\n"
        + (f"  user notes: {link.notes[:300]}\n" if link.notes else "")
        + "\n"
        + _format_block("Reference", ref_lines)
        + _format_kv_block("Prior AI interactions on this target", past)
        + ("_The interactions above are for context only — reviewers have "
           "already adopted or rejected past proposals. You are not bound by "
           "those framings; make your own judgment from the source itself._\n\n"
           if past else "")
        + (history if history else "")
        + "# Task\n"
        "Decide whether the source actually supports the specific "
        "claim, or only topically overlaps with it. Pick ONE action — "
        "change_verdict (with new_verdict) or remove — with rationale "
        "and confidence. Return an EvidenceDemoteProposal."
    )

    return ContextPack(
        system=SYSTEM_PREAMBLE,
        user=user_message,
        target_ids=[target_id] if target_id else [],
        related_attributes=[attribute],
    )


def _build_edge_reclassify(paths: ProjectPaths, inputs: dict[str, Any]) -> ContextPack:
    """Context for the AI interrogation Phase 3a EdgeReclassify prompt.

    Enumerates every edge with its current kind, source/target labels,
    polarity (when known), and any description that might explain the
    relationship. The AI's job is to look at this list and propose
    keep / retag / remove with rationale.
    """
    foundation = _load_foundation(paths)
    substrate = _load_substrate(paths)
    model_type = inputs.get("model_type", "cld")

    label_by_id = {e.id: e.label for e in substrate.entities}
    descs = load_model(DescriptionSet, paths.descriptions_yaml)
    desc_by_target = {d.target_id: d.value for d in descs.entries if d.attribute == "description"}
    polarity_path = paths.view_attribute_path(model_type, "polarity")
    polarities = load_model_or_default(PolaritySet, polarity_path)
    polarity_by_target = {p.target_id: p.value for p in polarities.entries}

    edge_lines: list[str] = []
    target_ids: list[str] = []
    for e in substrate.edges:
        target_ids.append(e.id)
        src = label_by_id.get(e.from_id, e.from_id)
        dst = label_by_id.get(e.to_id, e.to_id)
        polarity = polarity_by_target.get(e.id, "")
        polarity_block = f" polarity={polarity}" if polarity else ""
        line = f'edge_id={e.id}: "{src}" → "{dst}" (kind={e.kind}{polarity_block})'
        desc = desc_by_target.get(e.id)
        if desc:
            line += f"\n  description: {desc[:200]}"
        edge_lines.append(line)

    activity = _project_activity_summary(paths)

    user_message = (
        f"# Project foundation\n"
        f"{_foundation_summary(foundation)}"
        + (activity + "\n" if activity else "")
        + f"# Edges to reclassify ({len(edge_lines)})\n"
        + "\n".join(f"- {ln}" for ln in edge_lines)
        + "\n\n"
        + "# Task\n"
        "For each edge above decide keep / retag / remove with a "
        "rationale and confidence. Retag targets are constrained to "
        "causal | decision_rule | governance | definitional. Return an "
        "EdgeReclassifyProposal with the per-edge actions and a "
        "summary paragraph naming the worst misclassifications."
    )

    return ContextPack(
        system=SYSTEM_PREAMBLE,
        user=user_message,
        target_ids=target_ids,
        related_attributes=["kind"],
    )


def _build_completeness_gate(paths: ProjectPaths, inputs: dict[str, Any]) -> ContextPack:
    """Context builder for AI interrogation Phase 2c CompletenessGate."""
    from latris.operations.completeness import load_report
    from latris.operations.interpret import coverage_ratio
    from latris.schema import ExclusionLog

    foundation = _load_foundation(paths)
    substrate = _load_substrate(paths)
    model_type = inputs.get("model_type", "cld")
    claims = inputs.get("claims", [])

    cited, total, ratio = coverage_ratio(model_type, paths)

    entity_labels = [f"- {e.label} ({e.kind})" for e in substrate.entities]

    # Prior gate state — tells the AI what NOT to re-propose.
    prior_report = load_report(model_type, root=paths.root)
    excluded_rows = [
        f"- {mv.name} (excluded; rationale recorded)"
        for mv in prior_report.entries
        if mv.disposition == "excluded"
    ]
    dismissed_rows = [
        f"- {mv.name} (dismissed)"
        for mv in prior_report.entries
        if mv.disposition == "dismissed"
    ]
    open_rows = [
        f"- {mv.name} (severity={mv.severity})"
        for mv in prior_report.entries
        if mv.disposition == "open"
    ]
    added_rows = [
        f"- {mv.name} (already added to model as {mv.added_entity_id or 'an entity'})"
        for mv in prior_report.entries
        if mv.disposition == "added_to_model"
    ]

    # Project-wide ExclusionLog statements (legacy / human-authored).
    log = (
        load_model(ExclusionLog, paths.exclusions_yaml)
        if paths.exclusions_yaml.exists()
        else ExclusionLog()
    )
    project_exclusions = [f"- {ex.statement}" for ex in log.entries]
    activity = _project_activity_summary(paths)

    user_message = (
        f"# Project foundation\n{_foundation_summary(foundation)}"
        + (activity + "\n" if activity else "")
        + f"# Active model type\n{model_type}\n\n"
        + f"# Coverage at gate-time\n{cited}/{total} elements cited "
        + f"({ratio:.0%}).\n\n"
        + _format_block("Currently modelled entities", entity_labels)
        + _format_block(
            "Claims the upcoming Interpret* will produce",
            [f'"{c}"' for c in claims],
        )
        + _format_block("Prior excluded missing variables (DO NOT re-propose)", excluded_rows)
        + _format_block("Prior dismissed missing variables (DO NOT re-propose)", dismissed_rows)
        + _format_block(
            "Prior open missing variables (update or supersede; do not duplicate)",
            open_rows,
        )
        + _format_block("Prior added-to-model rows (already resolved)", added_rows)
        + _format_block("Project-wide scope exclusions (respect)", project_exclusions)
        + "\n# Task\n"
        + "Identify variables required to answer the modelling question "
        "that are MISSING from the substrate. For each, return a "
        "MissingVariableProposal (name, rationale, required_for, "
        "severity, confidence). Set the result's `model_type` to "
        f"'{model_type}' and the `coverage_ratio` to {ratio:.4f}. "
        "Re-read the hard rules in the prompt template before answering."
    )

    return ContextPack(system=SYSTEM_PREAMBLE, user=user_message)
