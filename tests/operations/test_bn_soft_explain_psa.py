"""Soft evidence, the most likely explanation, and Monte Carlo over the probability tables.

Checked against brute-force enumeration of the joint distribution and Jeffrey's
rule, on the classic rain / sprinkler / wet-grass network.
"""

from __future__ import annotations

import itertools

import pytest

from latris.operations import bn_montecarlo
from latris.operations.bn_explain import explain
from latris.operations.bn_inference import bn_infer
from latris.schema.attributes import ParameterUncertainty
from latris.schema.bn import CPTEntry, CPTRow, NoisyOrEntry, NoisyOrLink

pytest.importorskip("pgmpy")

S = {"Rain": ["yes", "no"], "Spr": ["yes", "no"], "Wet": ["yes", "no"]}
WET = {("yes", "yes"): [0.99, 0.01], ("yes", "no"): [0.9, 0.1], ("no", "yes"): [0.8, 0.2], ("no", "no"): [0.05, 0.95]}


def cpts() -> dict[str, CPTEntry]:
    return {
        "Rain": CPTEntry(target_id="Rain", states=S["Rain"], rows=[CPTRow(p=[0.2, 0.8])]),
        "Spr": CPTEntry(target_id="Spr", states=S["Spr"], rows=[CPTRow(p=[0.4, 0.6])]),
        "Wet": CPTEntry(
            target_id="Wet", parents=["Rain", "Spr"], states=S["Wet"],
            rows=[CPTRow(parent_states={"Rain": r, "Spr": s}, p=p) for (r, s), p in WET.items()],
        ),
    }


def joint(r: str, s: str, w: str) -> float:
    pr = 0.2 if r == "yes" else 0.8
    ps = 0.4 if s == "yes" else 0.6
    pw = WET[(r, s)][0 if w == "yes" else 1]
    return pr * ps * pw


# ── soft evidence ────────────────────────────────────────────────────


def test_certainty_follows_jeffreys_rule():
    r = bn_infer(S, cpts(), soft={"Wet": {"yes": 0.8}})
    assert r.marginals["Wet"]["yes"] == pytest.approx(0.8, abs=1e-9)
    hard_yes = bn_infer(S, cpts(), evidence={"Wet": "yes"}).marginals["Rain"]["yes"]
    hard_no = bn_infer(S, cpts(), evidence={"Wet": "no"}).marginals["Rain"]["yes"]
    assert r.marginals["Rain"]["yes"] == pytest.approx(0.8 * hard_yes + 0.2 * hard_no, abs=1e-9)
    assert r.soft == {"Wet": pytest.approx({"yes": 0.8, "no": 0.2})}


def test_certainty_of_one_equals_hard_evidence():
    soft = bn_infer(S, cpts(), soft={"Wet": {"yes": 1.0}}).marginals["Rain"]["yes"]
    hard = bn_infer(S, cpts(), evidence={"Wet": "yes"}).marginals["Rain"]["yes"]
    assert soft == pytest.approx(hard, abs=1e-9)


def test_two_soft_nodes_are_both_met():
    r = bn_infer(S, cpts(), soft={"Wet": {"yes": 0.7}, "Spr": {"yes": 0.5}})
    assert r.marginals["Wet"]["yes"] == pytest.approx(0.7, abs=1e-8)
    assert r.marginals["Spr"]["yes"] == pytest.approx(0.5, abs=1e-8)


def test_likelihood_is_virtual_evidence():
    r = bn_infer(S, cpts(), likelihood={"Wet": {"yes": 4, "no": 1}})
    num = sum(joint("yes", s, w) * (4 if w == "yes" else 1) for s in ("yes", "no") for w in ("yes", "no"))
    den = sum(joint(r_, s, w) * (4 if w == "yes" else 1) for r_ in ("yes", "no") for s in ("yes", "no")
              for w in ("yes", "no"))
    assert r.marginals["Rain"]["yes"] == pytest.approx(num / den, abs=1e-9)


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"soft": {"Wet": {"yes": 1.2}}}, "total 1"),
        ({"soft": {"Wet": {"damp": 0.5}}}, "unknown state"),
        ({"soft": {"Wet": {"yes": 0.5}}, "evidence": {"Wet": "no"}}, "both hard"),
        ({"soft": {"Spr": {"yes": 0.5}}, "evidence": {"Rain": "no", "Wet": "no"}}, None),
    ],
)
def test_bad_soft_evidence_is_refused(kwargs, match):
    if match is None:  # possible: not every soft target is refused
        bn_infer(S, cpts(), **kwargs)
        return
    with pytest.raises(ValueError, match=match):
        bn_infer(S, cpts(), **kwargs)


