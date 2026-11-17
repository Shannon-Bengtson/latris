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
    assert any("More inflow:" in c and "higher than the baseline" in c for c in claims)


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
