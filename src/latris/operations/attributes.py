"""Attribute mutations — set an attribute's value.

Attributes attach to a specific (target_id, attribute_name) pair. Each
attribute kind lives in its own YAML file, per the concept doc's
"one concern per file" rule. Maturity is no longer per-attribute — it lives
on the parent Entity/Edge (see ``operations/maturity.py``).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal, get_args

from pydantic import BaseModel

from latris.operations._attribute_helpers import upsert_entry
from latris.operations._resolve import resolve_target
from latris.operations.commit import auto_commit
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_model, load_model
from latris.schema import (
    Confidence,
    ConfidenceEntry,
    ConfidenceSet,
    DescriptionEntry,
    DescriptionSet,
    Substrate,
)

if TYPE_CHECKING:
    from latris.repo.layout import ProjectPaths

AttributeName = Literal["description", "confidence"]


def _file_for(attribute: AttributeName, paths: ProjectPaths) -> Path:
    match attribute:
        case "description":
            return paths.descriptions_yaml
        case "confidence":
            return paths.confidence_yaml


def _set_model_for(attribute: AttributeName) -> type[BaseModel]:
    match attribute:
        case "description":
            return DescriptionSet
        case "confidence":
            return ConfidenceSet


def _coerce_value(attribute: AttributeName, raw: str):
    match attribute:
        case "description":
            return raw
        case "confidence":
            if raw not in get_args(Confidence):
                raise ValueError(f"confidence must be one of {get_args(Confidence)}, got {raw!r}")
            return raw


def _entry_for(attribute: AttributeName, target_id: str, value):
    match attribute:
        case "description":
            return DescriptionEntry(target_id=target_id, value=value)
        case "confidence":
            return ConfidenceEntry(target_id=target_id, value=value)


def set_attribute(
    target: str,
    attribute: AttributeName,
    value: str,
    *,
    preserve_existing: bool = False,
    root: Path | None = None,
) -> tuple[str, str]:
    """Upsert ``(target, attribute) → value``. Returns (target_id, commit_sha).

    ``preserve_existing=True`` makes the write non-destructive: if the target
    already has a value for this attribute it is left untouched and no commit is
    made (the returned sha is ``""``). Used by AI applies so they never clobber a
    prior (human or co-authored) value; human/CLI writes overwrite as before.
    """
    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    target_id = resolve_target(target, substrate)

    file_path = _file_for(attribute, paths)
    set_model = _set_model_for(attribute)
    coerced = _coerce_value(attribute, value)

    store = load_model(set_model, file_path)
    outcome = upsert_entry(
        store,
        target_id,
        attribute,
        coerced,
        lambda tid, v: _entry_for(attribute, tid, v),
        preserve_existing=preserve_existing,
    )
    if outcome != "written":
        return target_id, ""  # existing value preserved; nothing to commit
    dump_model(store, file_path)

    sha = auto_commit(
        paths.root,
        subject=f"Set {attribute} on {target_id[:15]}…: {value}",
        body=f"target: {target_id}\nattribute: {attribute}\nvalue: {value}",
        paths=[file_path],
    )
    return target_id, sha


def add_contested_view(
    target: str,
    view_text: str,
    *,
    attribute: AttributeName = "description",
    root: Path | None = None,
) -> tuple[str, str]:
    """Append a contested-view entry to ``(target, attribute)``.

    Sets ``contested=True`` and appends ``view_text`` to the
    ``contested_views`` list. Returns ``(target_id, commit_sha)``.
    """
    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    target_id = resolve_target(target, substrate)

    file_path = _file_for(attribute, paths)
    set_model = _set_model_for(attribute)
    store = load_model(set_model, file_path)

    entry = next(
        (e for e in store.entries if e.target_id == target_id and e.attribute == attribute),
        None,
    )
    if entry is None:
        raise ValueError(
            f"no {attribute} attribute for {target_id} — set one first with "
            f'`latris attr set {target} {attribute} "..."`'
        )

    entry.contested = True
    entry.contested_views.append(view_text)
    dump_model(store, file_path)

    sha = auto_commit(
        paths.root,
        subject=f"Add contested view on {target_id[:15]}…",
        body=f"target: {target_id}\nattribute: {attribute}\nview: {view_text[:80]}",
        paths=[file_path],
    )
    return target_id, sha


