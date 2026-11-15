"""View role operations — assign formalism-specific roles to entities.

Roles classify what a substrate entity means within a formal view.
The API mirrors ``view_attributes.py``: set, get. Maturity now lives
on the parent Entity/Edge — see ``operations/maturity.py``.
"""

from __future__ import annotations

from pathlib import Path

from latris.operations._attribute_helpers import upsert_entry
from latris.operations._resolve import resolve_target
from latris.operations.commit import auto_commit
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_model, load_model
from latris.schema import Substrate
from latris.schema.model_types import get_model_type
from latris.schema.roles import RoleEntry, RoleSet


def set_role(
    target: str,
    model_type: str,
    role: str,
    *,
    root: Path | None = None,
) -> tuple[str, str]:
    """Assign a role to an entity within a model-type view.

    Returns ``(target_id, commit_sha)``.
    """
    if model_type == "sd" and role == "outcome":
        # SD roles (stock, flow, ...) are one per factor, so the outcome is kept with the SD settings.
        from latris.operations import sd as sd_ops

        return sd_ops.set_outcome(target, root=root)
    if model_type == "theory_of_change" and role == "outcome":
        raise ValueError(
            "A theory of change's outcome of interest is its impact: give the factor the level 'impact' "
            "(latris toc level <factor> impact). Outcomes along the way are short_term_outcome or long_term_outcome."
        )
    if model_type == "fault_tree" and role == "outcome":
        raise ValueError(
            "A fault tree's outcome of interest is its top event: give the factor the type 'top_event' "
            "(latris ft event <factor> top_event)."
        )
    if model_type == "bow_tie" and role == "outcome":
        raise ValueError(
            "A bow-tie's outcome of interest is its top event: give the factor the element 'top_event' "
            "(latris bowtie element <factor> top_event)."
        )
    if model_type == "event_tree" and role == "outcome":
        raise ValueError(
            "An event tree's outcomes are its end states: give the factor the element 'end_state' "
            "(latris et element <factor> end_state)."
        )
    spec = get_model_type(model_type)
    if spec.allowed_roles and role not in spec.allowed_roles:
        raise ValueError(f"{role!r} is not a valid role for {spec.display_name}. Valid: {spec.allowed_roles}")

    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    target_id = resolve_target(target, substrate)

    file_path = paths.role_path(model_type)
    # Ensure the roles directory exists on first write.
    file_path.parent.mkdir(parents=True, exist_ok=True)

    store = load_model(RoleSet, file_path) if file_path.exists() else RoleSet()
    upsert_entry(
        store,
        target_id,
        "role",
        role,
        lambda tid, v: RoleEntry(target_id=tid, value=v),
    )
    dump_model(store, file_path)

    sha = auto_commit(
        paths.root,
        subject=f"Set {model_type} role on {target_id[:15]}…: {role}",
        body=f"target: {target_id}\nmodel_type: {model_type}\nrole: {role}",
        paths=[file_path],
    )
    return target_id, sha


def get_roles(
    model_type: str,
    *,
    root: Path | None = None,
) -> RoleSet:
    """Load all role assignments for a model type."""
    paths = require_project(root)
    file_path = paths.role_path(model_type)
    return load_model(RoleSet, file_path) if file_path.exists() else RoleSet()


