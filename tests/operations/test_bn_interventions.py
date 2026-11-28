"""What-if settings (the do-operator) in the most likely explanation, sensitivity and Monte Carlo.

Hand-computed on two small networks: rain / sprinkler / wet grass, and A → T.
Setting a factor replaces its table by certainty in the set state and cuts the
links from its causes; observing it conditions on it. The two give different
answers upstream, which is the point of these tests.
"""

from __future__ import annotations

import pytest

from latris.operations import bn as bn_ops
from latris.operations import bn_sensitivity
from latris.operations.bn_explain import explain
from latris.operations.uncertainty import set_table_uncertainty

from .test_bn_sensitivity import project  # noqa: F401 - the A → T project fixture
from .test_bn_soft_explain_psa import S, cpts, joint

pytest.importorskip("pgmpy")


# ── most likely explanation ──────────────────────────────────────────


def test_setting_the_effect_leaves_its_causes_at_their_priors():
    # Observed wet grass: the likeliest causes are found by conditioning (brute force over Rain, Spr).
    observed = explain(S, cpts(), evidence={"Wet": "yes"})
    combos = {(r, s): joint(r, s, "yes") for r in ("yes", "no") for s in ("yes", "no")}
    best = max(combos, key=combos.get)
    assert (observed["assignment"]["Rain"], observed["assignment"]["Spr"]) == best == ("no", "yes")
    assert observed["probability"] == pytest.approx(combos[best] / sum(combos.values()))

    # SET wet grass (hose it): that says nothing about rain or the sprinkler — each keeps its prior,
    # so the likeliest is no rain (0.8) and no sprinkler (0.6), P = 0.48; Wet itself isn't explained.
    done = explain(S, cpts(), interventions={"Wet": "yes"})
    assert done["over"] == ["Rain", "Spr"]
    assert done["assignment"] == {"Rain": "no", "Spr": "no"}
    assert done["probability"] == pytest.approx(0.8 * 0.6)
    assert done["interventions"] == {"Wet": "yes"}


def test_setting_a_cause_is_kept_out_and_moves_its_effects():
    # Sprinkler set on: Wet ~ P(Wet | Rain, Spr=yes); likeliest (Rain=no 0.8)·(Wet=yes 0.8) = 0.64.
    done = explain(S, cpts(), interventions={"Spr": "yes"})
    assert "Spr" not in done["over"]
    assert done["assignment"] == {"Rain": "no", "Wet": "yes"}
    assert done["probability"] == pytest.approx(0.8 * 0.8)


def test_a_factor_cannot_be_set_and_observed():
    with pytest.raises(ValueError, match="set or observed, not both"):
        explain(S, cpts(), evidence={"Wet": "yes"}, interventions={"Wet": "no"})


# ── sensitivity ──────────────────────────────────────────────────────


def test_sensitivity_with_a_cause_set(project):  # noqa: F811
    root, a_id, t_id, n_id = project
    res = bn_sensitivity.sensitivity("T", "t0", interventions={"A": "a1"}, root=root)
    assert res.interventions == {a_id: "a1"}
    assert res.baseline == pytest.approx(0.1)  # P(T=t0 | do(A=a1)) = the a1 row
    nodes = {(f.node_id, tuple(f.parent_states.values())) for f in res.findings}
    assert (a_id, ()) not in nodes  # A's own table no longer counts
    by_row = {tuple(f.parent_states.values()): f.influence for f in res.findings if f.node_id == t_id}
    assert by_row[("a1",)] == pytest.approx(1.0)  # swept 0..1 moves the answer all the way
    assert by_row[("a0",)] == pytest.approx(0.0)  # the row that can't happen any more


def test_sensitivity_refuses_to_ask_about_a_set_factor(project):  # noqa: F811
    root, *_ = project
    with pytest.raises(ValueError, match="is set"):
        bn_sensitivity.sensitivity("A", "a0", interventions={"A": "a1"}, root=root)


def test_sensitivity_record_keeps_what_was_set(project):  # noqa: F811
    root, a_id, *_ = project
    res = bn_sensitivity.sensitivity("T", "t0", interventions={"A": "a0"}, root=root)
    bn_sensitivity.record_sensitivity(res, root=root)
    plain = bn_sensitivity.sensitivity("T", "t0", root=root)
    bn_sensitivity.record_sensitivity(plain, root=root)
    from latris.operations.analysis_results import list_results

    keys = {run.analysis_key for run, _hidden, _stale in list_results(root=root) if run.result_kind == "bn-sensitivity"}
    assert len(keys) == 2  # a what-if run doesn't replace the plain one


