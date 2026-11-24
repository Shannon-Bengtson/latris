"""The interpretation prompts — every report section shares one builder."""

from __future__ import annotations

from typing import Any

from latris.ai.context._shared import (
    SYSTEM_PREAMBLE,
    ContextPack,
    _foundation_summary,
    _load_foundation,
    _load_substrate,
)
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model, load_model_or_default
from latris.schema import EvidenceLinkSet, ReferenceLibrary


def _build_interpret_section(paths: ProjectPaths, inputs: dict[str, Any]) -> ContextPack:
    """Shared context builder for all Interpret* prompts."""
    from latris.ai import prompts as prompt_mod
    from latris.operations.findings import list_findings

    section_type = inputs.get("section_type", "")
    model_type = inputs.get("model_type", "")
    claims = inputs.get("claims", [])

    # Load project context
    foundation = _load_foundation(paths)
    substrate = _load_substrate(paths)

    # Model structure summary
    n_entities = len(substrate.entities)
    n_edges = len(substrate.edges)
    entity_labels = [e.label for e in substrate.entities[:20]]

    # Relevant findings
    from latris.operations.interpret_registry import MODEL_WIDE

    # A model-wide section (a model of several types) reads every type's findings.
    findings = list_findings(model_type=None if model_type == MODEL_WIDE else model_type, root=paths.root)
    findings_text = "\n".join(f"- [{f.category}] {f.statement}" for f in findings[:15]) or "(no findings recorded)"

    # Evidence links summary
    evidence = (
        load_model(EvidenceLinkSet, paths.evidence_links_yaml)
        if paths.evidence_links_yaml.exists()
        else EvidenceLinkSet()
    )
    n_evidence = len(evidence.entries)

    # References summary
    refs = load_model_or_default(ReferenceLibrary, paths.references_yaml)
    ref_titles = [r.title for r in refs.entries[:10] if r.title]

    # Claims as grounding anchors
    claims_block = "\n".join(f"- {c}" for c in claims) or "(no claims extracted)"

    # Get the prompt template for audience register
    prompt_spec = prompt_mod.get(inputs.get("_prompt_name", "InterpretAnswer"))
    template_instruction = prompt_spec.template.format(model_type=model_type)

    # Audience-specific register instruction — driven by the section
    # registry's `audience` field so the split is declared in one place
    # (operations/interpret_registry.py) instead of redundantly here and
    # in the per-template prompt text.
    from latris.operations.interpret_registry import get_section_spec

    try:
        audience = get_section_spec(section_type).audience
    except (KeyError, ValueError):
        # Unknown section type falls back to technical framing — same
        # as the previous else-branch behaviour.
        audience = "technical"

    if audience == "stakeholder":
        audience_note = (
            "\nIMPORTANT: Write for a non-technical stakeholder audience. "
            "Avoid jargon. Explain mechanisms in plain language. "
            "Reference specific model elements by their human-readable labels."
        )
    else:
        audience_note = (
            "\nWrite for a technical modelling audience. You may use "
            "formal terminology (feedback loops, d-separation, etc.) "
            "but explain significance, not just mechanics."
        )

    # AI interrogation Phase 2b: hedge instruction when evidence
    # coverage is below threshold AND no findings are accepted. The
    # constraint matters most for prompts that produce magnitude
    # claims; we apply it uniformly so the tone is consistent across
    # all sections during a single Interpret pass.
    from latris.operations.interpret import (
        coverage_ratio,
        hedge_mode_active,
    )

    hedge_active = hedge_mode_active(model_type, paths) if model_type else False
    cited, total, ratio = coverage_ratio(model_type, paths) if model_type else (0, 0, 1.0)

    hedge_block = ""
    if hedge_active:
        hedge_block = (
            f"\n\n## HEDGE MODE\n"
            f"Evidence coverage is {cited}/{total} ({ratio:.0%}) and no "
            f"findings are accepted. Constrain claims:\n"
            f"- Use hedged language: \"may\", \"could indicate\", \"preliminary\".\n"
            f"- Do NOT report centrality values to >1 decimal place.\n"
            f"- Do NOT report centrality values at all on unweighted graphs.\n"
            f"- Do NOT use phrases like \"self-amplifying\", \"runaway\", "
            f"\"dominant feedback\" without quantitative loop counts.\n"
            f"- State coverage explicitly: \"Based on {cited}/{total} elements "
            f"with evidence…\"."
        )

    user_message = (
        f"# Project: {foundation.name}\n"
        f"{_foundation_summary(foundation, header='## Modelling question')}"
        f"## Model structure ({model_type.upper()})\n"
        f"{n_entities} entities, {n_edges} edges.\n"
        f"Key entities: {', '.join(entity_labels)}\n\n"
        f"## Evidence base\n"
        f"{n_evidence} evidence links across {len(refs.entries)} references.\n"
        + (f"Key references: {'; '.join(ref_titles[:5])}\n" if ref_titles else "")
        + f"\n## All findings for this model\n{findings_text}\n\n"
        f"## Claims for this section ({section_type})\n{claims_block}\n\n"
        f"## Task\n{template_instruction}{audience_note}"
        f"{hedge_block}\n\n"
        "Return an InterpretProseResult with Markdown prose. "
        "Ground your interpretation in the claims above. "
        "Reference specific findings and model elements where appropriate."
    )

    return ContextPack(
        system=SYSTEM_PREAMBLE,
        user=user_message,
    )
