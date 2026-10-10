"""Operations against the project foundation (``project.yaml``)."""

from __future__ import annotations

from pathlib import Path

from latris.operations import provenance as prov_ops
from latris.operations.batch import batch
from latris.operations.commit import auto_commit
from latris.repo import git
from latris.repo.layout import ProjectPaths
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_model, load_model
from latris.schema import ProjectFoundation
from latris.schema.provenance import ModelChoice


def load_foundation(start: Path | None = None) -> tuple[ProjectPaths, ProjectFoundation]:
    paths = require_project(start)
    return paths, load_model(ProjectFoundation, paths.project_yaml)


def update_selected_models(
    model_type_ids: list[str],
    *,
    root: Path | None = None,
) -> tuple[Path, str]:
    """Set the project's selected model types.

    Validates each ID against the model-type registry and rejects
    ``planned`` or unknown types.
    """
    from latris.schema.model_types import get_model_type

    for mid in model_type_ids:
        spec = get_model_type(mid)  # raises ValueError if unknown
        if spec.availability != "stable":
            raise ValueError(
                f"Cannot select model type {mid!r}: availability is {spec.availability!r} "
                "(only stable types allowed)"
            )

    paths, existing = load_foundation(root)
    updated = existing.model_copy(update={"selected_model_types": model_type_ids})
    dump_model(updated, paths.project_yaml)
    sha = auto_commit(
        paths.root,
        subject="Updated selected model types",
        body=f"Selected: {', '.join(model_type_ids) or '(none)'}",
        provenance="human-authored",
        paths=[paths.project_yaml],
    )
    return paths.root, sha


# ---------------------------------------------------------------------------
# Model choices — selection captured as auditable, append-only decisions.
# ``selected_model_types`` stays the live set; the ModelChoiceLog is the
# narrative of why. Each select/retire/revise appends one entry.
# ---------------------------------------------------------------------------


def add_model_choice(
    model_type_id: str,
    rationale: str = "",
    *,
    origin: str = "human-direct",
    root: Path | None = None,
) -> tuple[Path, str]:
    """Select a model type and record a ModelChoice in a single commit.

    If the type is already selected, this is treated as a rationale revision.
    """
    paths, existing = load_foundation(root)
    current = list(existing.selected_model_types or [])
    if model_type_id in current:
        return revise_model_choice(model_type_id, rationale, origin=origin, root=root)
    new_list = [*current, model_type_id]
    with batch(paths.root, subject=f"Selected model type: {model_type_id}"):
        update_selected_models(new_list, root=root)
        prov_ops.log_model_choice(model_type_id, "added", rationale, origin=origin, root=root)
    return paths.root, git.head_sha(paths.root)


def retire_model_choice(
    model_type_id: str,
    rationale: str = "",
    *,
    root: Path | None = None,
) -> tuple[Path, str]:
    """Deselect a model type and append a 'removed' ModelChoice (history kept)."""
    paths, existing = load_foundation(root)
    current = list(existing.selected_model_types or [])
    if model_type_id not in current:
        return paths.root, git.head_sha(paths.root)
    new_list = [m for m in current if m != model_type_id]
    with batch(paths.root, subject=f"Retired model type: {model_type_id}"):
        update_selected_models(new_list, root=root)
        prov_ops.log_model_choice(model_type_id, "removed", rationale, root=root)
    return paths.root, git.head_sha(paths.root)


def revise_model_choice(
    model_type_id: str,
    rationale: str,
    *,
    origin: str = "human-direct",
    root: Path | None = None,
) -> tuple[Path, str]:
    """Append a 'revised' ModelChoice updating the rationale for a model type."""
    paths = require_project(root)
    prov_ops.log_model_choice(model_type_id, "revised", rationale, origin=origin, root=root)
    return paths.root, git.head_sha(paths.root)


def current_model_choices(root: Path | None = None) -> dict[str, ModelChoice]:
    """Latest 'added'/'revised' ModelChoice per currently-selected model type.

    Types selected without a recorded choice (e.g. legacy bulk updates) are
    simply absent — callers treat that as "rationale missing".
    """
    paths, existing = load_foundation(root)
    selected = set(existing.selected_model_types or [])
    log = prov_ops.load_model_choices(root=paths.root)
    latest: dict[str, ModelChoice] = {}
    for entry in log.entries:  # append-only: later entries override earlier
        if entry.model_type_id in selected and entry.action in ("added", "revised"):
            latest[entry.model_type_id] = entry
    return latest


def set_question(start: Path | None, statement: str) -> tuple[Path, str]:
    paths, existing = load_foundation(start)
    updated = existing.model_copy(update={"statement": statement})
    dump_model(updated, paths.project_yaml)
    verb = "Set" if existing.statement != statement else "Refreshed"
    subject = f"{verb} modelling question"
    sha = auto_commit(
        paths.root,
        subject=subject,
        body=f"Modelling question: {statement}",
        provenance="human-authored",
        paths=[paths.project_yaml],
    )
    return paths.root, sha


# String fields on ProjectFoundation that `set_foundation_field` is allowed
# to write. `statement` and `selected_model_types` have their own dedicated
# operations and are deliberately excluded.
_EDITABLE_FOUNDATION_FIELDS = (
    "name",
    "background",
    "boundary",
    "exclusions",
    "predictions",
    "coverage_dimensions",
    "granularity_level",
    "audience",
)


def set_foundation_field(
    field: str,
    value: str,
    *,
    root: Path | None = None,
) -> tuple[Path, str]:
    """Set one of the project foundation's free-text fields.

    Whitelisted to: name, background, boundary, exclusions, predictions.
    Use ``set_question`` for ``statement`` and ``update_selected_models``
    for ``selected_model_types`` — those have their own commit messages.
    """
    if field not in _EDITABLE_FOUNDATION_FIELDS:
        raise ValueError(
            f"field must be one of {_EDITABLE_FOUNDATION_FIELDS}; got {field!r}"
        )
    paths, existing = load_foundation(root)
    updated = existing.model_copy(update={field: value})
    dump_model(updated, paths.project_yaml)
    sha = auto_commit(
        paths.root,
        subject=f"Set project {field}",
        body=f"{field}: {value[:200]}{'…' if len(value) > 200 else ''}",
        provenance="human-authored",
        paths=[paths.project_yaml],
    )
    return paths.root, sha
