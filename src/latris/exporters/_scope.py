"""Shared view-scoping helper for exporters.

Maps a formalism (``model_type``) to the set of substrate element IDs that
belong to its view, via the mapping registry — the same projection
``operations/views.py::project_view`` uses to build ``views/{model_type}.yaml``.
The registry is the live source of truth (a node created directly in a view
records a ``human-direct`` mapping), so we read it rather than the derived
view file.

A ``None``/empty ``model_type``, the ``system_map`` lens, or a formalism with
no mappings yields ``None`` — meaning "no scoping": render the whole substrate,
preserving the legacy project-wide behaviour for back-compat.
"""

from __future__ import annotations

from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model
from latris.schema import MappingRegistry


def view_member_ids(paths: ProjectPaths, model_type: str | None) -> set[str] | None:
    """Return the substrate element IDs mapped to ``model_type``, or ``None``.

    ``None`` signals the caller to apply no scoping (whole substrate).
    """
    if not model_type or model_type == "system_map":
        return None
    registry = load_model(MappingRegistry, paths.mappings_yaml)
    mapped = {m.l2_id for m in registry.entries if m.l3_view == model_type}
    return mapped or None
