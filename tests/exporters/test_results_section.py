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
    for heading in ("#### Simulation", "#### Uncertainty (Monte Carlo)", "#### Sensitivity of Water",
                    "#### Feedback loop dominance"):
        assert heading in md
    # Grouped by workflow step, in the Analyse stage's order (schema/workflow.py).
    lines = md.split("\n")
    top = next(i for i, line in enumerate(lines) if line.lstrip("#") == " Results")
    level = len(lines[top]) - len(lines[top].lstrip("#"))  # packs nest Results at different depths
    step_prefix = "#" * (level + 1) + " "
    body = []
    for line in lines[top + 1:]:
        heading = len(line) - len(line.lstrip("#"))
        if line.startswith("#") and 0 < heading <= level:
            break  # the end of the Results section
        body.append(line)
    steps = [line[len(step_prefix):] for line in body if line.startswith(step_prefix)]
    # The scenario run is recorded as a simulation, so there is no option comparison here.
    assert steps == ["Base-case analysis", "Uncertainty analysis", "Sensitivity analysis"]
    assert md.index("Feedback loop dominance") < md.index(f"{step_prefix}Uncertainty analysis")
    assert "Drain Rate 0.1 1/year → 0.2 1/year" in md and "AI-proposed, not yet reviewed" in md
    assert "B1 (Water → Outflow) dominates" in md
    assert "latris-chart" not in md  # plain Markdown stays clean

    with_charts = markdown.render(require_project(root), pack="client", ai=False, chart_markers=True)
    fences = [block.split("\n", 1)[1].split("\n```")[0] for block in with_charts.split("```latris-chart")[1:]]
    charts = [json.loads(f)["chart"] for f in fences]
    assert charts == ["series", "loops", "bands", "tornado"]  # by step: base case, uncertainty, sensitivity


def test_results_go_out_of_date_and_can_be_hidden(sd_bathtub_root):
    from latris.operations import analysis_results as ar
    from latris.operations.handover import handover_check

    root = sd_bathtub_root
    sd_ops.record_simulation(sd_ops.simulate(**SETTINGS, root=root), root=root)
    sd_ops.set_constant("Inflow Rate", 7, "liter/year", root=root)
    md = markdown.render(require_project(root), pack="client", ai=False)
    # A reader isn't shown results from an earlier version of the model, only told they exist.
    assert "**Out of date**" not in md and "latris results hide" not in md  # no CLI hints in client packs
    assert "### Simulation" not in md
    assert "computed on an earlier version of the model and haven't been re-run yet" in md
    review = markdown.render(require_project(root), pack="review", ai=False)
    assert "**Out of date**" in review and "latris results hide" in review

    kinds = {i.kind for i in handover_check(model_type="sd", root=root).items}
    assert "stale_results" in kinds and "model_incomplete" not in kinds
    (run, _, _), = ar.list_results(root=root)
    ar.set_hidden(run.id, True, root=root)
    assert "## Results" not in markdown.render(require_project(root), pack="client", ai=False)
    assert "stale_results" not in {i.kind for i in handover_check(model_type="sd", root=root).items}


def test_reader_packs_show_current_results_once_and_count_the_earlier_ones(sd_bathtub_root):
    root = sd_bathtub_root
    sd_ops.record_loops(sd_ops.run_loops(settings=SETTINGS, root=root), root=root)
    sd_ops.set_constant("Inflow Rate", 7, "liter/year", root=root)  # the loop run is now out of date
    sd_ops.record_simulation(sd_ops.simulate(**SETTINGS, root=root), root=root)
    sd_ops.record_simulation(sd_ops.simulate(**{**SETTINGS, "dt": 0.5}, root=root), root=root)
    md = markdown.render(require_project(root), pack="client", ai=False)
    assert md.count("#### Simulation") == 1 and "Feedback loop dominance" not in md
    assert "_1 result from an earlier version of this model isn't shown. They're kept in the project's " \
        "analysis history._" in md
    review = markdown.render(require_project(root), pack="review", ai=False)
    assert "### Feedback loop dominance" in review and "**Out of date**" in review


def test_reader_packs_show_a_repeated_question_once(sd_bathtub_root, monkeypatch):
    from latris.exporters import results
    from latris.operations import analysis_results as ar

    root = sd_bathtub_root
    sd_ops.record_simulation(sd_ops.simulate(**SETTINGS, root=root), root=root)
    (only,) = ar.report_results(root=root)
    # Two runs of the same question that the latest-run rule keeps apart (different analysis keys).
    monkeypatch.setattr(ar, "report_results", lambda **_: [only, only])
    current = results.render_results(require_project(root), current_only=True)
    assert sum(line.startswith("#### Simulation") for line in current) == 1
    assert sum(line.startswith("#### Simulation") for line in results.render_results(require_project(root))) == 2
    assert sum(line == "### Base-case analysis" for line in current) == 1  # one step heading for the group


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
    assert any(c.startswith("Across their stated uncertainty ranges, Water's final value is most sensitive to Drain Rate")
               for c in sens)
    questions = extract_claims("open_questions", "sd", root=root)
    assert any("Faster drain's values are AI-proposed" in c for c in questions)
    assert any(c.startswith("Loop B1 dominates for a period but rests on weak links") for c in questions)

    # Results computed before a model change stop producing claims.
    sd_ops.set_constant("Inflow Rate", 7, "liter/year", root=root)
    assert not any("Simulation (baseline)" in c for c in extract_claims("answer_to_question", "sd", root=root))
