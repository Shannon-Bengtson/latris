"""Readiness validators for discrete Bayesian Networks.

BN is still "planned", so assess_readiness() short-circuits before running these
validators. They are exercised directly here (and via `bn check` later) by
building a ValidationContext over a real project, exactly as operations/bn.py
will once it lands.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations.edges import add_edge
from latris.operations.init import init_project
from latris.operations.nodes import add_node
from latris.operations.readiness import (
    ValidationContext,
    _check_cpt_complete,
    _check_state_space_defined,
)
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import dump_model, load_model
from latris.schema import Substrate
from latris.schema.bn import CPTEntry, CPTRow, CPTSet, StateSpaceEntry, StateSpaceSet
from latris.schema.model_types import get_model_type
from latris.schema.roles import RoleSet


def _ctx(root: Path) -> ValidationContext:
    paths = ProjectPaths(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    return ValidationContext(
        substrate=substrate,
        view_entity_ids=[e.id for e in substrate.entities],
        view_edge_ids=[e.id for e in substrate.edges],
        spec=get_model_type("bn"),
        roles=RoleSet(),
        paths=paths,
    )


def _write(root: Path, attribute: str, model) -> None:
    path = ProjectPaths(root).view_attribute_path("bn", attribute)
    path.parent.mkdir(parents=True, exist_ok=True)
    dump_model(model, path)


@pytest.fixture
def rain_wet(tmp_path: Path, git_identity):
    """Two-node BN: rain -> wet."""
    root = tmp_path / "demo"
    init_project(root, statement="BN readiness test")
    rain, _ = add_node("Rain", kind="variable", root=root)
    wet, _ = add_node("Wet", kind="variable", root=root)
    add_edge(rain.id, wet.id, kind="causal", root=root)
    return root, rain.id, wet.id


class TestStateSpaceDefined:
    def test_all_missing(self, rain_wet):
        root, _, _ = rain_wet
        gaps = _check_state_space_defined(_ctx(root))
        assert {g.gap_type for g in gaps} == {"missing_state_space"}
        assert len(gaps) == 2  # both nodes

    def test_complete(self, rain_wet):
        root, rain_id, wet_id = rain_wet
        _write(root, "state_space", StateSpaceSet(entries=[
            StateSpaceEntry(target_id=rain_id, states=["yes", "no"]),
            StateSpaceEntry(target_id=wet_id, states=["yes", "no"]),
        ]))
        assert _check_state_space_defined(_ctx(root)) == []


class TestCptComplete:
    def _state_spaces(self, root, rain_id, wet_id):
        _write(root, "state_space", StateSpaceSet(entries=[
            StateSpaceEntry(target_id=rain_id, states=["yes", "no"]),
            StateSpaceEntry(target_id=wet_id, states=["yes", "no"]),
        ]))

    def test_missing_cpt(self, rain_wet):
        root, rain_id, wet_id = rain_wet
        self._state_spaces(root, rain_id, wet_id)
        gaps = _check_cpt_complete(_ctx(root))
        assert {g.gap_type for g in gaps} == {"missing_cpt"}
        assert len(gaps) == 2

    def test_complete_and_normalised(self, rain_wet):
        root, rain_id, wet_id = rain_wet
        self._state_spaces(root, rain_id, wet_id)
        _write(root, "cpt", CPTSet(entries=[
            CPTEntry(target_id=rain_id, parents=[], states=["yes", "no"],
                     rows=[CPTRow(p=[0.2, 0.8])]),
            CPTEntry(target_id=wet_id, parents=[rain_id], states=["yes", "no"], rows=[
                CPTRow(parent_states={rain_id: "yes"}, p=[0.9, 0.1]),
                CPTRow(parent_states={rain_id: "no"}, p=[0.2, 0.8]),
            ]),
        ]))
        assert _check_cpt_complete(_ctx(root)) == []

    def test_incomplete_missing_combination(self, rain_wet):
        root, rain_id, wet_id = rain_wet
        self._state_spaces(root, rain_id, wet_id)
        _write(root, "cpt", CPTSet(entries=[
            CPTEntry(target_id=rain_id, parents=[], states=["yes", "no"],
                     rows=[CPTRow(p=[0.2, 0.8])]),
            CPTEntry(target_id=wet_id, parents=[rain_id], states=["yes", "no"], rows=[
                CPTRow(parent_states={rain_id: "yes"}, p=[0.9, 0.1]),
                # missing the rain=no row
            ]),
        ]))
        gaps = _check_cpt_complete(_ctx(root))
        assert any(g.gap_type == "cpt_incomplete" and g.element_id == wet_id for g in gaps)

    def test_unnormalised_row(self, rain_wet):
        root, rain_id, wet_id = rain_wet
        self._state_spaces(root, rain_id, wet_id)
        _write(root, "cpt", CPTSet(entries=[
            CPTEntry(target_id=rain_id, parents=[], states=["yes", "no"],
                     rows=[CPTRow(p=[0.5, 0.2])]),  # sums to 0.7
            CPTEntry(target_id=wet_id, parents=[rain_id], states=["yes", "no"], rows=[
                CPTRow(parent_states={rain_id: "yes"}, p=[0.9, 0.1]),
                CPTRow(parent_states={rain_id: "no"}, p=[0.2, 0.8]),
            ]),
        ]))
        gaps = _check_cpt_complete(_ctx(root))
        assert any(g.gap_type == "cpt_unnormalised" and g.element_id == rain_id for g in gaps)
