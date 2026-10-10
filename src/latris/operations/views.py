"""View projection operations — project substrate subsets into formal views.

Every mutation auto-commits.  Validation is registry-driven: the
``ModelTypeSpec`` for each view kind declares structural validators
and required model-specific attributes.

Dispatch tables are populated by ``activation.py`` / ``_activations.py``
rather than hardcoded here.
"""

from __future__ import annotations

import warnings
from pathlib import Path

# Ensure activations are loaded so registries are populated.
import latris.operations._activations  # noqa: F401
from latris.operations.activation import (
    ATTR_SET_MODELS,
    PROJECTION_VALIDATORS,
)
from latris.operations.commit import auto_commit
from latris.operations.mappings import map_to_view
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_model, load_model
from latris.schema import (
    Mapping,
    MappingRegistry,
    Substrate,
    View,
)
from latris.schema.model_types import get_model_type

# ---------------------------------------------------------------------------
# Attribute warnings
# ---------------------------------------------------------------------------


def _check_model_attribute(paths, view_kind: str, edge_ids: list[str], attr_name: str) -> list[str]:
    """Warn about elements missing a model-specific attribute. Returns missing IDs."""
    model_cls = ATTR_SET_MODELS.get(attr_name)
    if model_cls is None:
        return []
    store = load_model(model_cls, paths.view_attribute_path(view_kind, attr_name))
    has_attr = {e.target_id for e in store.entries if e.attribute == attr_name}
    missing = [eid for eid in edge_ids if eid not in has_attr]
    if missing:
        warnings.warn(
            f"{view_kind.upper()} view: {len(missing)} edge(s) missing {attr_name} attribute: "
            + ", ".join(missing[:5])
            + ("…" if len(missing) > 5 else ""),
            stacklevel=3,
        )
    return missing


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def project_view(
    view_kind: str,
    *,
    root: Path | None = None,
):
    """Build a view from the current mappings for view_kind. Auto-commits."""
    spec = get_model_type(view_kind)
    if spec.availability != "stable":
        raise ValueError(
            f"Model type {view_kind!r} is not yet available (availability: {spec.availability})."
        )

    paths = require_project(root)
    registry = load_model(MappingRegistry, paths.mappings_yaml)
    substrate = load_model(Substrate, paths.conceptual_yaml)

    entity_id_set = {e.id for e in substrate.entities}
    edge_id_set = {e.id for e in substrate.edges}

    mapped = [m for m in registry.entries if m.l3_view == view_kind]
    entity_ids = [m.l2_id for m in mapped if m.l2_id in entity_id_set]
    edge_ids = [m.l2_id for m in mapped if m.l2_id in edge_id_set]

    # Registry-driven structural validators
    for validator_name in spec.structural_validators:
        validator_fn = PROJECTION_VALIDATORS.get(validator_name)
        if validator_fn is not None:
            validator_fn(substrate, edge_ids, paths)

    # Registry-driven model-attribute checks (warnings, not blockers)
    for attr_name in spec.model_attributes:
        _check_model_attribute(paths, view_kind, edge_ids, attr_name)

    view = View(kind=view_kind, entity_ids=entity_ids, edge_ids=edge_ids)
    view_path = paths.view_yaml(view_kind)
    dump_model(view, view_path)
    auto_commit(
        paths.root,
        subject=f"Project {view_kind} view ({len(entity_ids)} entities, {len(edge_ids)} edges)",
        body=None,
        provenance="human-authored",
        paths=[view_path],
    )
    return view


def auto_project(
    view_kind: str,
    *,
    root: Path | None = None,
) -> list[Mapping]:
    """Map all substrate elements to the given view, then project. Returns created mappings."""
    spec = get_model_type(view_kind)
    if spec.availability != "stable":
        raise ValueError(
            f"Model type {view_kind!r} is not yet available (availability: {spec.availability})."
        )

    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    registry = load_model(MappingRegistry, paths.mappings_yaml)
    existing = {(m.l2_id, m.l3_view) for m in registry.entries}

    created: list[Mapping] = []
    for entity in substrate.entities:
        if (entity.id, view_kind) not in existing:
            mapping, _ = map_to_view(entity.id, view_kind, root=root)
            created.append(mapping)
    for edge in substrate.edges:
        if (edge.id, view_kind) not in existing:
            mapping, _ = map_to_view(edge.id, view_kind, root=root)
            created.append(mapping)

    # Now project the view
    project_view(view_kind, root=root)
    return created
