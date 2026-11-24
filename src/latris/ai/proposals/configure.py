"""Configure results: suggested attribute values (link polarities), and the recommended modelling approach."""

from __future__ import annotations

from pydantic import Field

from latris.ai.proposals._shared import _Base, _record_value_conflict
from latris.repo.layout import ProjectPaths


class AttributeSuggestion(_Base):
    """A single AI-suggested model attribute value."""

    edge_id: str = Field(..., description="Edge target ID.")
    attribute: str = Field(..., description="Attribute name (polarity, weight).")
    value: str = Field(..., description="Suggested value.")
    rationale: str = Field("", description="Why this value is appropriate.")
    confidence: str = Field("medium", description="low | medium | high")


class AttributeSuggestionsResult(_Base):
    """SuggestEdgePolarities output. Mutating — applies all suggestions via
    the Configure batch path.

    The model_type is derived from each suggestion's `attribute` name via
    the model_type registry (CLD owns 'polarity', FCM owns 'weight'); we
    don't ask the AI to emit it. Suggestions are grouped by
    (model_type, attribute) and committed in a single batch per group.
    """

    suggestions: list[AttributeSuggestion] = Field(default_factory=list)

    def apply(self, paths: ProjectPaths) -> list[str]:
        if not self.suggestions:
            return []
        from latris.operations.configure import batch_set_view_attributes
        from latris.schema.model_types import MODEL_TYPE_REGISTRY

        # attribute → model_type (assumes 1:1 in practice — polarity↔cld,
        # weight↔fcm). Raises if ambiguous.
        attr_to_model_type: dict[str, str] = {}
        for spec in MODEL_TYPE_REGISTRY.values():
            for attr in spec.model_attributes:
                if attr in attr_to_model_type and attr_to_model_type[attr] != spec.id:
                    raise ValueError(
                        f"attribute {attr!r} is claimed by multiple model "
                        f"types — apply() can't disambiguate."
                    )
                attr_to_model_type[attr] = spec.id

        from latris.operations.view_attributes import get_view_attributes

        # Group by (model_type, attribute).
        buckets: dict[tuple[str, str], list[AttributeSuggestion]] = {}
        for s in self.suggestions:
            mt = attr_to_model_type.get(s.attribute)
            if mt is None:
                # Unknown attribute — skip rather than crash. The AI may
                # have invented one; fail-safe is to drop it.
                continue
            buckets.setdefault((mt, s.attribute), []).append(s)

        applied: list[str] = []
        for (mt, attr), sugg in buckets.items():
            # Non-destructive: only WRITE values for edges that don't already
            # have one; where the suggestion disagrees with an existing value,
            # preserve it and record the disagreement as a question.
            existing = {
                e.target_id: str(e.value) for e in get_view_attributes(mt, attr, root=paths.root).entries
            }
            to_write: list[dict] = []
            for s in sugg:
                current = existing.get(s.edge_id)
                if current is None:
                    to_write.append({
                        "target_id": s.edge_id,
                        "value": s.value,
                        "origin": "ai-proposed",
                        "source_detail": s.rationale[:200],
                    })
                elif current.strip() == str(s.value).strip():
                    continue  # already set to the same value — nothing to do
                else:
                    qid = _record_value_conflict(
                        s.edge_id, attr, str(s.value), current, s.rationale, paths
                    )
                    if qid:
                        applied.append(qid)
            if to_write:
                ids, _ = batch_set_view_attributes(
                    model_type=mt,
                    attribute=attr,
                    entries=to_write,
                    preserve_existing=True,
                    root=paths.root,
                )
                applied.extend(ids)
        return applied


class ApproachRecommendation(_Base):
    """One AI-recommended formalism for the project's modelling approach."""

    model_type_id: str = Field(..., description="Model-type id (e.g. cld, dag, bn).")
    suitability: str = Field("consider", description="recommended | consider | not_suited")
    rationale: str = Field(
        "", description="One sentence on why this formalism fits (or doesn't) this question/evidence."
    )


class ApproachRecommendationResult(_Base):
    """RecommendApproach output — ranked formalism recommendations.

    Read-only (no ``apply``): the user accepts recommendations, which select the
    model type and record the rationale as an auditable ModelChoice.
    """

    recommendations: list[ApproachRecommendation] = Field(default_factory=list)
