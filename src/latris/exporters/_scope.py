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


def view_member_ids(paths: ProjectPaths, model_type: str | None) -> set[str] | None:
    """Return the substrate element IDs that belong to ``model_type``, or ``None``.

    ``None`` signals the caller to apply no scoping (whole substrate). The rule lives in
    ``operations/membership.py`` so diagrams, readiness, staleness and claims agree.
    """
    from latris.operations.membership import members

    found = members(paths, model_type)
    if found is None or not found.ids:
        return None
    return set(found.ids)
