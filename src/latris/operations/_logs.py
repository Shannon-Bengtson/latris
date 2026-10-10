"""Shared helpers for YAML-backed append-only logs.

For the list-of-entries log stores (assumptions, decisions, review sessions,
…): load the store, append one entry, write it back. JSONL logs use
``yaml_io.dump_jsonl_append`` instead.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from latris.repo.yaml_io import dump_model, load_model


def append_entry(log_model: type[BaseModel], path: Path, entry) -> BaseModel:
    """Append ``entry`` to the log at ``path`` and return the updated store."""
    store = load_model(log_model, path) if path.exists() else log_model()
    store.entries.append(entry)  # type: ignore[attr-defined]
    dump_model(store, path)
    return store
