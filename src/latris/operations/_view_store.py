"""Storage shared by the formalism operations (fault tree, bow-tie, MCDA, …).

Each of those modules keeps its numbers in per-attribute files under
``views/parameters/<model_type>-<attribute>.yaml`` and its element types as
view roles. :class:`ViewStore` is that layout, bound to one model type:
load a store (empty if the file isn't there yet), replace an entry, save
and commit, read the role map, and resolve a factor.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from latris.operations._resolve import resolve_target
from latris.operations.commit import auto_commit
from latris.repo.layout import ProjectPaths
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_model, load_model, load_model_or_default
from latris.schema import Substrate

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class ViewStore:
    model_type: str
    elements: Collection[str] = ()
    """The role values that count as this model type's elements."""

    def path(self, paths: ProjectPaths, attribute: str) -> Path:
        return paths.view_attribute_path(self.model_type, attribute)

    def load(self, root: Path | ProjectPaths | None, attribute: str, cls: type[T]) -> T:
        paths = root if isinstance(root, ProjectPaths) else require_project(root)
        return load_model_or_default(cls, self.path(paths, attribute))

    def save(self, paths: ProjectPaths, attribute: str, store: BaseModel, *, subject: str, body: str = "") -> str:
        """Write ``store`` and commit it; returns the commit sha."""
        path = self.path(paths, attribute)
        dump_model(store, path)
        return auto_commit(paths.root, subject=subject, body=body, paths=[path])

    def roles(self, root: Path | ProjectPaths | None) -> dict[str, str]:
        """Entity id → element type, for this model type's elements only."""
        from latris.schema.roles import RoleSet

        paths = root if isinstance(root, ProjectPaths) else require_project(root)
        p = paths.role_path(self.model_type)
        if not p.exists():
            return {}
        return {e.target_id: e.value for e in load_model(RoleSet, p).entries if e.value in self.elements}


def replace_entry(store: Any, entry: Any, *keys: str) -> None:
    """Put ``entry`` in ``store.entries``, replacing the one with the same key.

    The key is ``target_id`` unless other fields are named (e.g.
    ``"target_id", "criterion"`` for an MCDA score).
    """
    keys = keys or ("target_id",)
    key = tuple(getattr(entry, k) for k in keys)
    store.entries = [e for e in store.entries if tuple(getattr(e, k) for k in keys) != key] + [entry]


def resolve_factor(source: ProjectPaths | Substrate, target: str, *, link_error: str) -> tuple[str, str]:
    """(id, label) of the factor ``target`` names; ``link_error`` if it names a link."""
    substrate = source if isinstance(source, Substrate) else load_model(Substrate, source.conceptual_yaml)
    tid = resolve_target(target, substrate)
    label = next((e.label for e in substrate.entities if e.id == tid), None)
    if label is None:
        raise ValueError(link_error)
    return tid, label
