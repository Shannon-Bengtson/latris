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

from latris.operations import graph_analysis as ga
from latris.operations.coherence_checks import (
    CoherenceFinding,
    check_polarity_description_coherence,
)
from latris.operations.fcm_inference import FCMInferenceResult, fcm_infer
from latris.repo.layout import ProjectPaths
from latris.repo.project import require_project
from latris.repo.yaml_io import load_model
from latris.schema import DescriptionSet, FloatSet, PolaritySet, Substrate
from latris.schema.settings import FCMSettings


def _polarity_map(paths: ProjectPaths) -> dict[str, str]:
    pol_path = paths.view_attribute_path("cld", "polarity")
    if not pol_path.exists():
        return {}
    return {e.target_id: e.value for e in load_model(PolaritySet, pol_path).entries}


# ── Graph analysis ──────────────────────────────────────────────────────


def analyse_loops(root: Path | None = None) -> list[ga.Loop]:
    """All feedback loops on the causal subgraph, R/B-classified."""
    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    polarity = _polarity_map(paths)
    raw = ga.find_all_loops(ga.causal_edges(substrate.edges))
    return [ga.classify_loop(loop, polarity) for loop in raw]


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
    store = load_model(FloatSet, weight_path) if weight_path.exists() else FloatSet()
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


# ── Coherence ───────────────────────────────────────────────────────────


def run_coherence_check(root: Path | None = None) -> list[CoherenceFinding]:
    """Flag edges whose description and CLD polarity tell opposite causal stories."""
    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    descs = load_model(DescriptionSet, paths.descriptions_yaml)
    pol_path = paths.view_attribute_path("cld", "polarity")
    pol_set = load_model(PolaritySet, pol_path) if pol_path.exists() else PolaritySet()

    desc_lookup = {(d.target_id, d.attribute): d for d in descs.entries}
    pol_lookup = {(p.target_id, p.attribute): p for p in pol_set.entries}

    return check_polarity_description_coherence(substrate.edges, desc_lookup, pol_lookup)
