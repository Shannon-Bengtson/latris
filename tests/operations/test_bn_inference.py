"""Exact BN inference (operations/bn_inference.py + the pgmpy adapter).

Posteriors are hand-computed. The two-parent OR network in particular would
give wrong answers if the pgmpy CPT column ordering were mapped incorrectly,
so it guards the adapter's most error-prone step.
"""

from __future__ import annotations

import pytest

from latris.operations.bn_inference import bn_infer
from latris.schema.bn import CPTEntry, CPTRow

pytest.importorskip("pgmpy")


def _rain_wet():
    """rain -> wet. P(rain=yes)=0.2; P(wet=yes|rain=yes)=0.9, |rain=no)=0.1."""
    state_spaces = {"rain": ["yes", "no"], "wet": ["yes", "no"]}
    cpts = {
        "rain": CPTEntry(target_id="rain", parents=[], states=["yes", "no"],
                         rows=[CPTRow(p=[0.2, 0.8])]),
        "wet": CPTEntry(target_id="wet", parents=["rain"], states=["yes", "no"], rows=[
            CPTRow(parent_states={"rain": "yes"}, p=[0.9, 0.1]),
            CPTRow(parent_states={"rain": "no"}, p=[0.1, 0.9]),
        ]),
    }
    return state_spaces, cpts


class TestRainWet:
    def test_prior_marginal(self):
        ss, cpts = _rain_wet()
        res = bn_infer(ss, cpts, query=["wet"])
        # P(wet=yes) = 0.9*0.2 + 0.1*0.8 = 0.26
        assert res.marginals["wet"]["yes"] == pytest.approx(0.26)

    def test_posterior_given_evidence(self):
        ss, cpts = _rain_wet()
        res = bn_infer(ss, cpts, query=["rain"], evidence={"wet": "yes"})
        # P(rain=yes | wet=yes) = 0.18 / 0.26 = 0.6923...
        assert res.marginals["rain"]["yes"] == pytest.approx(0.6923076923, abs=1e-9)
        assert res.evidence == {"wet": "yes"}

    def test_all_marginals_when_no_query(self):
        ss, cpts = _rain_wet()
        res = bn_infer(ss, cpts)
        assert res.marginals["rain"]["yes"] == pytest.approx(0.2)
        assert res.marginals["wet"]["yes"] == pytest.approx(0.26)

    def test_evidence_node_excluded_from_default_query(self):
        ss, cpts = _rain_wet()
        res = bn_infer(ss, cpts, evidence={"rain": "yes"})
        assert "rain" not in res.marginals
        assert res.marginals["wet"]["yes"] == pytest.approx(0.9)


def _or_network():
    """C = A OR B, with P(A=t)=P(B=t)=0.5. P(C=t)=0.75."""
    ss = {"A": ["t", "f"], "B": ["t", "f"], "C": ["t", "f"]}
    cpts = {
        "A": CPTEntry(target_id="A", parents=[], states=["t", "f"], rows=[CPTRow(p=[0.5, 0.5])]),
        "B": CPTEntry(target_id="B", parents=[], states=["t", "f"], rows=[CPTRow(p=[0.5, 0.5])]),
        "C": CPTEntry(target_id="C", parents=["A", "B"], states=["t", "f"], rows=[
            CPTRow(parent_states={"A": "t", "B": "t"}, p=[1.0, 0.0]),
            CPTRow(parent_states={"A": "t", "B": "f"}, p=[1.0, 0.0]),
            CPTRow(parent_states={"A": "f", "B": "t"}, p=[1.0, 0.0]),
            CPTRow(parent_states={"A": "f", "B": "f"}, p=[0.0, 1.0]),
        ]),
    }
    return ss, cpts


class TestTwoParents:
    def test_or_marginal(self):
        ss, cpts = _or_network()
        res = bn_infer(ss, cpts, query=["C"])
        assert res.marginals["C"]["t"] == pytest.approx(0.75)

    def test_explaining_away_certain(self):
        # C=f happens only when A=f AND B=f, so P(A=t | C=f) = 0.
        ss, cpts = _or_network()
        res = bn_infer(ss, cpts, query=["A"], evidence={"C": "f"})
        assert res.marginals["A"]["t"] == pytest.approx(0.0)


