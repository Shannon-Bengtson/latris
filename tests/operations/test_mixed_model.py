"""One map, three model types: membership drives readiness, staleness and claims consistently."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import sd as sd_ops
from latris.repo.layout import ProjectPaths
from tests.conftest import build_with_template_identity, clone_project
from tests.mixed_model import build_mixed_model


@pytest.fixture(scope="module")
def _template_mixed(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_with_template_identity(lambda: build_mixed_model(tmp_path_factory.mktemp("tpl_mixed") / "proj"))


@pytest.fixture
def mixed_root(_template_mixed: Path, tmp_path: Path, git_identity) -> Path:
    return clone_project(_template_mixed, tmp_path / "proj")


def _labels(root: Path, ids) -> set[str]:
    from latris.repo.yaml_io import load_model
    from latris.schema import Substrate

    sub = load_model(Substrate, ProjectPaths(root).conceptual_yaml)
    by_id = {e.id: e.label for e in sub.entities}
    return {by_id[i] for i in ids if i in by_id}


# ── membership ───────────────────────────────────────────────────────


def test_each_type_is_made_of_its_own_factors(mixed_root):
    from latris.operations.membership import members

    paths = ProjectPaths(mixed_root)
    assert members(paths, "cld") is None  # the loop map is the whole map
    sd = _labels(mixed_root, members(paths, "sd").entity_ids)
    assert "Water-column phosphorus" in sd and "Catchment load" not in sd and "Bloom" not in sd
    assert _labels(mixed_root, members(paths, "bn").entity_ids) == {
        "Hot week", "Bloom", "Customer exceedance", "Barrier fails"}


# ── the simulation inside a loop map ─────────────────────────────────


def test_loop_map_links_into_the_simulation_dont_block_it(mixed_root):
    assert sd_ops.check(root=mixed_root) == []
    result = sd_ops.simulate(final_time=10, root=mixed_root)
    assert result.success


def test_loop_map_links_are_reported_as_advisories(mixed_root):
    advisories = [g for g in sd_ops.check(advisories=True, root=mixed_root) if g.severity == "advisory"]
    kinds = {(g.gap_type, g.element_label) for g in advisories}
    assert ("outside_link", "Catchment load → Water-column phosphorus") in kinds
    assert ("outside_link", "Bottom-water anoxia → Internal P release") in kinds
    assert ("stock_causal_input", "Internal P release → Water-column phosphorus") in kinds


def test_an_sd_only_model_still_flags_unclassified_parents(sd_diagram_root):
    gaps = {g.gap_type for g in sd_ops.check(root=sd_diagram_root)}
    assert "unclassified" in gaps


def test_not_ready_error_names_the_factor(mixed_root):
    from latris.operations._sd_eval import EquationError

    sd_ops.set_role("Treatment cost", "flow", root=mixed_root)  # a flow that fills nothing
    with pytest.raises(EquationError, match="Treatment cost: "):
        sd_ops.simulate(final_time=5, root=mixed_root)


# ── the network beside a loop map ────────────────────────────────────


def test_loop_map_cycles_dont_make_the_network_unready(mixed_root):
    from latris.operations.readiness import assess_readiness

    r = assess_readiness("bn", root=mixed_root)
    assert r.score > 0, r.gaps
    assert "cycle_detected" not in {g.gap_type for g in r.gaps}


def test_interpretation_has_sections_for_every_type(mixed_root):
    from latris.operations.interpret import initialise_sections

    store, _, skipped = initialise_sections(root=mixed_root)
    assert skipped == []
    assert {s.model_type for s in store.sections} >= {"cld", "sd", "bn"}


def test_empty_network_sharing_a_loop_map_says_so(tmp_path, git_identity):
    from latris.operations.edges import add_edge
    from latris.operations.init import init_project
    from latris.operations.nodes import add_node
    from latris.operations.project import update_selected_models
    from latris.operations.readiness import assess_readiness

    root = tmp_path / "proj"
    init_project(root, statement="Q?")
    a, _ = add_node("A", root=root)
    b, _ = add_node("B", root=root)
    add_edge(a.id, b.id, kind="causal", root=root)
    add_edge(b.id, a.id, kind="causal", root=root)
    update_selected_models(["cld", "bn"], root=root)
    r = assess_readiness("bn", root=root)
    assert r.score == 0
    assert [g.gap_type for g in r.gaps] == ["empty_network"]


# ── staleness ────────────────────────────────────────────────────────


def test_editing_the_loop_map_leaves_simulation_results_fresh(mixed_root):
    from latris.operations.analysis_results import report_results
    from latris.operations.edges import add_edge
    from latris.operations.nodes import add_node

    sd_ops.record_simulation(sd_ops.simulate(final_time=10, root=mixed_root), root=mixed_root)
    new, _ = add_node("Algaecide dosing", root=mixed_root)
    from latris.operations._resolve import resolve_entity
    from latris.repo.yaml_io import load_model
    from latris.schema import Substrate

    sub = load_model(Substrate, ProjectPaths(mixed_root).conceptual_yaml)
    add_edge(new.id, resolve_entity("Cyanobacteria biomass", sub.entities).id, kind="causal", root=mixed_root)
    [res] = [r for r in report_results(model_types=["sd"], root=mixed_root)]
    assert not res.stale

    sd_ops.set_constant("Settling rate", 2.0, "1/year", root=mixed_root)
    [res] = [r for r in report_results(model_types=["sd"], root=mixed_root)]
    assert res.stale


def test_runs_recorded_before_keep_their_whole_map_fingerprint(mixed_root):
    from latris.operations.analysis_results import fingerprint
    from latris.operations.nodes import add_node

    paths = ProjectPaths(mixed_root)
    v1, v2 = fingerprint(paths, "sd", version=1), fingerprint(paths, "sd", version=2)
    add_node("Something in the loop map", root=mixed_root)
    assert fingerprint(paths, "sd", version=1) != v1
    assert fingerprint(paths, "sd", version=2) == v2


# ── taking a factor out of a model type ─────────────────────────────


def test_unset_role_keeps_the_factor_and_its_links(mixed_root):
    from latris.operations.membership import members
    from latris.operations.nodes import list_nodes

    sd_ops.set_role("Treatment cost", "auxiliary", root=mixed_root)
    assert sd_ops.check(root=mixed_root)  # an auxiliary with no equation
    _, removed, _ = sd_ops.unset_role("Treatment cost", root=mixed_root)
    assert removed == 1
    assert sd_ops.check(root=mixed_root) == []
    assert "Treatment cost" in {n.label for n in list_nodes(mixed_root)}
    assert "Treatment cost" not in _labels(mixed_root, members(ProjectPaths(mixed_root), "sd").entity_ids)


def test_unset_role_drops_the_values(mixed_root):
    _, removed, _ = sd_ops.unset_role("Release rate", root=mixed_root)
    assert removed >= 2  # role + constant
    assert "Release rate" not in {c.target_id for c in sd_ops.get_constants(root=mixed_root).entries}


def test_remove_states_refuses_a_parent_and_removes_a_leaf(mixed_root):
    from latris.operations import bn as bn_ops

    with pytest.raises(ValueError, match="parent"):
        bn_ops.remove_states("Hot week", root=mixed_root)
    _, removed, _ = bn_ops.remove_states("Customer exceedance", root=mixed_root)
    assert removed >= 2  # states + table
    assert len(bn_ops.get_state_spaces(root=mixed_root).entries) == 3
