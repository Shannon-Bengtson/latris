"""Registry-driven model type activation.

Adding a new stable model type means: declare it via
``register_model_type(ModelTypeSpec(...))`` in ``schema/model_types.py``,
then add one ``activate_model_type()`` call in ``_activations.py`` to
register its validators and attribute coercers. Every other concern
(view class, view path) is uniform across model types and derived from
the spec.

All operation-side dispatch tables live here.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

# ── Global registries (populated by activate_model_type) ────────────────

PROJECTION_VALIDATORS: dict[str, Callable] = {}
"""validator_name → callable(substrate, edge_ids, paths) that raises on violation."""

ATTR_SET_MODELS: dict[str, type[BaseModel]] = {}
"""attribute_name → Set pydantic class (PolaritySet, …)."""

ATTR_COERCE: dict[str, Callable[[str], Any]] = {}
"""attribute_name → callable(raw_string) → coerced value."""

ATTR_ENTRY_FACTORY: dict[str, Callable] = {}
"""attribute_name → callable(target_id, value) → Entry instance."""


def activate_model_type(
    model_type_id: str,
    *,
    projection_validators: dict[str, Callable] | None = None,
    attr_set_models: dict[str, type[BaseModel]] | None = None,
    attr_coerce: dict[str, Callable[[str], Any]] | None = None,
    attr_entry_factory: dict[str, Callable] | None = None,
) -> None:
    """Wire a model type's operation-side behaviours into dispatch tables.

    The model type itself must already be registered via
    ``register_model_type()``; this call adds the runtime callables
    (validators, attribute coercers) that ``operations/`` needs.
    """
    from latris.schema.model_types import MODEL_TYPE_REGISTRY

    if model_type_id not in MODEL_TYPE_REGISTRY:
        raise ValueError(
            f"Cannot activate unknown model type {model_type_id!r}. "
            f"Call register_model_type() first."
        )
    if projection_validators:
        PROJECTION_VALIDATORS.update(projection_validators)
    if attr_set_models:
        ATTR_SET_MODELS.update(attr_set_models)
    if attr_coerce:
        ATTR_COERCE.update(attr_coerce)
    if attr_entry_factory:
        ATTR_ENTRY_FACTORY.update(attr_entry_factory)
