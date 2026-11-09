"""Noisy-OR names the state the causes push toward; [no, yes] can't silently invert it."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import bn as bn_ops
from latris.operations._bn_canonical import expand_noisy_or
from latris.operations.edges import add_edge
from latris.operations.init import init_project
from latris.operations.nodes import add_node
from latris.schema.bn import NoisyOrEntry, NoisyOrLink

pytest.importorskip("pgmpy")


def _project(root: Path, states: list[str]) -> Path:
    init_project(root, statement="Does the volunteer leave?")
    for n in ("Leaves", "Burnout"):
        add_node(n, kind="variable", root=root)
    add_edge("Burnout", "Leaves", kind="causal", root=root)
    bn_ops.set_state_space("Burnout", ["yes", "no"], root=root)
    bn_ops.set_state_space("Leaves", states, root=root)
    bn_ops.set_cpt("Burnout", [], [0.3, 0.7], root=root)
    return root


def test_no_yes_order_must_name_the_effect(tmp_path: Path, git_identity) -> None:
    root = _project(tmp_path / "p", ["no", "yes"])
    with pytest.raises(ValueError, match="say which state .* is the effect happening .*--active yes"):
        bn_ops.set_noisy_or("Leaves", 0.1, [("Burnout", "yes", 0.6)], root=root)
    entry, _ = bn_ops.set_noisy_or("Leaves", 0.1, [("Burnout", "yes", 0.6)], active="yes", root=root)
    assert entry.active_state == "yes"
    p_leave = bn_ops.infer(query=["Leaves"], root=root).marginals
    leaves = next(iter(p_leave.values()))
    # P(leave) = 0.3·(1 − 0.9·0.4) + 0.7·0.1
    assert leaves["yes"] == pytest.approx(0.3 * (1 - 0.9 * 0.4) + 0.7 * 0.1)


def test_yes_first_is_accepted_and_stated(tmp_path: Path, git_identity) -> None:
    root = _project(tmp_path / "p", ["yes", "no"])
    entry, _ = bn_ops.set_noisy_or("Leaves", 0.1, [("Burnout", "yes", 0.6)], root=root)
    assert entry.active == "yes"
    with pytest.raises(ValueError, match="not a state"):
        bn_ops.set_noisy_or("Leaves", 0.1, [("Burnout", "yes", 0.6)], active="maybe", root=root)


def test_entries_without_active_keep_their_old_meaning() -> None:
    old = NoisyOrEntry(target_id="L", parents=["B"], states=["yes", "no"], leak=0.1,
                       links=[NoisyOrLink(parent_id="B", active_state="yes", prob=0.6)])
    new = old.model_copy(update={"states": ["no", "yes"], "active": "yes"})
    spaces = {"B": ["yes", "no"]}
    a = expand_noisy_or(old, {**spaces, "L": ["yes", "no"]})
    b = expand_noisy_or(new, {**spaces, "L": ["no", "yes"]})
    assert [r.p for r in a.rows] == [list(reversed(r.p)) for r in b.rows]