class TestErrors:
    def test_invalid_evidence_state(self):
        ss, cpts = _rain_wet()
        with pytest.raises(ValueError, match="not a valid state"):
            bn_infer(ss, cpts, evidence={"wet": "maybe"})

    def test_unknown_evidence_node(self):
        ss, cpts = _rain_wet()
        with pytest.raises(ValueError, match="not in the network"):
            bn_infer(ss, cpts, evidence={"ghost": "yes"})

    def test_unknown_query_node(self):
        ss, cpts = _rain_wet()
        with pytest.raises(ValueError, match="not in the network"):
            bn_infer(ss, cpts, query=["ghost"])

    def test_incomplete_cpt_rejected_at_build(self):
        ss, cpts = _rain_wet()
        # Drop the rain=no row — schema allows it (soft), but the engine must not.
        cpts["wet"] = CPTEntry(target_id="wet", parents=["rain"], states=["yes", "no"],
                               rows=[CPTRow(parent_states={"rain": "yes"}, p=[0.9, 0.1])])
        with pytest.raises(ValueError, match="missing the row"):
            bn_infer(ss, cpts, query=["wet"])


# ── Brute-force cross-check ────────────────────────────────────────────────
# An independent reference implementation: build the full joint by enumerating
# every assignment (reading CPT rows by parent-state *name*, never by column
# position) and marginalise by summation. This is independent of the pgmpy
# adapter's positional column mapping — the most error-prone step per
# `_bn_engine` — so a transpose or off-by-one in that mapping makes the engine
# disagree with this reference. The existing binary OR network can't catch such
# a bug: it's symmetric in its two parents, so swapping columns is a no-op. The
# network below is deliberately asymmetric, with a 3-state node and parents of
# different cardinality.


def _joint_prob(assignment: dict, state_spaces: dict, cpts: dict) -> float:
    """P(assignment) = ∏ P(node=value | parents), looked up by parent name."""
    p = 1.0
    for nid, cpt in cpts.items():
        si = state_spaces[nid].index(assignment[nid])
        if cpt.parents:
            row = next(
                r for r in cpt.rows
                if all(r.parent_states.get(par) == assignment[par] for par in cpt.parents)
            )
        else:
            row = cpt.rows[0]
        p *= row.p[si]
    return p


def _brute_force_marginals(state_spaces, cpts, *, query, evidence=None):
    """Reference marginals via full-joint enumeration (no pgmpy)."""
    import itertools

    evidence = evidence or {}
    nodes = list(cpts.keys())
    totals = {q: dict.fromkeys(state_spaces[q], 0.0) for q in query}
    norm = 0.0
    for combo in itertools.product(*[state_spaces[n] for n in nodes]):
        assignment = dict(zip(nodes, combo, strict=True))
        if any(assignment[k] != v for k, v in evidence.items()):
            continue
        jp = _joint_prob(assignment, state_spaces, cpts)
        norm += jp
        for q in query:
            totals[q][assignment[q]] += jp
    return {q: {s: totals[q][s] / norm for s in totals[q]} for q in query}


