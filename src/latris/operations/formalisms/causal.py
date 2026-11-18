"""The causal types — causal loop diagram, causal DAG and fuzzy cognitive map — as formalism plugins.

They are made of the substrate itself (factors, links, polarity, weights on links), so they have no
build-spec block and no command group of their own; the shared interpretation, readiness and diagram
code is written for them. What sets each apart is declared here, so shared code reads a field instead of
testing the type's name: loop claims for the loop maps (CLD, FCM), acyclicity claims and a top-to-bottom
diagram for the DAG, and an outcome that is an ordinary role (``latris view role <type> <factor>
outcome``). DAG's effect estimation is an analysis layer on it (``dag_estimation.py``).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from latris.operations.formalisms import Formalism, register


def _outcome_ids(model_type: str):  # noqa: ANN202
    def ids(paths: Any) -> set[str]:
        from latris.repo.yaml_io import load_model
        from latris.schema.roles import RoleSet

        path = paths.role_path(model_type)
        if not path.exists():
            return set()
        return {e.target_id for e in load_model(RoleSet, path).entries if e.value == "outcome"}

    return ids


def _set_outcome(model_type: str):  # noqa: ANN202
    def set_outcome(target: str, root: Path) -> Any:
        from latris.operations.view_roles import assign_role

        return assign_role(target, model_type, "outcome", root=root)

    return set_outcome


@dataclass(frozen=True)
class _Problem:
    target_id: str | None
    gap_type: str
    message: str


def _problems(model_type: str):  # noqa: ANN202
    def problems(root: Path) -> list[_Problem]:
        """The readiness gaps of this view; an empty model is one problem (it isn't a complete one)."""
        from latris.operations.readiness import assess_readiness
        from latris.repo.layout import ProjectPaths
        from latris.repo.yaml_io import load_model
        from latris.schema import Substrate

        if not load_model(Substrate, ProjectPaths(root).conceptual_yaml).entities:
            return [_Problem(None, "empty_model", "The model has no factors yet.")]
        return [_Problem(g.element_id or None, g.gap_type, g.message)
                for g in assess_readiness(model_type, root=root).gaps]

    return problems


def _causal(model_type: str, **declared: Any) -> Formalism:
    return Formalism(
        model_type=model_type,
        outcome_role="outcome",  # an ordinary role, set through the hook so it isn't refused as a plugin's
        outcome_refusal="",
        outcome_ids=_outcome_ids(model_type),
        set_outcome=_set_outcome(model_type),
        structure_problems=_problems(model_type),
        **declared,
    )


register(_causal("cld", loop_claims=True, polarity_labels=True))
register(_causal("dag", acyclicity_claims=True, diagram_direction="TB"))
register(_causal("fcm", loop_claims=True))
