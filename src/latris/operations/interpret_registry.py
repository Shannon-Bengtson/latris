"""Interpret section registry — declares which sections apply per model type.

Each ``InterpretSectionSpec`` describes a single interpretation section:
its display metadata, audience, applicable model types, and which AI
prompt to use for prose generation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class InterpretSectionSpec:
    """Declarative specification for an interpretation section."""

    section_type: str
    display_name: str
    description: str
    audience: Literal["technical", "stakeholder"]
    applicable_model_types: tuple[str, ...]
    prompt_name: str  # AI prompt for prose generation


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

INTERPRET_SECTION_REGISTRY: dict[str, InterpretSectionSpec] = {}


def _register(spec: InterpretSectionSpec) -> None:
    """Add *spec* to the registry."""
    INTERPRET_SECTION_REGISTRY[spec.section_type] = spec


def get_section_spec(section_type: str) -> InterpretSectionSpec:
    """Return the spec for *section_type*, or raise ``ValueError``."""
    try:
        return INTERPRET_SECTION_REGISTRY[section_type]
    except KeyError:
        known = sorted(INTERPRET_SECTION_REGISTRY)
        raise ValueError(f"Unknown interpret section type: {section_type!r}. Known: {known}") from None


def get_sections_for_model_types(
    model_type_ids: list[str],
) -> list[InterpretSectionSpec]:
    """Return section specs applicable to any of the given model types."""
    return [
        spec
        for spec in INTERPRET_SECTION_REGISTRY.values()
        if any(mt in spec.applicable_model_types for mt in model_type_ids)
    ]


# ---------------------------------------------------------------------------
# Built-in section definitions
# ---------------------------------------------------------------------------

_ALL_STABLE = ("cld", "dag", "fcm", "bn")

# -- Technical sections (for the modeller) --

_register(
    InterpretSectionSpec(
        section_type="structural_summary",
        display_name="Structural Summary",
        description="What the analysis found: topology, connectivity, key paths and cycles.",
        audience="technical",
        applicable_model_types=_ALL_STABLE,
        prompt_name="InterpretStructuralSummary",
    )
)

_register(
    InterpretSectionSpec(
        section_type="key_findings",
        display_name="Key Findings",
        description="Which findings matter most — ranked by importance and confidence.",
        audience="technical",
        applicable_model_types=_ALL_STABLE,
        prompt_name="InterpretKeyFindings",
    )
)

_register(
    InterpretSectionSpec(
        section_type="sensitivity",
        display_name="Sensitivity & Robustness",
        description="What matters most: structural sensitivity for qualitative models, parametric for quantitative.",
        audience="technical",
        applicable_model_types=_ALL_STABLE,
        prompt_name="InterpretSensitivity",
    )
)

_register(
    InterpretSectionSpec(
        section_type="assumptions_limitations",
        display_name="Assumptions & Limitations",
        description="Model assumptions and known limitations that bound interpretation.",
        audience="technical",
        applicable_model_types=_ALL_STABLE,
        prompt_name="InterpretAssumptions",
    )
)

_register(
    InterpretSectionSpec(
        section_type="evidence_gaps",
        display_name="Evidence Gaps",
        description="Where provenance is thin — elements without evidence or uncited relationships.",
        audience="technical",
        applicable_model_types=_ALL_STABLE,
        prompt_name="InterpretEvidenceGaps",
    )
)

_register(
    InterpretSectionSpec(
        section_type="evidence_coverage",
        display_name="Evidence Coverage",
        description="Cross-reference audit — uncited model elements and unused references.",
        audience="technical",
        applicable_model_types=_ALL_STABLE,
        prompt_name="InterpretEvidenceCoverage",
    )
)

# -- Stakeholder sections (flow to report) --

_register(
    InterpretSectionSpec(
        section_type="answer_to_question",
        display_name="Answer to Modelling Question",
        description="Synthesis answering the project's modelling question based on all analysis results.",
        audience="stakeholder",
        applicable_model_types=_ALL_STABLE,
        prompt_name="InterpretAnswer",
    )
)

_register(
    InterpretSectionSpec(
        section_type="implications",
        display_name="Implications & Interventions",
        description="What the results mean for decisions — where to intervene and what to expect.",
        audience="stakeholder",
        applicable_model_types=_ALL_STABLE,
        prompt_name="InterpretImplications",
    )
)

_register(
    InterpretSectionSpec(
        section_type="confidence_assessment",
        display_name="Confidence Assessment",
        description="How much to trust these results — evidence density, finding maturity, known gaps.",
        audience="stakeholder",
        applicable_model_types=_ALL_STABLE,
        prompt_name="InterpretConfidence",
    )
)

_register(
    InterpretSectionSpec(
        section_type="open_questions",
        display_name="Open Questions & Next Steps",
        description="Unresolved questions and recommended further work.",
        audience="stakeholder",
        applicable_model_types=_ALL_STABLE,
        prompt_name="InterpretOpenQuestions",
    )
)