def test_impossible_soft_evidence_is_refused():
    table = cpts()
    table["Wet"] = table["Wet"].model_copy(update={"rows": [
        CPTRow(parent_states={"Rain": r, "Spr": s}, p=[0.0, 1.0] if (r, s) == ("no", "no") else p)
        for (r, s), p in WET.items()]})
    with pytest.raises(ValueError, match="impossible"):
        bn_infer(S, table, evidence={"Rain": "no", "Spr": "no"}, soft={"Wet": {"yes": 0.5}})


# ── most likely explanation ──────────────────────────────────────────


def brute(evidence: dict[str, str], over: list[str]) -> tuple[dict[str, str], float]:
    scores: dict[tuple, float] = {}
    for r, s, w in itertools.product(*S.values()):
        a = {"Rain": r, "Spr": s, "Wet": w}
        if any(a[k] != v for k, v in evidence.items()):
            continue
        key = tuple(a[v] for v in over)
        scores[key] = scores.get(key, 0.0) + joint(r, s, w)
    total = sum(scores.values())
    best = max(scores, key=scores.get)
    return dict(zip(over, best, strict=True)), scores[best] / total


@pytest.mark.parametrize("over", [None, ["Rain"], ["Spr"], ["Rain", "Spr"]])
def test_explanation_matches_enumeration(over):
    out = explain(S, cpts(), over=over, evidence={"Wet": "yes"})
    variables = over or ["Rain", "Spr"]
    assignment, prob = brute({"Wet": "yes"}, variables)
    assert out["assignment"] == assignment and "Wet" not in out["assignment"]
    assert out["probability"] == pytest.approx(prob, abs=1e-9)
    assert out["kind"] == ("MPE" if over is None else "MAP")


def test_margin_is_a_ratio_of_joint_probabilities():
    out = explain(S, cpts(), evidence={"Wet": "yes"})  # best: Rain=no, Spr=yes
    rain = next(r for r in out["rows"] if r["node"] == "Rain")
    assert rain["runner_up"] == "yes"
    expected = joint("no", "yes", "yes") / joint("yes", "yes", "yes")
    assert rain["times_likelier"] == pytest.approx(expected, rel=1e-9)


def test_jointly_likeliest_can_differ_from_the_marginal_favourite():
    # P(Rain) = P(Sprinkler) = 0.3, grass wet: the likeliest joint story is "rain, sprinkler off",
    # yet on its own the sprinkler is more likely on than off. The report must say so.
    table = cpts()
    table["Spr"] = table["Spr"].model_copy(update={"rows": [CPTRow(p=[0.3, 0.7])]})
    table["Rain"] = table["Rain"].model_copy(update={"rows": [CPTRow(p=[0.3, 0.7])]})
    out = explain(S, table, evidence={"Wet": "yes"})
    assert out["assignment"] == {"Rain": "yes", "Spr": "no"}
    marg = bn_infer(S, table, evidence={"Wet": "yes"}).marginals
    assert marg["Spr"]["yes"] > marg["Spr"]["no"]
    spr = next(r for r in out["rows"] if r["node"] == "Spr")
    assert spr["differs_from_marginal"] and spr["favourite"] == "yes"
    assert not next(r for r in out["rows"] if r["node"] == "Rain")["differs_from_marginal"]


def test_explanation_with_soft_evidence_matches_weighted_enumeration():
    out = explain(S, cpts(), soft={"Wet": {"yes": 0.9}}, over=["Rain", "Spr"])
    weights = bn_infer(S, cpts(), soft={"Wet": {"yes": 0.9}}).fitted_likelihood["Wet"]
    scores = {(r, s): sum(joint(r, s, w) * weights[w] for w in ("yes", "no"))
              for r, s in itertools.product(("yes", "no"), repeat=2)}
    best = max(scores, key=scores.get)
    assert (out["assignment"]["Rain"], out["assignment"]["Spr"]) == best
    assert out["probability"] == pytest.approx(scores[best] / sum(scores.values()), abs=1e-9)


