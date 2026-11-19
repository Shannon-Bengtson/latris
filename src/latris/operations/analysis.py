"""Root-accepting orchestration for the analysis compute kernels.

The kernels in :mod:`graph_analysis`, :mod:`fcm_inference`, and
:mod:`coherence_checks` are pure — they take pre-loaded data so they stay
trivially testable. These wrappers own the data-assembly half: given a project
``root`` they load the substrate (plus polarity / weights / descriptions as
needed) and call the kernel, so the CLI and the server share one loading path
instead of duplicating it.

Graph-analysis wrappers always operate on the *causal* subgraph
(``causal_edges``): d-separation, Markov blankets, path enumeration, and the
backdoor criterion are only defined over causal edges, not the full substrate.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from latris.operations import graph_analysis as ga
from latris.operations.coherence_checks import (
    CoherenceFinding,
    check_polarity_description_coherence,
)
from latris.operations.fcm_inference import FCMInferenceResult, fcm_infer
from latris.repo.layout import ProjectPaths
from latris.repo.project import require_project
from latris.repo.yaml_io import load_model, load_model_or_default
from latris.schema import DescriptionSet, FloatSet, PolaritySet, Substrate
from latris.schema.settings import FCMSettings


def _polarity_map(paths: ProjectPaths) -> dict[str, str]:
    pol_path = paths.view_attribute_path("cld", "polarity")
    if not pol_path.exists():
        return {}
    return {e.target_id: e.value for e in load_model(PolaritySet, pol_path).entries}


# ── Graph analysis ──────────────────────────────────────────────────────


def analyse_loops(root: Path | None = None) -> list[ga.Loop]:
    """All feedback loops — causal links plus stock-and-flow structure — R/B-classified."""
    from latris.operations.feedback import feedback_edges, link_polarity

    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    polarity = {**link_polarity(substrate.edges, paths), **_polarity_map(paths)}
    raw = ga.find_all_loops(feedback_edges(substrate.edges, paths))
    return [ga.classify_loop(loop, polarity) for loop in raw]


def loop_model_types(loops: list[ga.Loop], root: Path | None = None) -> list[list[str]]:
    """For each loop, the selected model types it lies in: the whole-map types always, a simulation or
    network only when every factor on the loop belongs to it (``operations/membership.py``)."""
    from latris.operations.membership import members
    from latris.schema import ProjectFoundation

    paths = require_project(root)
    selected = load_model(ProjectFoundation, paths.project_yaml).selected_model_types or ["cld"]
    scopes = {mt: members(paths, mt) for mt in selected}
    return [
        [mt for mt, scope in scopes.items() if scope is None or set(loop.node_ids) <= scope.entity_ids]
        for loop in loops
    ]


def analyse_propagation(entity_id: str, root: Path | None = None) -> list[ga.PropagationEffect]:
    """Qualitative impact of an increase in ``entity_id`` across the causal subgraph."""
    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    polarity = _polarity_map(paths)
    return ga.propagate_polarity(entity_id, ga.causal_edges(substrate.edges), polarity)


def analyse_d_separation(
    x_ids: Iterable[str],
    y_ids: Iterable[str],
    given_ids: Iterable[str] = (),
    root: Path | None = None,
) -> bool:
    """Whether X ⊥ Y given Z on the causal subgraph."""
    substrate = load_model(Substrate, require_project(root).conceptual_yaml)
    return ga.d_separation(
        ga.causal_edges(substrate.edges), set(x_ids), set(y_ids), set(given_ids)
    )


def analyse_blanket(entity_id: str, root: Path | None = None) -> set[str]:
    """Markov blanket of ``entity_id`` on the causal subgraph."""
    substrate = load_model(Substrate, require_project(root).conceptual_yaml)
    return ga.markov_blanket(entity_id, ga.causal_edges(substrate.edges))


def analyse_paths(from_id: str, to_id: str, root: Path | None = None) -> list[ga.GraphPath]:
    """All paths from ``from_id`` to ``to_id`` on the causal subgraph."""
    substrate = load_model(Substrate, require_project(root).conceptual_yaml)
    return ga.enumerate_paths(from_id, to_id, ga.causal_edges(substrate.edges))


def analyse_adjustment_sets(
    exposure_id: str, outcome_id: str, root: Path | None = None
) -> list[set[str]]:
    """Valid backdoor adjustment sets for exposure → outcome on the causal subgraph."""
    substrate = load_model(Substrate, require_project(root).conceptual_yaml)
    return ga.adjustment_sets(exposure_id, outcome_id, ga.causal_edges(substrate.edges))


# ── FCM ─────────────────────────────────────────────────────────────────


def infer_fcm(
    root: Path | None = None,
    *,
    initial_activations: dict[str, float] | None = None,
    clamped: dict[str, float] | None = None,
    settings: FCMSettings | None = None,
) -> FCMInferenceResult:
    """Run FCM inference to steady state from a project's edges + weights."""
    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    weight_path = paths.view_attribute_path("fcm", "weight")
    store = load_model_or_default(FloatSet, weight_path)
    weight_map = {e.target_id: e.value for e in store.entries}
    entity_ids = [e.id for e in substrate.entities]
    return fcm_infer(
        substrate.edges,
        weight_map,
        entity_ids,
        initial_activations=initial_activations,
        clamped=clamped,
        settings=settings,
    )


