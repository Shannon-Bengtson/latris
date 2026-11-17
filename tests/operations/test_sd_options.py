"""Comparing options under uncertainty: every option on the same draws, differences paired."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import sd as sd_ops
from latris.operations import uncertainty
from latris.repo.layout import ProjectPaths
from tests.conftest import build_with_template_identity, build_sd_bathtub, clone_project


def _build(root: Path) -> Path:
    from latris.operations import sd_scenarios

    build_sd_bathtub(root)
    uncertainty.set_uncertainty("Drain Rate", "triangular", {"min": 0.05, "mode": 0.08, "max": 0.2}, root=root)
    uncertainty.set_uncertainty("Water", "uniform", {"min": 50, "max": 150}, root=root)
    sd_scenarios.set_scenario("More inflow", ["Inflow Rate=8"], root=root)
    sd_scenarios.set_scenario("Faster drain", ["Drain Rate=0.3"], root=root)
    return root


@pytest.fixture(scope="module")
def _template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_with_template_identity(lambda: _build(tmp_path_factory.mktemp("tpl_options") / "proj"))


@pytest.fixture
def options_root(_template: Path, tmp_path: Path, git_identity) -> Path:
    return clone_project(_template, tmp_path / "proj")


def _run(root: Path, **kw):
    return sd_ops.run_compare(["More inflow", "Faster drain"], "Water", runs=60,
                              settings={"final_time": 20}, root=root, **kw)


def test_each_option_is_compared_with_the_baseline_draw_by_draw(options_root):
    p = _run(options_root)
    by = {r["name"]: r for r in p["options"]}
    assert set(by) == {"baseline", "More inflow", "Faster drain"}
    assert by["More inflow"]["difference"]["share_higher"] == 1.0  # more inflow fills the tub in every draw
    assert by["Faster drain"]["difference"]["share_lower"] == 1.0
    assert "difference" not in by["baseline"]
    # a scenario that fixes Drain Rate isn't sampled on it: its spread comes from the initial water alone
    assert by["Faster drain"]["p97.5"] - by["Faster drain"]["p2.5"] < by["baseline"]["p97.5"] - by["baseline"]["p2.5"]


def test_paired_draws_are_reproducible_by_seed(options_root):
    assert _run(options_root)["options"] == _run(options_root)["options"]
    assert _run(options_root)["options"] != _run(options_root, seed=7)["options"]


def test_total_metric_integrates_over_the_run(options_root):
    p = _run(options_root, metric="total")
    assert p["units"] == "liter × years"
    base = next(r for r in p["options"] if r["name"] == "baseline")
    assert base["central"] > 0


def test_recorded_comparison_reaches_report_and_claims(options_root):
    from latris.exporters.results import render_results
    from latris.operations.interpret import extract_claims

    sd_ops.record_compare(_run(options_root), root=options_root)
    lines = render_results(ProjectPaths(options_root))
    assert "### Options compared under uncertainty: Water, final value" in lines
    claims = extract_claims("answer_to_question", "sd", root=options_root)
    assert any(c.startswith("Options compared on Water") for c in claims)
    assert any("More inflow — Water, final value:" in c and "higher in the median draw" in c
               and "vs the baseline (no scenario changes)" in c for c in claims)


def test_comparison_replays_from_its_definition(options_root):
    from latris.operations.analysis_replay import definitions, run_analysis

    sd_ops.record_compare(_run(options_root), root=options_root)
    [spec] = [d for d in definitions(root=options_root) if d.kind == "compare"]
    assert spec.scenarios == ["More inflow", "Faster drain"] and spec.variable == "Water"
    run_analysis(spec, root=options_root)


def test_values_applied_to_all_hold_in_every_option(options_root):
    plain = {r["name"]: r for r in _run(options_root)["options"]}
    world = _run(options_root, apply_to_all=["Inflow Rate=20"])
    assert world["world"] == ["Inflow Rate=20 liter/year"]
    hot = {r["name"]: r for r in world["options"]}
    assert hot["baseline"]["central"] > plain["baseline"]["central"]
    assert hot["Faster drain"]["central"] > plain["Faster drain"]["central"]


def test_a_world_is_named_in_the_heading_and_kept_apart(options_root):
    from latris.exporters.results import render_results

    payload, runs = sd_ops.simulate_scenarios(["Faster drain"], final_time=10, root=options_root)
    sd_ops.record_comparison(payload, runs, root=options_root)
    payload, runs = sd_ops.simulate_scenarios(["Faster drain"], final_time=10, apply_to_all=["Inflow Rate=20"],
                                              root=options_root)
    sd_ops.record_comparison(payload, runs, root=options_root)
    headings = [h for h in render_results(ProjectPaths(options_root)) if h.startswith("### Simulation")]
    assert len(headings) == 2
    assert any("in every run: Inflow Rate=20" in h for h in headings)


# ── references: what each option is measured against ────────────────


def _delayed(root: Path) -> None:
    from latris.operations import sd_scenarios

    sd_scenarios.set_scenario("More inflow later", ["Water=40"], extends="More inflow", root=root)


def test_an_option_extending_a_compared_option_is_measured_against_it(options_root):
    _delayed(options_root)
    p = sd_ops.run_compare(["More inflow", "More inflow later"], "Water", runs=40,
                           settings={"final_time": 20}, root=options_root)
    by = {r["name"]: r for r in p["options"]}
    later = by["More inflow later"]
    assert later["extends"] == "More inflow"
    assert later["reference"] == "More inflow"
    assert later["difference"]["share_lower"] == 1.0  # less water to start than the undelayed option
    assert "vs_baseline" in later  # the do-nothing comparison stays available, labelled
    assert by["More inflow"]["reference"] == "baseline"
    assert p["warnings"] == []


def test_an_extending_scenario_inherits_its_parents_values(options_root):
    from latris.operations import sd_scenarios
    from latris.repo.project import require_project

    _delayed(options_root)
    merged = sd_scenarios.get("More inflow later", require_project(options_root))
    assert {o.attribute for o in merged.overrides} == {"constant", "initial_value"}
    stored = next(s for s in sd_scenarios.list_scenarios(root=options_root) if s.name == "More inflow later")
    assert len(stored.overrides) == 1  # only its own change is stored


def test_extending_without_the_parent_warns(options_root):
    _delayed(options_root)
    p = sd_ops.run_compare(["More inflow later"], "Water", runs=20, settings={"final_time": 20}, root=options_root)
    (row,) = [r for r in p["options"] if r["name"] == "More inflow later"]
    assert row["reference"] == "baseline"
    assert any("isn't in this comparison" in w for w in p["warnings"])


def test_a_delay_sounding_option_against_the_baseline_warns(options_root):
    from latris.operations import sd_scenarios

    sd_scenarios.set_scenario("Inflow delayed", ["Inflow Rate=8"], root=options_root)
    p = sd_ops.run_compare(["Inflow delayed"], "Water", runs=20, settings={"final_time": 20}, root=options_root)
    assert any("cost of waiting" in w for w in p["warnings"])


def test_an_explicit_reference_applies_to_every_option(options_root):
    p = _run(options_root, reference="more INFLOW")
    by = {r["name"]: r for r in p["options"]}
    assert p["reference"] == "More inflow"
    assert by["baseline"]["reference"] == "More inflow"
    assert by["Faster drain"]["reference"] == "More inflow"
    assert "difference" not in by["More inflow"]
    with pytest.raises(ValueError, match="must be 'baseline' or one of the compared"):
        _run(options_root, reference="Nope")


def test_claims_name_the_metric_reference_and_world(options_root):
    from latris.operations.sd_montecarlo import describe_option

    p = sd_ops.run_compare(["More inflow"], "Water", runs=20, settings={"final_time": 20},
                           apply_to_all=["Drain Rate=0.1"], root=options_root)
    row = next(r for r in p["options"] if r["name"] == "More inflow")
    text = describe_option(p, row)
    assert "Water, final value:" in text
    assert "vs the baseline (no scenario changes)" in text
    assert "; in every run: Drain Rate=0.1" in text
    base = next(r for r in p["options"] if r["name"] == "baseline")
    assert describe_option(p, base).startswith("Baseline (no scenario changes) — Water")


def test_scenario_loops_and_orphans_are_refused(options_root):
    from latris.operations import sd_scenarios

    with pytest.raises(ValueError, match="no scenario named"):
        sd_scenarios.set_scenario("X", ["Inflow Rate=3"], extends="Missing", root=options_root)
    _delayed(options_root)
    with pytest.raises(ValueError, match="in a loop"):
        sd_scenarios.set_scenario("More inflow", ["Inflow Rate=8"], extends="More inflow later", root=options_root)
    with pytest.raises(ValueError, match="extends 'More inflow'"):
        sd_scenarios.remove_scenario("More inflow", root=options_root)


def test_extends_and_reference_survive_a_spec_round_trip(options_root):
    from latris.operations.build import build_from_spec
    from latris.operations.init import init_project
    from latris.operations.share_link import export_spec

    _delayed(options_root)
    sd_ops.record_compare(sd_ops.run_compare(["More inflow", "More inflow later"], "Water", runs=20,
                                             settings={"final_time": 20}, reference="baseline", root=options_root),
                          root=options_root)
    _, spec = export_spec(model_type="sd", root=options_root)
    by = {s.name: s for s in spec.sd.scenarios}
    assert by["More inflow later"].extends == "More inflow"
    (cmp,) = [a for a in spec.analyses if a.kind == "compare"]
    assert cmp.reference == "baseline"
    # the child listed before its parent still builds (parents are applied first)
    spec.sd.scenarios.sort(key=lambda s: s.name != "More inflow later")
    other = options_root.parent / "rebuilt"
    init_project(other, statement="Q?")
    build_from_spec(spec, root=other)
    from latris.operations import sd_scenarios

    rebuilt = {s.name: s for s in sd_scenarios.list_scenarios(root=other)}
    assert rebuilt["More inflow later"].extends == "More inflow"