# ── Monte Carlo over the tables ──────────────────────────────────────


def _spec(n: float, cell: str = "bn:cpt") -> ParameterUncertainty:
    return ParameterUncertainty(target_id="x", distribution="dirichlet", params={"n": n}, parameter_cell_id=cell)


def test_monte_carlo_is_reproducible_and_narrows_with_n():
    point = bn_infer(S, cpts(), evidence={"Wet": "yes"}).marginals["Rain"]["yes"]
    wide = bn_montecarlo.monte_carlo(S, cpts(), {}, {"Wet": {"bn:cpt": _spec(5)}}, "Rain",
                                     evidence={"Wet": "yes"}, runs=200, seed=3)
    again = bn_montecarlo.monte_carlo(S, cpts(), {}, {"Wet": {"bn:cpt": _spec(5)}}, "Rain",
                                      evidence={"Wet": "yes"}, runs=200, seed=3)
    assert {k: v for k, v in wide.items() if k != "seconds"} == {k: v for k, v in again.items() if k != "seconds"}
    narrow = bn_montecarlo.monte_carlo(S, cpts(), {}, {"Wet": {"bn:cpt": _spec(1e6)}}, "Rain",
                                       evidence={"Wet": "yes"}, runs=100, seed=3)
    w, n = wide["by_state"]["yes"], narrow["by_state"]["yes"]
    assert w["point"] == pytest.approx(point, abs=1e-6)
    assert n["p2.5"] == pytest.approx(point, abs=2e-3) and n["p97.5"] == pytest.approx(point, abs=2e-3)
    assert w["p97.5"] - w["p2.5"] > 10 * (n["p97.5"] - n["p2.5"])
    fixed = {t["label"]: t["fixed"] for t in wide["tables"]}
    assert fixed == {"Rain": True, "Spr": True, "Wet": False}


def test_zero_cells_stay_zero():
    import random

    from latris.operations._sampling import dirichlet

    rng = random.Random(1)
    assert all(dirichlet(rng, [0.0, 0.3, 0.7], 2)[0] == 0.0 for _ in range(50))


def test_row_override_and_noisy_or():
    specs = {"Wet": {"bn:cpt:Rain=no,Spr=no": _spec(3, "bn:cpt:Rain=no,Spr=no")}}
    out = bn_montecarlo.monte_carlo(S, cpts(), {}, specs, "Wet", runs=50, seed=1)
    assert out["by_state"]["yes"]["p2.5"] < out["by_state"]["yes"]["point"] < out["by_state"]["yes"]["p97.5"]

    from latris.operations._bn_canonical import expand_noisy_or

    ne = NoisyOrEntry(target_id="Wet", parents=["Rain", "Spr"], states=["yes", "no"], leak=0.05,
                      links=[NoisyOrLink(parent_id="Rain", active_state="yes", prob=0.9),
                             NoisyOrLink(parent_id="Spr", active_state="yes", prob=0.8)])
    table = {**cpts(), "Wet": expand_noisy_or(ne, S)}
    out = bn_montecarlo.monte_carlo(S, table, {"Wet": ne}, {"Wet": {"bn:cpt": _spec(10)}}, "Rain",
                                    evidence={"Wet": "yes"}, runs=60, seed=2)
    assert out["tables"][-1]["noisy_or"] is True
    assert out["by_state"]["yes"]["p97.5"] > out["by_state"]["yes"]["p2.5"]


def test_monte_carlo_needs_uncertainty_and_respects_the_time_guard():
    with pytest.raises(ValueError, match="no probability table has an uncertainty"):
        bn_montecarlo.monte_carlo(S, cpts(), {}, {}, "Rain", runs=10)
    with pytest.raises(ValueError, match="would take about"):
        bn_montecarlo.monte_carlo(S, cpts(), {}, {"Wet": {"bn:cpt": _spec(5)}}, "Rain", runs=2000,
                                  max_seconds=1e-6)
