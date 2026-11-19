"""The qualitative model types — causal loop diagram, causal DAG and fuzzy cognitive map — as plugins.

They predate the registry and are the whole map: every factor and link (``membership.QUALITATIVE``).
Registering them closes latris#3, so the wiring guard covers every stable type and no reader needs
"is this one of the old types?". What they bring is small, because the shared code already treats a
causal map as its default:

- their outcome is an ordinary ``outcome`` role (``latris view role cld <factor> outcome``);
- their structure problems are their readiness gaps (CLD: no feedback loop; DAG: a cycle), with the
  named validators (``loops_present``, ``acyclicity``) kept in ``readiness._STRUCTURAL_VALIDATORS``;
- they have no build-spec block of their own: a link's polarity (CLD) and weight (FCM) ride on the
  link in a spec;
- graph-centrality claims, the generic Mermaid sketch and the interpretation's causal-map sections
  are the shared defaults;
- FCM brings its ``latris fcm`` commands and ``/api/fcm`` routes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from latris.operations.formalisms import Formalism, register


@dataclass(frozen=True)
class _Problem:
    target_id: str | None
    gap_type: str
    message: str


def _outcome_ids(model_type: str):
    def ids(paths) -> set[str]:  # noqa: ANN001
        path = paths.role_path(model_type)
        if not path.exists():
            return set()
        from latris.repo.yaml_io import load_model
        from latris.schema.roles import RoleSet

        return {e.target_id for e in load_model(RoleSet, path).entries if e.value == "outcome"}

    return ids


def _set_outcome(model_type: str):
    def set_outcome(target: str, root: Path):
        from latris.operations.view_roles import set_role

        return set_role(target, model_type, "outcome", root=root)

    return set_outcome


def _problems(model_type: str):
    def problems(root: Path) -> list[_Problem]:
        from latris.operations.readiness import assess_readiness
        from latris.repo.layout import ProjectPaths
        from latris.repo.yaml_io import load_model
        from latris.schema import Substrate

        if not load_model(Substrate, ProjectPaths(root).conceptual_yaml).entities:
            return [_Problem(None, "empty_model", "No factors yet.")]
        gaps = assess_readiness(model_type, root=root).gaps
        return [_Problem(g.element_id or None, g.gap_type, g.message) for g in gaps]

    return problems


def _dag_claims(paths, section: str) -> list[str]:  # noqa: ANN001
    """A DAG's structure claim: acyclic as its readiness confirms, or how many cycles stop it being one."""
    if section != "structure":
        return []
    from latris.operations.graph_analysis import causal_edges, find_all_loops
    from latris.operations.readiness import assess_readiness
    from latris.repo.yaml_io import load_model
    from latris.schema import Substrate

    if not any(g.gap_type == "cycle_detected" for g in assess_readiness("dag", root=paths.root).gaps):
        return ["DAG structure confirmed (acyclic by readiness gate)."]
    loops = find_all_loops(causal_edges(load_model(Substrate, paths.conceptual_yaml).edges))
    return [
        f"DAG readiness FAILS: substrate contains {len(loops)} cycle(s). The substrate is not projectable to a "
        "valid DAG view without dropping or redirecting edges."
    ]


_REFUSAL = "Mark the factor the model explains with `latris view role {t} <factor> outcome`."

for _t, _label, _extra in (
    ("cld", "Loop map", {"feedback_claims": True, "link_attribute": ("polarity", "polarity (+/-)")}),
    ("dag", "Causal DAG", {"diagram_direction": "TB", "claims": _dag_claims}),
    ("fcm", "FCM", {"feedback_claims": True, "link_attribute": ("weight", "weight (float in [-1, +1])"),
                    "cli": ("latris.cli.fcm_cmd", "fcm"),
                    "routes": "latris.server.routes.fcm"}),
):
    register(Formalism(
        model_type=_t,
        outcome_role="outcome",
        outcome_refusal=_REFUSAL.format(t=_t),
        outcome_ids=_outcome_ids(_t),
        set_outcome=_set_outcome(_t),
        structure_problems=_problems(_t),
        whole_map=True,
        source_label=_label,
        **_extra,
    ))
