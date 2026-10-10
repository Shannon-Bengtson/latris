"""Batch view-attribute configuration — the Configure workflow backend.

Supports batch-setting model-specific attributes (e.g. CLD polarity, FCM
weight) in a single git commit with per-entry provenance tracking.  Used
by the Analyse phase's Configure sub-mode in the GUI.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Ensure activations are loaded so registries are populated.
import latris.operations._activations  # noqa: F401
from latris.operations._attribute_helpers import upsert_entry
from latris.operations._resolve import resolve_target
from latris.operations.activation import (
    ATTR_COERCE,
    ATTR_ENTRY_FACTORY,
    ATTR_SET_MODELS,
)
from latris.operations.batch import batch
from latris.operations.commit import auto_commit
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_model, load_model
from latris.schema import Substrate
from latris.schema.model_types import get_model_type


def batch_set_view_attributes(
    *,
    model_type: str,
    attribute: str,
    entries: list[dict[str, Any]],
    preserve_existing: bool = False,
    root: Path | None = None,
) -> tuple[list[str], str]:
    """Set multiple view attributes in a single git commit.

    Each entry dict must have ``target_id`` and ``value``.
    Optional provenance fields: ``origin`` (default ``"human-direct"``),
    ``source_detail`` (default ``""``).

    ``preserve_existing=True`` makes each write non-destructive: targets that
    already have a value are left untouched (not restamped, not in the returned
    ``applied_target_ids``). Used by AI applies as a safety net so a stray
    suggestion can never clobber an existing value.

    Returns ``(applied_target_ids, commit_sha)`` — only the targets actually
    written.
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

    if not entries:
        raise ValueError("entries must not be empty")

    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)

    file_path = paths.view_attribute_path(model_type, attribute)
    store = load_model(set_model, file_path)

    applied_ids: list[str] = []
    n = len(entries)
    subject = f"Configure: set {n} {model_type}/{attribute} value{'s' if n != 1 else ''}"

    with batch(paths.root, subject=subject):
        for entry_def in entries:
            target_id = resolve_target(entry_def["target_id"], substrate)
            coerced = coerce_fn(entry_def["value"])

            # Upsert the entry in the in-memory store.
            outcome = upsert_entry(
                store,
                target_id,
                attribute,
                coerced,
                lambda tid, v: entry_fn(tid, v),
                preserve_existing=preserve_existing,
            )
            if outcome != "written":
                continue  # existing value preserved — don't restamp or report

            # Set provenance on the entry (find it after upsert).
            entry_obj = next(e for e in store.entries if e.target_id == target_id and e.attribute == attribute)
            origin = entry_def.get("origin", "human-direct")
            if hasattr(entry_obj, "origin"):
                entry_obj.origin = origin
            if hasattr(entry_obj, "source_id") and entry_def.get("source_detail"):
                entry_obj.source_id = entry_def["source_detail"]

            applied_ids.append(target_id)

        # Write the store once (not per entry) and register with batch.
        # If preserve_existing skipped everything, there is nothing to write.
        if applied_ids:
            dump_model(store, file_path)
            auto_commit(paths.root, subject=subject, paths=[file_path])

    # The batch context manager produces the final commit.
    from latris.repo import git

    sha = git.head_sha(paths.root)

    return applied_ids, sha