def fcm_steady_state(
    *,
    clamp: dict[str, float] | None = None,
    initial: dict[str, float] | None = None,
    settings: dict[str, Any] | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    """FCM inference as a result: factors named by label (as a build spec names them), each factor's
    activation at the end, ranked, whether it settled, and the scenario (``clamp``) it ran under."""
    from latris.operations._resolve import resolve_target

    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    label = {e.id: e.label for e in substrate.entities}
    ids = lambda d: {resolve_target(k, substrate): float(v) for k, v in (d or {}).items()}  # noqa: E731
    for name, values in (("clamp", clamp), ("initial", initial)):
        for k, v in (values or {}).items():
            if not 0.0 <= float(v) <= 1.0:
                raise ValueError(f"{name} {k} = {v}: activations run from 0 to 1")
    given = {k: v for k, v in (settings or {}).items() if v is not None}
    result = infer_fcm(paths.root, initial_activations=ids(initial) or None, clamped=ids(clamp) or None,
                       settings=FCMSettings(**given) if given else None)
    clamped = ids(clamp)
    ranked = sorted(result.activations.items(), key=lambda kv: -kv[1])
    return {
        "activations": [{"id": i, "label": label.get(i, i), "activation": round(a, 4), "clamped": i in clamped}
                        for i, a in ranked],
        "converged": result.converged,
        "iterations": result.iterations,
        "clamp": {label.get(i, i): v for i, v in clamped.items()},
        "initial": {label.get(i, i): v for i, v in ids(initial).items()},
        "settings": given,
    }


def describe_fcm(p: dict[str, Any]) -> str:
    top = [a for a in p["activations"] if not a["clamped"]][:3]
    under = f" with {', '.join(f'{k} held at {v:g}' for k, v in p['clamp'].items())}" if p["clamp"] else ""
    head = ", ".join(f"{a['label']} {a['activation']:.2f}" for a in top) or "no free factors"
    settled = f"{'settled' if p['converged'] else 'not settled'} after {p['iterations']} steps"
    return f"Fuzzy cognitive map{under}: most active {head} ({settled})"


def record_fcm(payload: dict[str, Any], *, root: Path | None = None) -> tuple[str, str]:
    """Record a steady state for the report; one per scenario (its clamp)."""
    import json

    from latris.operations.analysis_results import record_result

    sha, run = record_result(
        kind="fcm-inference",
        key="fcm-inference:" + json.dumps(payload["clamp"], sort_keys=True),
        payload=payload,
        purpose="simulation",
        algorithm=f"FCM iteration to steady state ({payload['settings'].get('transfer_function', 'sigmoid')} "
                  "transfer, Kosko update)",
        library_version="latris",
        summary=describe_fcm(payload),
        model_type="fcm",
        hyperparameters={"clamp": payload["clamp"], "initial": payload["initial"], **payload["settings"]},
        root=root,
    )
    return sha, run.id


# ── Coherence ───────────────────────────────────────────────────────────


def run_coherence_check(root: Path | None = None) -> list[CoherenceFinding]:
    """Flag edges whose description and CLD polarity tell opposite causal stories."""
    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    descs = load_model(DescriptionSet, paths.descriptions_yaml)
    pol_path = paths.view_attribute_path("cld", "polarity")
    pol_set = load_model_or_default(PolaritySet, pol_path)

    desc_lookup = {(d.target_id, d.attribute): d for d in descs.entries}
    pol_lookup = {(p.target_id, p.attribute): p for p in pol_set.entries}

    return check_polarity_description_coherence(substrate.edges, desc_lookup, pol_lookup)
