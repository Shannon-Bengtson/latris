"""The report's Results section, the claims drawn from results, and handover's view of them."""

from __future__ import annotations

import json

import pytest

from latris.exporters import markdown
from latris.operations import sd as sd_ops
from latris.operations import sd_scenarios, uncertainty
from latris.repo.project import require_project

pytest.importorskip("scipy")

SETTINGS = {"final_time": 10, "dt": 0.25, "saveper": 1, "method": "euler"}


def _record_everything(root):
    sd_scenarios.set_scenario("Faster drain", ["Drain Rate=0.2"], description="Wider plughole",
                              reason="plumber's quote", origin="ai-proposed", root=root)
    payload, runs = sd_ops.simulate_scenarios(["Faster drain"], [], **SETTINGS, root=root)
    sd_ops.record_comparison(payload, runs, root=root)
    uncertainty.set_uncertainty("Drain Rate", "uniform", {"min": 0.05, "max": 0.2}, origin="ai-proposed",
                                root=root)
    sd_ops.record_monte_carlo(sd_ops.run_monte_carlo(runs=40, settings=SETTINGS, root=root), root=root)
    sd_ops.record_sensitivity(sd_ops.run_sensitivity("Water", settings=SETTINGS, root=root), root=root)
    sd_ops.record_loops(sd_ops.run_loops(settings=SETTINGS, root=root), root=root)


def test_client_report_shows_results_after_the_diagram(sd_bathtub_root):
    root = sd_bathtub_root
    _record_everything(root)
    md = markdown.render(require_project(root), pack="client", ai=False)
    assert "## Results" in md and md.index("## Results") > md.index("## Diagram")
    for heading in ("### Simulation", "### Uncertainty (Monte Carlo)", "### Sensitivity of Water",
                    "### Feedback loop dominance"):
        assert heading in md
    assert "Drain Rate 0.1 1/year → 0.2 1/year" in md and "AI-proposed, not yet reviewed" in md
    assert "B1 (Water → Outflow) dominates" in md
    assert "latris-chart" not in md  # plain Markdown stays clean

    with_charts = markdown.render(require_project(root), pack="client", ai=False, chart_markers=True)
    fences = [block.split("\n", 1)[1].split("\n```")[0] for block in with_charts.split("```latris-chart")[1:]]
    charts = [json.loads(f)["chart"] for f in fences]
    assert charts == ["series", "bands", "tornado", "loops"]


def test_results_go_out_of_date_and_can_be_hidden(sd_bathtub_root):
    from latris.operations import analysis_results as ar
    from latris.operations.handover import handover_check

    root = sd_bathtub_root
    sd_ops.record_simulation(sd_ops.simulate(**SETTINGS, root=root), root=root)
    sd_ops.set_constant("Inflow Rate", 7, "liter/year", root=root)
    md = markdown.render(require_project(root), pack="client", ai=False)
    assert "**Out of date**" in md and "latris results hide" not in md  # no CLI hints in client packs
    review = markdown.render(require_project(root), pack="review", ai=False)
    assert "latris results hide" in review

    kinds = {i.kind for i in handover_check(model_type="sd", root=root).items}
    assert "stale_results" in kinds and "model_incomplete" not in kinds
    (run, _, _), = ar.list_results(root=root)
    ar.set_hidden(run.id, True, root=root)
    assert "## Results" not in markdown.render(require_project(root), pack="client", ai=False)
    assert "stale_results" not in {i.kind for i in handover_check(model_type="sd", root=root).items}


def test_sd_gets_interpretation_sections_with_claims_from_results(sd_bathtub_root):
    from latris.operations.interpret import extract_claims, initialise_sections
    from latris.operations.project import update_selected_models

    root = sd_bathtub_root
    update_selected_models(["sd"], root=root)
    _record_everything(root)
    store, _, skipped = initialise_sections(root=root)
    assert not skipped
    assert {s.section_type for s in store.sections if s.model_type == "sd"} >= {"answer_to_question", "sensitivity"}

    answer = extract_claims("answer_to_question", "sd", root=root)
    assert any(c.startswith("Simulation (baseline): Water goes from 100 to") for c in answer)
    assert any(c.startswith("Scenario Faster drain (Drain Rate 0.1 1/year → 0.2 1/year): Water ends at") for c in answer)
    sens = extract_claims("sensitivity", "sd", root=root)
    assert any("in 95% of runs" in c for c in sens)
    assert any(c.startswith("Water's final value is most sensitive to Drain Rate") for c in sens)
    questions = extract_claims("open_questions", "sd", root=root)
    assert any("Faster drain's values are AI-proposed" in c for c in questions)
    assert any(c.startswith("Loop B1 dominates for a period but rests on weak links") for c in questions)

    # Results computed before a model change stop producing claims.
    sd_ops.set_constant("Inflow Rate", 7, "liter/year", root=root)
    assert not any("Simulation (baseline)" in c for c in extract_claims("answer_to_question", "sd", root=root))
