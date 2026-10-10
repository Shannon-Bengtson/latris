"""Shared helpers for attribute upsert.

Both ``attributes.py`` and ``view_attributes.py`` share the same
find-or-append logic. These pure helpers operate on in-memory
pydantic stores — callers still own file I/O and commits.

Maturity no longer lives on attribute entries (it sits on the parent
Entity/Edge); see ``operations/maturity.py`` for the chokepoint and
``docs/design/MATURITY_LADDER.md`` for the design rationale.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def upsert_entry(
    store: Any,
    target_id: str,
    attribute: str,
    value: Any,
    entry_factory: Callable[[str, Any], Any],
    *,
    preserve_existing: bool = False,
) -> str:
    """Find an existing entry by (target_id, attribute) and update it, or append a new one.

    Returns the outcome so callers can act on it:
      - ``"written"``  — value was set (created, or overwrote an existing value);
      - ``"kept"``     — an entry already existed with the SAME value; left as-is;
      - ``"conflict"`` — an entry already existed with a DIFFERENT value; left
                         as-is (existing wins).

    ``preserve_existing=True`` makes the write non-destructive: an existing value
    is never overwritten (the caller decides what to do about a conflict). The
    default preserves the historical overwrite behaviour for human/CLI writes.
    """
    existing = next(
        (e for e in store.entries if e.target_id == target_id and e.attribute == attribute),
        None,
    )
    if existing is None:
        store.entries.append(entry_factory(target_id, value))
        return "written"
    if preserve_existing:
        return "kept" if existing.value == value else "conflict"
    existing.value = value
    return "written"
