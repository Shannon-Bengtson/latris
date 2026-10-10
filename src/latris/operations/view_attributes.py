"""View-specific attribute mutations — model-type-scoped attributes.

Model-specific attributes (e.g. polarity for CLD, CPTs for BN) are stored
in ``views/parameters/{model_type}-{attr}.yaml``.  This module parallels
``operations/attributes.py`` but is scoped to a model type.

Dispatch tables are populated by ``activation.py`` / ``_activations.py``
rather than hardcoded here.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

# Ensure activations are loaded so registries are populated.
import latris.operations._activations  # noqa: F401
from latris.operations._attribute_helpers import upsert_entry
from latris.operations._resolve import resolve_target
from latris.operations.activation import (
    ATTR_COERCE,
    ATTR_ENTRY_FACTORY,
    ATTR_SET_MODELS,
)
from latris.operations.commit import auto_commit
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_model, load_model
from latris.schema import (
    Substrate,
)
from latris.schema.model_types import get_model_type

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def set_view_attribute(
    target: str,
    model_type: str,
    attribute: str,
    value: str,
    *,
    rationale: str | None = None,
    preserve_existing: bool = False,
    root: Path | None = None,
) -> tuple[str, str]:
    """Upsert a model-specific ``(target, attribute) → value``.

    ``rationale`` is an optional free-text justification stored on the entry
    (e.g. a polarity's causal story, so it can be authored in the same call as
    the value and stays coherent with the edge description).

    ``preserve_existing=True`` makes the write non-destructive: an existing value
    is left untouched and no commit is made (returned sha ``""``). Used by AI
    applies so they never clobber a prior polarity/weight.

    Returns ``(target_id, commit_sha)``.
    """
    spec = get_model_type(model_type)
    if attribute not in spec.model_attributes:
        raise ValueError(
            f"{attribute!r} is not a valid attribute for {spec.display_name}. Valid: {spec.model_attributes}"
        )

    coerce_fn = ATTR_COERCE.get(attribute)
    if coerce_fn is None:
        raise ValueError(f"Unknown view attribute: {attribute!r}")
    entry_fn = ATTR_ENTRY_FACTORY.get(attribute)
    if entry_fn is None:
        raise ValueError(f"No entry factory for view attribute: {attribute!r}")
    set_model = ATTR_SET_MODELS.get(attribute)
    if set_model is None:
        raise ValueError(f"No set model for view attribute: {attribute!r}")

    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    target_id = resolve_target(target, substrate)

    file_path = paths.view_attribute_path(model_type, attribute)
    coerced = coerce_fn(value)

    def _make_entry(tid: str, v: object):  # noqa: ANN202 — entry type varies by attribute
        entry = entry_fn(tid, v)
        if rationale is not None and "rationale" in type(entry).model_fields:
            entry = entry.model_copy(update={"rationale": rationale})
        return entry

    store = load_model(set_model, file_path)
    outcome = upsert_entry(
        store, target_id, attribute, coerced, _make_entry, preserve_existing=preserve_existing
    )
    if outcome != "written":
        return target_id, ""  # existing value preserved; nothing to commit
    dump_model(store, file_path)

    sha = auto_commit(
        paths.root,
        subject=f"Set {model_type}/{attribute} on {target_id[:15]}…: {value}",
        body=f"target: {target_id}\nmodel_type: {model_type}\nattribute: {attribute}\nvalue: {value}",
        paths=[file_path],
    )
    return target_id, sha


def get_view_attributes(
    model_type: str,
    attribute: str,
    *,
    root: Path | None = None,
) -> BaseModel:
    """Load the attribute set for *model_type* / *attribute*."""
    spec = get_model_type(model_type)
    if attribute not in spec.model_attributes:
        raise ValueError(
            f"{attribute!r} is not a valid attribute for {spec.display_name}. Valid: {spec.model_attributes}"
        )

    paths = require_project(root)
    file_path = paths.view_attribute_path(model_type, attribute)
    set_model = ATTR_SET_MODELS.get(attribute)
    if set_model is None:
        raise ValueError(f"No set model for view attribute: {attribute!r}")
    return load_model(set_model, file_path)


