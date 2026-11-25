"""Filling one provenance field: the prompt, and the guidance each kind of field gets."""

from __future__ import annotations

from latris.ai.prompts._spec import PromptIntent, PromptScope, PromptSpec
from latris.ai.prompts.inputs import FillProvenanceFieldInputs

PROMPTS: dict[str, PromptSpec] = {
    "FillProvenanceField": PromptSpec(
        name="FillProvenanceField",
        title="Fill this field with AI",
        description=(
            "Suggest a value for a single provenance field (description, "
            "rationale, evidence note, etc.). The user reviews and saves "
            "via the normal field-edit path; nothing commits without "
            "explicit save."
        ),
        inputs=FillProvenanceFieldInputs,
        template=(
            "Suggest a value for the {target_kind} field {field_path}.\n"
            "Current value: {current_value}\n"
            "Use the project context above to make the suggestion specific, "
            "mechanistic, and consistent with the modelling question. "
            "Return a FillFieldProposal with `value`, `rationale`, and "
            "`confidence`."
        ),
        output_hint="A FillFieldProposal with the suggested field value.",
        scope=PromptScope.element,
        intent=PromptIntent.insight,
    ),
}


# ---------- Per-field AI guidance ----------

FIELD_GUIDANCE: dict[tuple[str, str], str] = {
    # (target_kind, field_path) → short instruction snippet appended to the
    # FillProvenanceField user message. Keep entries concise — the helper
    # below falls back to a default for unmapped fields.
    ("project", "background"): (
        "Write 2-4 sentences capturing the broader situation: who this model "
        "is for, what decision it informs, the operational/policy setting, "
        "and any prior work or constraints worth respecting."
    ),
    ("project", "boundary"): (
        "List what is in and out of scope. Prefer concrete bounds (variables, "
        "spatial/temporal extent) over abstractions."
    ),
    ("project", "exclusions"): (
        "List things deliberately not modelled, with one-line reasons."
    ),
    ("project", "predictions"): (
        "List the model's expected outputs or forecast values, in plain "
        "language, with the readership in mind."
    ),
    ("entity", "description"): (
        "1-2 sentences: what this node represents mechanistically. Focus on "
        "the lever/quantity, not meta-description ('this is a node about X')."
    ),
    ("edge", "description"): (
        "1-2 sentences: how the source affects the target — mechanism, sign, "
        "and any conditions."
    ),
    ("citation", "attribute"): (
        "Which part of the cited work supports this claim — page/section/"
        "figure where applicable, or 'overall thesis' if work-level."
    ),
    ("citation", "notes"): (
        "1-2 sentences linking the cited work to the specific claim it "
        "supports here."
    ),
    ("assumption", "rationale"): (
        "1-2 sentences: why this assumption is needed for the model to make "
        "sense, and what would happen if it were violated."
    ),
    ("challenge", "argument"): (
        "Argue against the claim/element. Focus on mechanism, confounding, "
        "directionality, or scope. Be specific."
    ),
    ("challenge", "resolution_rationale"): (
        "1-2 sentences: how the challenge was resolved, accepted, or "
        "deferred, and why."
    ),
    ("decision", "rationale"): (
        "Why this decision was made — the tradeoff being managed, "
        "alternatives considered, and the reason this option was chosen."
    ),
    ("question", "question"): (
        "1 sentence: a specific open question about this element. Avoid "
        "rhetorical or yes/no framings."
    ),
}


def field_guidance(target_kind: str, field_path: str) -> str:
    """Return a guidance snippet for a (target_kind, field_path), or a default."""
    if (target_kind, field_path) in FIELD_GUIDANCE:
        return FIELD_GUIDANCE[(target_kind, field_path)]
    # Fall back: try last segment of dotted path against any kind
    last = field_path.rsplit(".", 1)[-1]
    for (_kind, path), guidance in FIELD_GUIDANCE.items():
        if path == last:
            return guidance
    return (
        "Write a concise, evidence-aware value for this field, consistent "
        "with the project context above."
    )
