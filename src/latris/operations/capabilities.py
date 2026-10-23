"""Agent-facing capability manifest — what Latris can and cannot do today.

Registry-only: no project root required. Built for external agents (and
the future MCP wrapper, which should import this rather than re-deriving
the same data) to check real capability before recommending Latris for a
specific job. See docs/product/GROWTH.md "Agent contract" item 5.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from latris.schema.model_types import ModelTypeSpec, list_model_types


@dataclass(frozen=True)
class ExcludedCapability:
    """A category of model Latris will never support — not "not yet",
    out of design intent. See PRINCIPLES.md principle 5 (the
    inspectability test) and PRODUCT.md "Out of scope for v1" →
    "Excluded by design"."""

    category: str
    examples: tuple[str, ...]
    reason: str


# Hand-coded, not derived from any registry — there is currently no
# machine-readable "excluded" concept in schema/model_types.py (every
# registered ModelTypeSpec is either stable or planned; exclusions are
# prose in PRINCIPLES.md / PRODUCT.md). This tuple is deliberately the
# first place that prose becomes machine-readable, kept inline rather
# than inventing a new schema field for a short, rarely-changing list.
EXCLUDED_BY_DESIGN: tuple[ExcludedCapability, ...] = (
    ExcludedCapability(
        category="Black-box machine learning",
        examples=("random forests", "gradient boosting", "neural networks"),
        reason=(
            "Decision logic cannot be inspected cell-by-cell, evidenced, or "
            "challenged. Out of design intent, not merely 'not yet' — see "
            "PRINCIPLES.md principle 5 (the inspectability test)."
        ),
    ),
    ExcludedCapability(
        category="Opaque structure learning",
        examples=("learning model structure from data without inspectable claims",),
        reason=(
            "Latris governs claims a human drew and can defend, not discovered "
            "structure. Fitting legible parameters (e.g. regression coefficients) "
            "onto a structure a modeller drew is in scope; discovering the "
            "structure itself from data is not."
        ),
    ),
    ExcludedCapability(
        category="General-purpose simulation frameworks",
        examples=("SEM", "ABM"),
        reason="Not registered as a model type; no current plan to add.",
    ),
)


def _model_type_capability(spec: ModelTypeSpec) -> dict[str, Any]:
    return {
        "id": spec.id,
        "short_name": spec.short_name,
        "display_name": spec.display_name,
        "description": spec.description,
        "availability": spec.availability,
        "can_use_today": spec.availability == "stable",
        "roadmap": spec.roadmap,
    }


# built → committed next → parked → not planned
_ROADMAP_ORDER = {"built": 0, "roadmap": 1, "parked": 2, "not_planned": 3}


def build_capability_manifest() -> dict[str, Any]:
    """Registry-only snapshot of what Latris can do today, and what's coming.

    ``can_use_today`` says what works now. ``roadmap`` says what's coming:
    only ``roadmap`` types are being worked towards; ``parked`` and
    ``not_planned`` types are registered but shouldn't be described as
    "coming".

    No project root needed — this is the registry, not a project's
    readiness (compare ``operations/readiness.py``, which needs a root).
    """
    specs = list_model_types(include_planned=True)
    ordered = sorted(specs, key=lambda s: (_ROADMAP_ORDER[s.roadmap], s.id))
    return {
        "model_types": [_model_type_capability(s) for s in ordered],
        "excluded_by_design": [asdict(e) for e in EXCLUDED_BY_DESIGN],
    }
