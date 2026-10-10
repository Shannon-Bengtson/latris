"""Structural validation for the discrete BN schema (schema/bn.py).

Covers the *intrinsic* integrity the pydantic validators enforce. Cross-node
completeness and per-row normalisation are deliberately not enforced here —
they are soft, tolerance-based readiness checks (operations/readiness.py).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from latris.schema.bn import (
    CPTEntry,
    CPTRow,
    StateSpaceEntry,
)


class TestStateSpace:
    def test_valid(self) -> None:
        ss = StateSpaceEntry(target_id="node_1", states=["low", "high"])
        assert ss.states == ["low", "high"]
        assert ss.ordered is False

    def test_empty_rejected(self) -> None:
        with pytest.raises(ValidationError, match="at least one state"):
            StateSpaceEntry(target_id="node_1", states=[])

    def test_duplicate_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate state names"):
            StateSpaceEntry(target_id="node_1", states=["a", "a"])

    def test_blank_rejected(self) -> None:
        with pytest.raises(ValidationError, match="non-empty"):
            StateSpaceEntry(target_id="node_1", states=["a", ""])


class TestCPTRow:
    def test_valid(self) -> None:
        row = CPTRow(parent_states={"p": "yes"}, p=[0.2, 0.8])
        assert row.p == [0.2, 0.8]
        assert row.origin == "human-direct"

    def test_out_of_range_rejected(self) -> None:
        with pytest.raises(ValidationError, match=r"in \[0, 1\]"):
            CPTRow(p=[1.2, -0.2])

    def test_empty_rejected(self) -> None:
        with pytest.raises(ValidationError, match="at least one probability"):
            CPTRow(p=[])


class TestCPTEntry:
    def test_valid_root(self) -> None:
        cpt = CPTEntry(
            target_id="node_a",
            parents=[],
            states=["low", "high"],
            rows=[CPTRow(p=[0.3, 0.7])],
        )
        assert len(cpt.rows) == 1

    def test_valid_with_parent(self) -> None:
        cpt = CPTEntry(
            target_id="node_b",
            parents=["node_a"],
            states=["low", "med", "high"],
            rows=[
                CPTRow(parent_states={"node_a": "low"}, p=[0.6, 0.3, 0.1]),
                CPTRow(parent_states={"node_a": "high"}, p=[0.1, 0.3, 0.6]),
            ],
        )
        assert cpt.parents == ["node_a"]

    def test_row_width_must_match_states(self) -> None:
        with pytest.raises(ValidationError, match="3 states"):
            CPTEntry(
                target_id="node_b",
                parents=[],
                states=["low", "med", "high"],
                rows=[CPTRow(p=[0.5, 0.5])],  # 2 probs, 3 states
            )

    def test_row_cannot_condition_on_non_parent(self) -> None:
        with pytest.raises(ValidationError, match="non-parent"):
            CPTEntry(
                target_id="node_b",
                parents=["node_a"],
                states=["low", "high"],
                rows=[CPTRow(parent_states={"node_z": "low"}, p=[0.5, 0.5])],
            )

    def test_duplicate_states_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate state names"):
            CPTEntry(target_id="n", parents=[], states=["a", "a"], rows=[])
