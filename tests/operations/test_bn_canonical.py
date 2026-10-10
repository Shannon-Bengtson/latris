"""Canonical models — Noisy-OR expansion + effective CPT map.

Expansion is hand-computed; inference over a Noisy-OR node must match the same
network built from the equivalent explicit CPT.
"""

from __future__ import annotations

import pytest

from latris.operations._bn_canonical import effective_cpt_map, expand_noisy_or
from latris.operations.bn_inference import bn_infer
from latris.schema.bn import (
    CPTEntry,
    CPTRow,
    CPTSet,
    NoisyOrEntry,
    NoisyOrLink,
    NoisyOrSet,
)

pytest.importorskip("pgmpy")


def _state_spaces():
    return {
        "fail": ["yes", "no"],   # yes = active outcome (index 0)
        "A": ["on", "off"],
        "B": ["on", "off"],
    }


def _noisy_or_fail():
    return NoisyOrEntry(
        target_id="fail",
        parents=["A", "B"],
        states=["yes", "no"],
        leak=0.1,
        links=[
            NoisyOrLink(parent_id="A", active_state="on", prob=0.6),
            NoisyOrLink(parent_id="B", active_state="on", prob=0.3),
        ],
    )


def test_expansion_matches_hand_computation():
    ss = _state_spaces()
    cpt = expand_noisy_or(_noisy_or_fail(), ss)
    # P(active) = 1 - (1-leak)·∏_{active causes}(1-prob); leak=0.1, A=0.6, B=0.3.
    expected = {
        ("on", "on"): 1 - 0.9 * 0.4 * 0.7,   # 0.748
        ("on", "off"): 1 - 0.9 * 0.4,        # 0.640
        ("off", "on"): 1 - 0.9 * 0.7,        # 0.370
        ("off", "off"): 1 - 0.9,             # 0.100 (= leak)
    }
    by_combo = {(r.parent_states["A"], r.parent_states["B"]): r.p for r in cpt.rows}
    assert set(by_combo) == set(expected)
    for combo, p_active in expected.items():
        assert by_combo[combo][0] == pytest.approx(p_active)
        assert by_combo[combo][1] == pytest.approx(1 - p_active)
        assert sum(by_combo[combo]) == pytest.approx(1.0)


def test_leak_only_when_no_active_cause():
    ss = _state_spaces()
    cpt = expand_noisy_or(_noisy_or_fail(), ss)
    off_off = next(r for r in cpt.rows if r.parent_states == {"A": "off", "B": "off"})
    assert off_off.p[0] == pytest.approx(0.1)


def test_inference_matches_equivalent_explicit_cpt():
    ss = _state_spaces()
    roots = {
        "A": CPTEntry(target_id="A", parents=[], states=["on", "off"], rows=[CPTRow(p=[0.5, 0.5])]),
        "B": CPTEntry(target_id="B", parents=[], states=["on", "off"], rows=[CPTRow(p=[0.2, 0.8])]),
    }
    # Canonical version.
    canon = effective_cpt_map(CPTSet(entries=list(roots.values())), NoisyOrSet(entries=[_noisy_or_fail()]), ss)
    res_canon = bn_infer(ss, canon, query=["fail"])
    # Explicit version: same rows, hand-built.
    explicit = dict(roots)
    explicit["fail"] = expand_noisy_or(_noisy_or_fail(), ss)
    res_explicit = bn_infer(ss, explicit, query=["fail"])
    assert res_canon.marginals["fail"]["yes"] == pytest.approx(res_explicit.marginals["fail"]["yes"])
    # And a fully independent hand-check of the marginal:
    # P(fail=yes) = Σ P(A)P(B)·P(yes|A,B)
    p = (
        0.5 * 0.2 * 0.748 + 0.5 * 0.8 * 0.640 + 0.5 * 0.2 * 0.370 + 0.5 * 0.8 * 0.100
    )
    assert res_canon.marginals["fail"]["yes"] == pytest.approx(p)


def test_effective_map_errors_on_dual_definition():
    ss = _state_spaces()
    tabular = CPTSet(entries=[
        CPTEntry(target_id="fail", parents=[], states=["yes", "no"], rows=[CPTRow(p=[0.5, 0.5])]),
    ])
    with pytest.raises(ValueError, match="both a tabular CPT and a Noisy-OR"):
        effective_cpt_map(tabular, NoisyOrSet(entries=[_noisy_or_fail()]), ss)


# ── expand_noisy_or validation guards ────────────────────────────────


def test_expand_errors_when_node_has_no_state_space():
    ss = {"A": ["on", "off"], "B": ["on", "off"]}  # no "fail"
    with pytest.raises(ValueError, match="no state space"):
        expand_noisy_or(_noisy_or_fail(), ss)


def test_expand_errors_when_states_disagree_with_state_space():
    ss = _state_spaces()
    ss["fail"] = ["true", "false"]  # binary but different labels than the entry's
    with pytest.raises(ValueError, match="disagree with the declared state space"):
        expand_noisy_or(_noisy_or_fail(), ss)


def test_expand_errors_when_parent_has_no_state_space():
    ss = {"fail": ["yes", "no"], "A": ["on", "off"]}  # missing "B"
    with pytest.raises(ValueError, match="parent 'B'.*has no state space"):
        expand_noisy_or(_noisy_or_fail(), ss)


def test_expand_errors_when_parent_is_not_binary():
    ss = _state_spaces()
    ss["B"] = ["on", "off", "maybe"]
    with pytest.raises(ValueError, match="parent 'B' must be binary"):
        expand_noisy_or(_noisy_or_fail(), ss)


def test_expand_errors_when_active_state_not_in_parent_state_space():
    ss = _state_spaces()
    entry = NoisyOrEntry(
        target_id="fail",
        parents=["A", "B"],
        states=["yes", "no"],
        leak=0.1,
        links=[
            NoisyOrLink(parent_id="A", active_state="on", prob=0.6),
            NoisyOrLink(parent_id="B", active_state="HIGH", prob=0.3),  # not a state of B
        ],
    )
    with pytest.raises(ValueError, match="active_state 'HIGH' is not a state of parent 'B'"):
        expand_noisy_or(entry, ss)


def test_expand_handles_parentless_noisy_or():
    """A leak-only node with no parents expands to a single row (the leak)."""
    ss = {"fail": ["yes", "no"]}
    entry = NoisyOrEntry(target_id="fail", parents=[], states=["yes", "no"], leak=0.25, links=[])
    cpt = expand_noisy_or(entry, ss)
    assert len(cpt.rows) == 1
    assert cpt.rows[0].parent_states == {}
    assert cpt.rows[0].p[0] == pytest.approx(0.25)
    assert cpt.rows[0].p[1] == pytest.approx(0.75)
