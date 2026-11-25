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
from latris.operations._actor import author
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
from latris.schema.common import default_origin
from latris.schema.ids import new_id
from latris.schema.model_types import get_model_type
from latris.schema.provenance import Question, QuestionLog

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

    rationale_sent = rationale is not None
    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    target_id = resolve_target(target, substrate)

    file_path = paths.view_attribute_path(model_type, attribute)
    coerced = coerce_fn(value)

    def _make_entry(tid: str, v: object):  # noqa: ANN202 — entry type varies by attribute
        entry = entry_fn(tid, v)
        if "origin" in type(entry).model_fields:
            entry = entry.model_copy(update={"origin": default_origin()})
        if rationale is not None and "rationale" in type(entry).model_fields:
            entry = entry.model_copy(update={"rationale": rationale})
        return entry

    store = load_model(set_model, file_path)
    # What was there before, copied: the upsert below changes the entry in place.
    before = next(
        (e.model_copy() for e in store.entries if e.target_id == target_id and e.attribute == attribute),
        None,
    )
    if rationale is not None:
        rationale = rationale.strip() or None  # a blank reason removes it
    outcome = upsert_entry(store, target_id, attribute, coerced, _make_entry, preserve_existing=preserve_existing)
    reason_given = rationale_sent  # a reason was sent: written, or blank to remove it
    if outcome == "written" and reason_given:
        # upsert_entry overwrites only the value of an existing entry; a new
        # rationale supplied with it must replace the old one too.
        for entry in store.entries:
            if entry.target_id == target_id and entry.attribute == attribute and hasattr(entry, "rationale"):
                entry.rationale = rationale
    if outcome != "written":
        return target_id, ""  # existing value preserved; nothing to commit
    dump_model(store, file_path)
    touched = [file_path]
    if attribute == "polarity":
        touched += _check_polarity_reason(paths, target_id, before, coerced, reason_given, rationale)

    sha = auto_commit(
        paths.root,
        subject=f"Set {model_type}/{attribute} on {target_id[:15]}…: {value}",
        body=f"target: {target_id}\nmodel_type: {model_type}\nattribute: {attribute}\nvalue: {value}",
        paths=touched,
    )
    return target_id, sha


def _check_polarity_reason(
    paths,  # noqa: ANN001 — ProjectPaths
    target_id: str,
    before: object | None,
    value: object,
    reason_given: bool,
    rationale: str | None,
) -> list[Path]:
    """Keep a link's written reason honest about its sign.

    A sign changed under a reason that was left as it was raises an open question on the link — the reason was
    written for the other sign and may now argue against it. Editing or removing the reason (or writing one with
    the new sign) answers it, and latris resolves the question itself. Returns the files it changed.
    """
    log = load_model(QuestionLog, paths.questions_yaml) if paths.questions_yaml.exists() else QuestionLog()
    open_ones = [
        q
        for q in log.entries
        if q.target_id == target_id and q.concerns == "polarity_reason" and q.disposition == "open"
    ]
    old_reason = getattr(before, "rationale", None) if before is not None else None
    old_value = getattr(before, "value", None) if before is not None else None
    changed = False
    if reason_given:
        for q in open_ones:
            q.disposition = "resolved"
            q.resolution = (
                "The reason was removed."
                if not rationale
                else "The reason was kept: it holds for the new sign."
                if rationale == old_reason
                else "The reason was rewritten."
            )
            changed = True
    elif old_reason and old_value is not None and old_value != value and not open_ones:
        log.entries.append(
            Question(
                id=new_id("question"),
                question=(
                    f"This link's sign changed from {old_value} to {value}, but its reason was written for "
                    f"{old_value}: “{old_reason}”. Does it still hold? Edit the reason or remove it."
                ),
                target_id=target_id,
                raised_by=author(paths.root),
                concerns="polarity_reason",
            )
        )
        changed = True
    if not changed:
        return []
    dump_model(log, paths.questions_yaml)
    return [paths.questions_yaml]


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
