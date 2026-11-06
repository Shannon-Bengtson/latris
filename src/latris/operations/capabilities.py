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
        "reports": _report_capabilities(),
        "building": _building_capabilities(),
    }


def _building_capabilities() -> dict[str, str]:
    """How an agent builds a model quickly and records evidence on both sides."""
    return {
        "whole_model_in_one_step": (
            "latris build --spec model.yaml (YAML or JSON; '-' reads stdin): factors, links with polarity and "
            "reasons, sources, citations, evidence against, assumptions, questions and the outcome, as one "
            "commit. The spec is checked in full first; a mistake changes nothing."
        ),
        "evidence_for": "latris evidence add <link> polarity <bibkey> [--verified-by ai]",
        "evidence_against": (
            "latris evidence add <link> polarity <bibkey> --contradicts — a source that argues against the "
            "link; reports show the link's sources for and against under 'Contested links'."
        ),
        "outcome": (
            "latris view role cld <factor> outcome — marks what the model explains so it isn't suggested as "
            "an intervention point."
        ),
    }


def _report_capabilities() -> dict[str, Any]:
    """What a person can be handed, and how to make it."""
    from latris.exporters.packs import PACKS

    return {
        "packs": [
            {"name": p.name, "audience": p.audience, "purpose": p.purpose, "sections": list(p.sections)}
            for p in PACKS.values()
        ],
        "how": "latris export md --pack <name> [--model-type <type>] -o report.md",
        "link_for_a_person": (
            "latris link — prints a link that opens this model in the Latris app (works offline; the model "
            "travels inside the link): a hosted report with the full Latris figure (loops, polarity, "
            "evidence) that the person can share, and save to a free account for the editor and Word. "
            "Give the person this link alongside (or instead of) the Markdown."
        ),
        "board_ready_prose": (
            "The client and publication packs include an interpretation: the answer to the modelling "
            "question, implications, confidence and open questions, each written from claims Latris "
            "extracts from the model. `latris interpret initialise`, then for each section either "
            "`latris interpret generate-prose <section>` (needs an AI key) or read its claims with "
            "`latris interpret show <section>` and write the prose yourself with "
            "`latris interpret set-prose <section> \"...\" --by ai`."
        ),
        "library_formats": ["markdown (with a Mermaid diagram)", "graphviz dot"],
        "app_formats": {
            "where": "https://app.latris.app (the Latris app)",
            "formats": ["Word report", "HTML review pack (and importing completed reviews)",
                        "scrollytelling story", "hosted report link (no sign-in to view)"],
        },
    }
