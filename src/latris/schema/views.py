"""View projection schema.

A view is a thin projection of substrate IDs into a formalism. Every view
has the same on-disk shape: lists of entity and edge IDs plus optional
display notes. The ``kind`` field discriminates which formalism the view
belongs to — its value is validated against ``MODEL_TYPE_REGISTRY`` so
adding a new model type doesn't require a new view class.

Formalism-specific parameters (polarity, FCM weights, BN CPTs, etc.)
live in separate ``views/parameters/{kind}-{attribute}.yaml`` files,
not on the view itself.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class _ViewBase(_Base):
    """Shared view shape — a projection selects a subset of substrate IDs."""

    entity_ids: list[str] = Field(default_factory=list)
    edge_ids: list[str] = Field(default_factory=list)
    notes: str | None = None


class View(_ViewBase):
    """A view of the substrate projected into a formalism.

    The ``kind`` is validated lazily against ``MODEL_TYPE_REGISTRY`` so
    activation order doesn't matter (the registry is populated at
    import time, but in some test paths it may not be loaded yet when
    the schema module is first imported).
    """

    kind: str

    @field_validator("kind")
    @classmethod
    def _kind_must_be_registered(cls, value: str) -> str:
        from latris.schema.model_types import MODEL_TYPE_REGISTRY

        if value not in MODEL_TYPE_REGISTRY:
            known = sorted(MODEL_TYPE_REGISTRY)
            raise ValueError(f"Unknown view kind: {value!r}. Known: {known}")
        return value