def _weather_net():
    """Asymmetric net: 3-state root, a 3-state child, and a 2-state child whose
    parents have *different* cardinalities (2 and 3) with a non-symmetric table.
    """
    ss = {
        "season": ["dry", "mild", "wet"],
        "sprinkler": ["on", "off"],
        "pollen": ["low", "med", "high"],
        "grass": ["wet", "dry"],
    }
    cpts = {
        "season": CPTEntry(target_id="season", parents=[], states=ss["season"],
                           rows=[CPTRow(p=[0.5, 0.3, 0.2])]),
        "sprinkler": CPTEntry(target_id="sprinkler", parents=["season"], states=ss["sprinkler"], rows=[
            CPTRow(parent_states={"season": "dry"}, p=[0.7, 0.3]),
            CPTRow(parent_states={"season": "mild"}, p=[0.4, 0.6]),
            CPTRow(parent_states={"season": "wet"}, p=[0.1, 0.9]),
        ]),
        "pollen": CPTEntry(target_id="pollen", parents=["season"], states=ss["pollen"], rows=[
            CPTRow(parent_states={"season": "dry"}, p=[0.2, 0.3, 0.5]),
            CPTRow(parent_states={"season": "mild"}, p=[0.3, 0.4, 0.3]),
            CPTRow(parent_states={"season": "wet"}, p=[0.6, 0.3, 0.1]),
        ]),
        # parents listed [sprinkler, season]: sprinkler (card 2) varies slowest.
        "grass": CPTEntry(target_id="grass", parents=["sprinkler", "season"], states=ss["grass"], rows=[
            CPTRow(parent_states={"sprinkler": "on", "season": "dry"}, p=[0.9, 0.1]),
            CPTRow(parent_states={"sprinkler": "on", "season": "mild"}, p=[0.85, 0.15]),
            CPTRow(parent_states={"sprinkler": "on", "season": "wet"}, p=[0.95, 0.05]),
            CPTRow(parent_states={"sprinkler": "off", "season": "dry"}, p=[0.1, 0.9]),
            CPTRow(parent_states={"sprinkler": "off", "season": "mild"}, p=[0.3, 0.7]),
            CPTRow(parent_states={"sprinkler": "off", "season": "wet"}, p=[0.8, 0.2]),
        ]),
    }
    return ss, cpts


class TestAgainstBruteForce:
    @pytest.mark.parametrize("evidence", [
        None,                                       # priors
        {"grass": "wet"},                           # diagnostic, single evidence
        {"season": "wet", "sprinkler": "off"},      # predictive, multi evidence
        {"pollen": "high", "grass": "dry"},         # mixed
    ])
    def test_engine_matches_reference(self, evidence):
        ss, cpts = _weather_net()
        ev = evidence or {}
        targets = [n for n in cpts if n not in ev]
        got = bn_infer(ss, cpts, query=targets, evidence=ev or None).marginals
        want = _brute_force_marginals(ss, cpts, query=targets, evidence=ev or None)
        for n in targets:
            for s in ss[n]:
                assert got[n][s] == pytest.approx(want[n][s], abs=1e-9), f"{n}={s}"

    def test_marginals_normalise(self):
        ss, cpts = _weather_net()
        res = bn_infer(ss, cpts, evidence={"grass": "wet"})
        for node, dist in res.marginals.items():
            assert sum(dist.values()) == pytest.approx(1.0, abs=1e-9), node


# ── Conditional independence (d-separation) ────────────────────────────────


def _chain():
    """A -> B -> C (all binary). C is d-separated from A given B, so observing
    C on top of B must not change beliefs about A."""
    ss = {"A": ["a0", "a1"], "B": ["b0", "b1"], "C": ["c0", "c1"]}
    cpts = {
        "A": CPTEntry(target_id="A", parents=[], states=ss["A"], rows=[CPTRow(p=[0.3, 0.7])]),
        "B": CPTEntry(target_id="B", parents=["A"], states=ss["B"], rows=[
            CPTRow(parent_states={"A": "a0"}, p=[0.8, 0.2]),
            CPTRow(parent_states={"A": "a1"}, p=[0.4, 0.6]),
        ]),
        "C": CPTEntry(target_id="C", parents=["B"], states=ss["C"], rows=[
            CPTRow(parent_states={"B": "b0"}, p=[0.9, 0.1]),
            CPTRow(parent_states={"B": "b1"}, p=[0.2, 0.8]),
        ]),
    }
    return ss, cpts


class TestConditionalIndependence:
    def test_chain_blocks_on_middle_node(self):
        ss, cpts = _chain()
        for b in ss["B"]:
            base = bn_infer(ss, cpts, query=["A"], evidence={"B": b}).marginals["A"]
            for c in ss["C"]:
                also = bn_infer(ss, cpts, query=["A"], evidence={"B": b, "C": c}).marginals["A"]
                for s in ss["A"]:
                    assert also[s] == pytest.approx(base[s], abs=1e-9), f"A={s}|B={b},C={c}"
