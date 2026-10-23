"""SD readiness validators and operations against a real project.

Validators are exercised through ``operations.sd.check()``, directly via a
hand-built ValidationContext (mirroring test_bn_readiness.py), and through the
registry-driven ``assess_readiness("sd")`` now that SD is stable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations import sd as sd_ops
from latris.operations.readiness import _STRUCTURAL_VALIDATORS, SD_VALIDATORS, ValidationContext
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model
from latris.schema import Substrate
from latris.schema.model_types import get_model_type
from latris.schema.roles import RoleSet
from tests.conftest import SD_BATHTUB_ROLES


def _gap_types(root: Path) -> set[str]:
    return {g.gap_type for g in sd_ops.check(root=root)}


def test_unparameterised_model_reports_classification_gaps(sd_diagram_root):
    root = sd_diagram_root
    gaps = sd_ops.check(root=root)
    assert {g.gap_type for g in gaps} == {"unclassified", "no_stocks"}
    assert {g.element_label for g in gaps if g.gap_type == "unclassified"} == {"Water", "Inflow", "Outflow", "Inflow Rate", "Drain Rate", "Tap",
                                               "Drain"}


def test_complete_model_passes(sd_bathtub_root):
    root = sd_bathtub_root
    assert sd_ops.check(root=root) == []


def test_assess_readiness_complete_model_can_switch(sd_bathtub_root):
    from latris.operations.readiness import assess_readiness

    ready = assess_readiness("sd", root=sd_bathtub_root)
    assert ready.score == 100 and ready.can_switch


def test_assess_readiness_incomplete_model(sd_diagram_root):
    from latris.operations.readiness import assess_readiness

    not_ready = assess_readiness("sd", root=sd_diagram_root)
    assert not_ready.score == 0 and not not_ready.can_switch
    assert {g.gap_type for g in not_ready.gaps} == {"unclassified", "no_stocks"}


def test_validators_registered_and_wired_to_registry():
    spec = get_model_type("sd")
    assert spec.structural_validators == SD_VALIDATORS
    assert all(name in _STRUCTURAL_VALIDATORS for name in SD_VALIDATORS)


def test_each_validator_reports_only_its_category(sd_bathtub_root):
    root = sd_bathtub_root
    # Break units only: the outflow now yields liter / year**2.
    sd_ops.set_constant("Drain Rate", 0.1, "1/year**2", root=root)
    paths = ProjectPaths(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    ctx = ValidationContext(
        substrate=substrate,
        view_entity_ids=[e.id for e in substrate.entities],
        view_edge_ids=[e.id for e in substrate.edges],
        spec=get_model_type("sd"),
        roles=load_model(RoleSet, paths.role_path("sd")),
        paths=paths,
    )
    by_validator = {name: _STRUCTURAL_VALIDATORS[name](ctx) for name in SD_VALIDATORS}
    assert [g.gap_type for g in by_validator["sd_dimensional_consistency"]] == ["units_mismatch"]
    assert all(not gaps for name, gaps in by_validator.items() if name != "sd_dimensional_consistency")


def test_missing_values_and_equations(sd_diagram_root):
    root = sd_diagram_root
    for label, role in SD_BATHTUB_ROLES:
        sd_ops.set_role(label, role, root=root)
    assert _gap_types(root) == {"missing_initial_value", "missing_constant_value", "missing_equation"}


def test_causal_edge_into_stock_is_flagged(sd_bathtub_root):
    """Stocks change only through flows — an information link into one is a structural gap."""
    root = sd_bathtub_root
    extra, _ = node_ops.add_node("Rainfall", kind="variable", root=root)
    sd_ops.set_role("Rainfall", "constant", root=root)
    sd_ops.set_constant("Rainfall", 1, "liter", root=root)
    water_id = next(n.id for n in node_ops.list_nodes(root=root) if n.label == "Water")
    edge_ops.add_edge(extra.id, water_id, kind="causal", root=root)
    assert _gap_types(root) == {"stock_causal_input"}


# ── operations guards ────────────────────────────────────────────────


def test_equation_requires_flow_or_auxiliary_role(sd_diagram_root):
    root = sd_diagram_root
    with pytest.raises(ValueError, match="no SD role yet"):
        sd_ops.set_equation("Inflow", "1", "liter/year", root=root)
    sd_ops.set_role("Water", "stock", root=root)
    with pytest.raises(ValueError, match="classified as stock"):
        sd_ops.set_equation("Water", "1", "liter", root=root)


def test_equation_rejects_unknown_names_self_reference_and_bad_units(sd_bathtub_root):
    root = sd_bathtub_root
    with pytest.raises(ValueError, match="'ghost'"):
        sd_ops.set_equation("Outflow", "water * ghost", "liter/year", root=root)
    with pytest.raises(ValueError, match="refers to itself"):
        sd_ops.set_equation("Outflow", "outflow * 2", "liter/year", root=root)
    with pytest.raises(ValueError, match="unknown or malformed units"):
        sd_ops.set_equation("Outflow", "water * drain_rate", "bananas", root=root)
    with pytest.raises(ValueError, match="cannot parse"):
        sd_ops.set_equation("Outflow", "water *", "liter/year", root=root)


def test_role_must_be_allowed(sd_diagram_root):
    root = sd_diagram_root
    with pytest.raises(ValueError, match="not a valid role"):
        sd_ops.set_role("Water", "reservoir", root=root)


def test_value_setters_check_roles(sd_bathtub_root):
    root = sd_bathtub_root
    with pytest.raises(ValueError, match="needs a stock"):
        sd_ops.set_initial_value("Inflow", 1, "liter", root=root)
    with pytest.raises(ValueError, match="needs a constant"):
        sd_ops.set_constant("Water", 1, "liter", root=root)
    with pytest.raises(ValueError, match="needs a flow or auxiliary"):
        sd_ops.set_table("Water", [(0, 0), (1, 1)], "dimensionless", "dimensionless", root=root)


def test_upsert_replaces_and_commits(sd_bathtub_root):
    root = sd_bathtub_root
    entry, sha = sd_ops.set_constant("Drain Rate", 0.2, "1/year", origin="human-elicited", source_id="src_x",
                                     root=root)
    consts = sd_ops.get_constants(root=root).entries
    assert len([c for c in consts if c.target_id == entry.target_id]) == 1
    assert entry.value == 0.2 and entry.origin == "human-elicited" and entry.source_id == "src_x"
    assert len(sha) >= 7


# ── simulation + run provenance ──────────────────────────────────────


def test_simulate_and_record(sd_bathtub_root):
    root = sd_bathtub_root
    pytest.importorskip("scipy")
    from latris.operations.analysis_runs import list_runs

    result = sd_ops.simulate(final_time=10, dt=0.5, saveper=5, root=root)
    assert result.success
    assert len(result.times) == 3

    sha, run_id = sd_ops.record_simulation(result, root=root)
    runs = list_runs(root=root)
    run = next(r for r in runs if r.id == run_id)
    assert run.purpose == "simulation"
    assert run.target_view == "sd"
    assert run.algorithm.startswith("scipy.integrate.solve_ivp[RK45")
    assert run.output_artifacts and (root / run.output_artifacts[0]).exists()
    assert "Water 100 →" in run.output_summary
    assert sha


def test_simulate_refuses_incomplete_model(sd_diagram_root):
    root = sd_diagram_root
    with pytest.raises(ValueError, match="not ready to simulate"):
        sd_ops.simulate(root=root)


def test_simulate_rejects_bad_settings(sd_bathtub_root):
    root = sd_bathtub_root
    with pytest.raises(ValueError):
        sd_ops.simulate(method="midpoint", root=root)
