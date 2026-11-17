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
    return mapped or _parameterised_members(paths, model_type) or None


def _parameterised_members(paths: ProjectPaths, model_type: str) -> set[str]:
    """For a quantified formalism with no mappings, the factors it computes on, and the links among them.

    A Bayesian network computes on the factors with a state space or a table (and those tables'
    parents); a system dynamics model on the factors with a role (stock, flow, ...). Without this a
    BN or SD diagram drew the whole causal model, feedback loops and all.
    """
    nodes: set[str] = set()
    if model_type == "bn":
        from latris.operations import bn as bn_ops

        nodes = {e.target_id for e in bn_ops._load_state_spaces(paths).entries}
        for target, cpt in bn_ops._effective_cpt_map(paths).items():
            nodes |= {target, *cpt.parents}
    elif model_type == "sd":
        from latris.operations import sd as sd_ops

        nodes = {e.target_id for e in sd_ops._load_roles(paths).entries}
    if not nodes:
        return set()
    from latris.schema import Substrate

    substrate = load_model(Substrate, paths.conceptual_yaml)
    return nodes | {e.id for e in substrate.edges if e.from_id in nodes and e.to_id in nodes}
