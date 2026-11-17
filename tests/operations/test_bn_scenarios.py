"""BN scenarios: named what-ifs (observations, settings, table overrides) that never mutate the model,
and comparing them on the same draws of the tables."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import bn as bn_ops
from latris.operations import bn_scenarios, uncertainty
from latris.repo.layout import ProjectPaths
from latris.schema.bn import BNScenario, BNScenarioSet, BNTableOverride
from tests.conftest import build_with_template_identity, clone_project

pytest.importorskip("pgmpy")

# Heavy rain and the levee drive a flood; a flood closes the road.
FLOOD = {
    "Heavy Rain": ([], [0.3, 0.7]),
    "Levee Holds": ([], [0.9, 0.1]),
    "Flood": (["Heavy Rain", "Levee Holds"], [0.2, 0.8, 0.95, 0.05, 0.02, 0.98, 0.3, 0.7]),
    "Road Closed": (["Flood"], [0.9, 0.1, 0.05, 0.95]),
}


def _p_flood(rain: float, hold: float, table: dict[tuple[str, str], float] | None = None) -> float:
    t = {("yes", "yes"): 0.2, ("yes", "no"): 0.95, ("no", "yes"): 0.02, ("no", "no"): 0.3, **(table or {})}
    return sum((rain if r == "yes" else 1 - rain) * (hold if h == "yes" else 1 - hold) * t[(r, h)]
               for r in ("yes", "no") for h in ("yes", "no"))


def _build(root: Path) -> Path:
    from latris.operations import edges as edge_ops
    from latris.operations import nodes as node_ops
    from latris.operations.init import init_project
    from latris.operations.project import update_selected_models

    init_project(root, statement="How likely is a flood?")
    update_selected_models(["bn"], root=root)
    ids = {n: node_ops.add_node(n, kind="variable", root=root)[0].id for n in FLOOD}
    for node, (parents, _) in FLOOD.items():
        for parent in parents:
            edge_ops.add_edge(ids[parent], ids[node], kind="causal", root=root)
    for node in FLOOD:
        bn_ops.set_state_space(node, ["yes", "no"], root=root)
    for node, (parents, probs) in FLOOD.items():
        bn_ops.set_cpt(node, parents, probs, root=root)
    return root


@pytest.fixture(scope="module")
def _template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_with_template_identity(lambda: _build(tmp_path_factory.mktemp("tpl_bn_scen") / "proj"))


@pytest.fixture
def flood(_template: Path, tmp_path: Path, git_identity) -> Path:
    return clone_project(_template, tmp_path / "proj")


def _scenarios(root: Path) -> None:
    bn_scenarios.set_scenario("Stronger levee", tables=["Levee Holds=0.99,0.01"], reason="Upgrade", root=root)
    bn_scenarios.set_scenario("Stronger levee, storm season", extends="Stronger levee",
                              tables=["Heavy Rain=0.6,0.4"], root=root)
    bn_scenarios.set_scenario("Storm", observe=["Heavy Rain=yes"], root=root)


def test_schema_round_trips_and_checks():
    s = BNScenario(name="A", evidence={"n1": "yes"}, tables=[BNTableOverride(target_id="n2", p=[0.25, 0.75])])
    assert BNScenarioSet.model_validate_json(BNScenarioSet(scenarios=[s]).model_dump_json()).scenarios == [s]
    with pytest.raises(ValueError, match="sum to 1"):
        BNTableOverride(target_id="n", p=[0.5, 0.6])
    with pytest.raises(ValueError, match="both observed and set"):
        BNScenario(name="B", evidence={"n": "yes"}, interventions={"n": "no"})
    with pytest.raises(ValueError, match="baseline"):
        BNScenario(name="Baseline", evidence={"n": "yes"})


def test_a_table_override_changes_the_answer_without_touching_the_model(flood):
    _scenarios(flood)
    before = bn_ops.get_cpts(root=flood).model_dump()
    r = bn_ops.infer(query=["Flood"], scenario="Stronger levee", root=flood)
    assert r.marginals[next(iter(r.marginals))]["yes"] == pytest.approx(_p_flood(0.3, 0.99))
    assert r.scenario == "Stronger levee" and r.scenario_changes == ["P(Levee Holds) → 0.99, 0.01"]
    assert bn_ops.get_cpts(root=flood).model_dump() == before  # the model's own tables are untouched
    plain = bn_ops.infer(query=["Flood"], root=flood)
    assert plain.marginals[next(iter(plain.marginals))]["yes"] == pytest.approx(_p_flood(0.3, 0.9))


def test_rows_are_selected_by_parent_states(flood):
    bn_scenarios.set_scenario("Flood-proofed", tables=["Flood[Levee Holds=no]=0.1,0.9"], root=flood)
    r = bn_ops.infer(query=["Flood"], scenario="Flood-proofed", root=flood)
    want = _p_flood(0.3, 0.9, {("yes", "no"): 0.1, ("no", "no"): 0.1})
    assert next(iter(r.marginals.values()))["yes"] == pytest.approx(want)
    with pytest.raises(ValueError, match="not a parent of Flood"):
        bn_scenarios.set_scenario("X", tables=["Flood[Road Closed=yes]=0.1,0.9"], root=flood)
    with pytest.raises(ValueError, match="give 2 probabilities"):
        bn_scenarios.set_scenario("X", tables=["Flood=1"], root=flood)
    with pytest.raises(ValueError, match="is not a state of Heavy Rain"):
        bn_scenarios.set_scenario("X", observe=["Heavy Rain=maybe"], root=flood)


def test_extends_merges_and_evidence_in_the_call_wins(flood):
    _scenarios(flood)
    merged = bn_scenarios.get("Stronger levee, storm season", ProjectPaths(flood))
    assert len(merged.tables) == 2 and merged.extends == "Stronger levee"
    r = bn_ops.infer(query=["Flood"], scenario="Stronger levee, storm season", root=flood)
    assert next(iter(r.marginals.values()))["yes"] == pytest.approx(_p_flood(0.6, 0.99))
    # the call's own say about Heavy Rain replaces the scenario's
    r = bn_ops.infer(query=["Flood"], evidence={"Heavy Rain": "no"}, scenario="Storm", root=flood)
    assert list(r.evidence.values()) == ["no"]
    with pytest.raises(ValueError, match="in a loop"):
        bn_scenarios.set_scenario("Stronger levee", extends="Stronger levee, storm season",
                                  tables=["Levee Holds=0.99,0.01"], root=flood)
    with pytest.raises(ValueError, match="extends 'Stronger levee'"):
        bn_scenarios.remove_scenario("Stronger levee", root=flood)


def test_point_comparison_names_the_reference(flood):
    _scenarios(flood)
    p = bn_ops.run_compare("Flood", ["Stronger levee", "Stronger levee, storm season"], state="yes", root=flood)
    by = {r["name"]: r for r in p["options"]}
    assert p["runs"] == 0  # no table uncertainty: point probabilities only
    assert by["baseline"]["point"] == pytest.approx(_p_flood(0.3, 0.9), abs=1e-6)
    assert by["Stronger levee"]["reference"] == "baseline"
    season = by["Stronger levee, storm season"]
    assert season["reference"] == "Stronger levee"
    assert season["difference"]["point"] == pytest.approx(_p_flood(0.6, 0.99) - _p_flood(0.3, 0.99), abs=1e-6)
    assert "vs_baseline" in season


def test_paired_draws_and_held_overrides(flood):
    _scenarios(flood)
    uncertainty.set_table_uncertainty("Levee Holds", 20, root=flood)
    uncertainty.set_table_uncertainty("Flood", 30, root=flood)
    p = bn_ops.run_compare("Flood", ["Stronger levee"], state="yes", runs=200, root=flood)
    by = {r["name"]: r for r in p["options"]}
    assert p["runs"] == 200
    d = by["Stronger levee"]["difference"]
    assert d["share_lower"] == 1.0  # a stronger levee lowers the flood risk in every draw
    assert d["p97.5"] < 0
    assert p == bn_ops.run_compare("Flood", ["Stronger levee"], state="yes", runs=200, root=flood) | {
        "seconds": p["seconds"]}
    mc = bn_ops.run_monte_carlo("Flood", state="yes", runs=100, scenario="Stronger levee", root=flood)
    levee = next(t for t in mc["tables"] if t["label"] == "Levee Holds")
    assert levee["fixed"] is False and mc["scenario"] == "Stronger levee"


def test_comparison_records_reports_and_replays(flood):
    from latris.exporters import markdown
    from latris.operations.build import build_from_spec
    from latris.operations.init import init_project
    from latris.operations.interpret import extract_claims
    from latris.operations.share_link import export_spec

    _scenarios(flood)
    p = bn_ops.run_compare("Flood", ["Stronger levee", "Stronger levee, storm season"], state="yes", root=flood)
    bn_ops.record_compare(p, root=flood)
    md = markdown.render(ProjectPaths(flood), model_type="bn", ai=False)
    assert "Options compared" in md and "Compared with" in md
    claims = extract_claims("answer_to_question", "bn", root=flood)
    assert any(c.strip("- ").startswith("Stronger levee, storm season — P(Flood = yes)")
               and "vs Stronger levee:" in c for c in claims)

    _, spec = export_spec(model_type="bn", root=flood)
    by = {s.name: s for s in spec.bn.scenarios}
    assert by["Stronger levee, storm season"].extends == "Stronger levee"
    assert by["Stronger levee"].tables == ["Levee Holds=0.99,0.01"]
    (cmp,) = [a for a in spec.analyses if a.kind == "bn_compare"]
    assert cmp.scenarios == ["Stronger levee", "Stronger levee, storm season"]
    spec.bn.scenarios.sort(key=lambda s: s.name != "Stronger levee, storm season")  # child first still builds
    other = flood.parent / "rebuilt"
    init_project(other, statement="Q?")
    built = build_from_spec(spec, root=other)
    assert built.analyses
    assert {s.name for s in bn_scenarios.list_scenarios(root=other)} == set(by)


def test_a_changed_parent_ages_a_childs_result(flood):
    from latris.operations.analysis_results import report_results

    _scenarios(flood)
    p = bn_ops.run_compare("Flood", ["Stronger levee, storm season"], state="yes", root=flood)
    bn_ops.record_compare(p, root=flood)

    def stale() -> bool:
        return next(r for r in report_results(model_types=["bn"], root=flood)
                    if r.run.result_kind == "bn-options").stale

    assert not stale()
    bn_scenarios.set_scenario("Stronger levee", tables=["Levee Holds=0.95,0.05"], root=flood)
    assert stale()


def test_cli_and_routes(flood, monkeypatch):
    from fastapi.testclient import TestClient
    from typer.testing import CliRunner

    from latris.cli.app import app
    from latris.server.app import create_app

    monkeypatch.chdir(flood)
    runner = CliRunner()
    r = runner.invoke(app, ["bn", "set-scenario", "Stronger levee", "-t", "Levee Holds=0.99,0.01",
                            "--reason", "Upgrade"])
    assert r.exit_code == 0, r.output
    r = runner.invoke(app, ["bn", "set-scenario", "Levee later", "--extends", "Stronger levee",
                            "-t", "Levee Holds=0.95,0.05"])
    assert r.exit_code == 0 and "extends Stronger levee" in r.output, r.output
    r = runner.invoke(app, ["bn", "scenarios"])
    assert "Stronger levee, plus" in r.output, r.output
    r = runner.invoke(app, ["bn", "query", "-q", "Flood", "--scenario", "Stronger levee", "--no-record"])
    assert r.exit_code == 0 and "scenario Stronger levee" in r.output, r.output
    r = runner.invoke(app, ["bn", "compare", "Flood", "--state", "yes", "-S", "Stronger levee", "-S", "Levee later"])
    assert r.exit_code == 0, r.output
    assert "Levee later — P(Flood = yes)" in r.output and "vs Stronger levee" in r.output
    assert "later" in r.output  # no delay warning: it extends the undelayed option
    assert "⚠" not in r.output

    client = TestClient(create_app(project_root=flood))
    assert client.get("/api/bn/scenarios").json()["count"] == 2
    r = client.post("/api/bn/scenario", json={"name": "Storm", "observe": ["Heavy Rain=yes"]})
    assert r.status_code == 200 and r.json()["result"]["evidence"]
    r = client.post("/api/bn/query", json={"query": ["Flood"], "scenario": "Storm"})
    assert r.status_code == 200 and r.json()["scenario"] == "Storm"
    r = client.post("/api/bn/compare", json={"target": "Flood", "state": "yes", "scenarios": ["Storm"],
                                             "record": False})
    assert r.status_code == 200 and r.json()["result"]["options"][1]["reference"] == "baseline"
    assert client.delete("/api/bn/scenario/Stronger levee").status_code == 400  # Levee later extends it