# ── Monte Carlo ──────────────────────────────────────────────────────


def test_monte_carlo_with_a_cause_set_holds_its_table(project):  # noqa: F811
    root, a_id, t_id, _ = project
    # Both tables uncertain. Asked plainly, A's prior drives the spread; with A set to a0, A's table is
    # held (it no longer counts), the answer centres on the a0 row's 0.9 and only T's table drives it.
    set_table_uncertainty("A", 10, root=root)
    set_table_uncertainty("T", 50, root=root)
    plain = bn_ops.run_monte_carlo("T", state="t0", runs=200, root=root)
    assert plain["by_state"]["t0"]["point"] == pytest.approx(0.5)
    assert a_id in {d["node"] for d in plain["drivers"]}
    done = bn_ops.run_monte_carlo("T", state="t0", interventions={"A": "a0"}, runs=200, root=root)
    assert done["interventions"] == {a_id: "a0"}
    assert done["by_state"]["t0"]["point"] == pytest.approx(0.9)
    assert a_id not in {d["node"] for d in done["drivers"]}
    from latris.operations.bn_montecarlo import describe

    assert "A set to a0" in describe(done)
    with pytest.raises(ValueError, match="is set"):
        bn_ops.run_monte_carlo("A", interventions={"A": "a0"}, runs=10, root=root)


def test_monte_carlo_says_when_only_set_tables_are_uncertain(project):  # noqa: F811
    root, *_ = project
    set_table_uncertainty("A", 10, root=root)
    with pytest.raises(ValueError, match="belong to factors that are set"):
        bn_ops.run_monte_carlo("T", state="t0", interventions={"A": "a0"}, runs=20, root=root)


# ── routes ───────────────────────────────────────────────────────────


def test_routes_take_interventions(project):  # noqa: F811
    from fastapi.testclient import TestClient

    from latris.server.app import create_app

    root, a_id, t_id, _ = project
    client = TestClient(create_app(project_root=root))
    r = client.post("/api/bn/explain", json={"interventions": {"A": "a1"}, "record": True})
    assert r.status_code == 200, r.text
    assert r.json()["result"]["assignment"][t_id] == "t1" and a_id not in r.json()["result"]["assignment"]
    r = client.post("/api/bn/sensitivity", json={"target": "T", "state": "t0", "interventions": {"A": "a1"}})
    assert r.status_code == 200, r.text
    assert r.json()["baseline"] == pytest.approx(0.1)
    set_table_uncertainty("T", 10, root=root)
    r = client.post("/api/bn/monte-carlo", json={"target": "T", "state": "t0", "interventions": {"A": "a0"}, "runs": 50})
    assert r.status_code == 200, r.text
    assert r.json()["result"]["by_state"]["t0"]["point"] == pytest.approx(0.9)


# ── build specs (latris#66) ──────────────────────────────────────────


def test_spec_analyses_take_interventions_and_give_them_back(project):  # noqa: F811
    """The explanation and Monte Carlo analyses take ``interventions`` from a spec (as the query does), and a
    recorded run's definition carries them back out, so a spec or a link reruns the same what-if."""
    from latris.operations.analysis_replay import definitions, run_analysis
    from latris.schema.build_spec import make_analysis

    root, a_id, t_id, _ = project
    set_table_uncertainty("T", 10, root=root)
    explained = make_analysis(kind="bn_explain", interventions={"A": "a1"})
    sampled = make_analysis(kind="bn_monte_carlo", target="T", state="t0", interventions={"A": "a0"}, runs=50)
    for a in (explained, sampled):
        type(a).model_validate(a.model_dump(mode="json"))  # round-trips
        run_analysis(a, root=root)

    back = {d.kind: d for d in definitions(root=root)}
    assert back["bn_explain"].interventions == {"A": "a1"}
    assert back["bn_monte_carlo"].interventions == {"A": "a0"}
    mc = bn_ops.run_monte_carlo("T", state="t0", interventions={"A": "a0"}, runs=50, root=root)
    assert mc["by_state"]["t0"]["point"] == pytest.approx(0.9)
