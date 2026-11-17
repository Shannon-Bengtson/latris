"""One map, three model types: membership drives readiness, staleness and claims consistently."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import sd as sd_ops
from latris.repo.layout import ProjectPaths
from tests.conftest import build_with_template_identity, clone_project
from tests.mixed_model import build_mixed_model


@pytest.fixture(scope="module")
def _template_mixed(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_with_template_identity(lambda: build_mixed_model(tmp_path_factory.mktemp("tpl_mixed") / "proj"))


@pytest.fixture
def mixed_root(_template_mixed: Path, tmp_path: Path, git_identity) -> Path:
    return clone_project(_template_mixed, tmp_path / "proj")


def _labels(root: Path, ids) -> set[str]:
    from latris.repo.yaml_io import load_model
    from latris.schema import Substrate

    sub = load_model(Substrate, ProjectPaths(root).conceptual_yaml)
    by_id = {e.id: e.label for e in sub.entities}
    return {by_id[i] for i in ids if i in by_id}


# ── membership ───────────────────────────────────────────────────────


def test_each_type_is_made_of_its_own_factors(mixed_root):
    from latris.operations.membership import members

    paths = ProjectPaths(mixed_root)
    assert members(paths, "cld") is None  # the loop map is the whole map
    sd = _labels(mixed_root, members(paths, "sd").entity_ids)
    assert "Water-column phosphorus" in sd and "Catchment load" not in sd and "Bloom" not in sd
    assert _labels(mixed_root, members(paths, "bn").entity_ids) == {
        "Hot week", "Bloom", "Customer exceedance", "Barrier fails"}


# ── the simulation inside a loop map ─────────────────────────────────


def test_loop_map_links_into_the_simulation_dont_block_it(mixed_root):
    assert sd_ops.check(root=mixed_root) == []
    result = sd_ops.simulate(final_time=10, root=mixed_root)
    assert result.success


def test_loop_map_links_are_reported_as_advisories(mixed_root):
    advisories = [g for g in sd_ops.check(advisories=True, root=mixed_root) if g.severity == "advisory"]
    kinds = {(g.gap_type, g.element_label) for g in advisories}
    assert ("outside_link", "Catchment load → Water-column phosphorus") in kinds
    assert ("outside_link", "Bottom-water anoxia → Internal P release") in kinds
    assert ("stock_causal_input", "Internal P release → Water-column phosphorus") in kinds


def test_an_sd_only_model_still_flags_unclassified_parents(sd_diagram_root):
    gaps = {g.gap_type for g in sd_ops.check(root=sd_diagram_root)}
    assert "unclassified" in gaps


def test_not_ready_error_names_the_factor(mixed_root):
    from latris.operations._sd_eval import EquationError

    sd_ops.set_role("Treatment cost", "flow", root=mixed_root)  # a flow that fills nothing
    with pytest.raises(EquationError, match="Treatment cost: "):
        sd_ops.simulate(final_time=5, root=mixed_root)


# ── the network beside a loop map ────────────────────────────────────


def test_loop_map_cycles_dont_make_the_network_unready(mixed_root):
    from latris.operations.readiness import assess_readiness

    r = assess_readiness("bn", root=mixed_root)
    assert r.score > 0, r.gaps
    assert "cycle_detected" not in {g.gap_type for g in r.gaps}


def test_interpretation_has_sections_for_every_type(mixed_root):
    from latris.operations.interpret import initialise_sections

    store, _, skipped = initialise_sections(root=mixed_root)
    assert skipped == []
    assert {s.model_type for s in store.sections} >= {"cld", "sd", "bn"}


def test_empty_network_sharing_a_loop_map_says_so(tmp_path, git_identity):
    from latris.operations.edges import add_edge
    from latris.operations.init import init_project
    from latris.operations.nodes import add_node
    from latris.operations.project import update_selected_models
    from latris.operations.readiness import assess_readiness

    root = tmp_path / "proj"
    init_project(root, statement="Q?")
    a, _ = add_node("A", root=root)
    b, _ = add_node("B", root=root)
    add_edge(a.id, b.id, kind="causal", root=root)
    add_edge(b.id, a.id, kind="causal", root=root)
    update_selected_models(["cld", "bn"], root=root)
    r = assess_readiness("bn", root=root)
    assert r.score == 0
    assert [g.gap_type for g in r.gaps] == ["empty_network"]


# ── staleness ────────────────────────────────────────────────────────


def test_editing_the_loop_map_leaves_simulation_results_fresh(mixed_root):
    from latris.operations.analysis_results import report_results
    from latris.operations.edges import add_edge
    from latris.operations.nodes import add_node

    sd_ops.record_simulation(sd_ops.simulate(final_time=10, root=mixed_root), root=mixed_root)
    new, _ = add_node("Algaecide dosing", root=mixed_root)
    from latris.operations._resolve import resolve_entity
    from latris.repo.yaml_io import load_model
    from latris.schema import Substrate

    sub = load_model(Substrate, ProjectPaths(mixed_root).conceptual_yaml)
    add_edge(new.id, resolve_entity("Cyanobacteria biomass", sub.entities).id, kind="causal", root=mixed_root)
    [res] = [r for r in report_results(model_types=["sd"], root=mixed_root)]
    assert not res.stale

    sd_ops.set_constant("Settling rate", 2.0, "1/year", root=mixed_root)
    [res] = [r for r in report_results(model_types=["sd"], root=mixed_root)]
    assert res.stale


def test_runs_recorded_before_keep_their_whole_map_fingerprint(mixed_root):
    from latris.operations.analysis_results import fingerprint
    from latris.operations.nodes import add_node

    paths = ProjectPaths(mixed_root)
    v1, v2 = fingerprint(paths, "sd", version=1), fingerprint(paths, "sd", version=2)
    add_node("Something in the loop map", root=mixed_root)
    assert fingerprint(paths, "sd", version=1) != v1
    assert fingerprint(paths, "sd", version=2) == v2


# ── taking a factor out of a model type ─────────────────────────────


def test_unset_role_keeps_the_factor_and_its_links(mixed_root):
    from latris.operations.membership import members
    from latris.operations.nodes import list_nodes

    sd_ops.set_role("Treatment cost", "auxiliary", root=mixed_root)
    assert sd_ops.check(root=mixed_root)  # an auxiliary with no equation
    _, removed, _ = sd_ops.unset_role("Treatment cost", root=mixed_root)
    assert removed == 1
    assert sd_ops.check(root=mixed_root) == []
    assert "Treatment cost" in {n.label for n in list_nodes(mixed_root)}
    assert "Treatment cost" not in _labels(mixed_root, members(ProjectPaths(mixed_root), "sd").entity_ids)


def test_unset_role_drops_the_values(mixed_root):
    _, removed, _ = sd_ops.unset_role("Release rate", root=mixed_root)
    assert removed >= 2  # role + constant
    assert "Release rate" not in {c.target_id for c in sd_ops.get_constants(root=mixed_root).entries}


def test_remove_states_refuses_a_parent_and_removes_a_leaf(mixed_root):
    from latris.operations import bn as bn_ops

    with pytest.raises(ValueError, match="parent"):
        bn_ops.remove_states("Hot week", root=mixed_root)
    _, removed, _ = bn_ops.remove_states("Customer exceedance", root=mixed_root)
    assert removed >= 2  # states + table
    assert len(bn_ops.get_state_spaces(root=mixed_root).entries) == 3


# ── one answer for the whole model ───────────────────────────────────


def test_a_model_of_several_types_gets_one_answer(mixed_root):
    from latris.operations.interpret import initialise_sections
    from latris.operations.interpret_registry import MODEL_WIDE, MODEL_WIDE_SECTIONS

    store, _, _ = initialise_sections(root=mixed_root)
    answers = [s for s in store.sections if s.section_type == "answer_to_question"]
    assert [s.model_type for s in answers] == [MODEL_WIDE]
    for section_type in MODEL_WIDE_SECTIONS:
        assert sum(s.section_type == section_type for s in store.sections) == 1
    # technical sections stay per type
    assert {s.model_type for s in store.sections if s.section_type == "structural_summary"} == {"cld", "sd", "bn"}


def test_model_wide_claims_are_labelled_by_source(mixed_root):
    from latris.operations.interpret import extract_claims
    from latris.operations.interpret_registry import MODEL_WIDE

    sd_ops.record_simulation(sd_ops.simulate(final_time=10, root=mixed_root), root=mixed_root)
    claims = extract_claims("answer_to_question", MODEL_WIDE, root=mixed_root)
    assert any(c.startswith("Simulation: Simulation (baseline): Water-column phosphorus") for c in claims), claims


def test_per_type_prose_is_kept_when_a_second_type_arrives(tmp_path, git_identity):
    from latris.operations.edges import add_edge
    from latris.operations.init import init_project
    from latris.operations.interpret import initialise_sections, load_interpretation, update_prose
    from latris.operations.interpret_registry import MODEL_WIDE
    from latris.operations.nodes import add_node
    from latris.operations.project import update_selected_models

    root = tmp_path / "proj"
    init_project(root, statement="Q?")
    a, _ = add_node("A", root=root)
    b, _ = add_node("B", root=root)
    add_edge(a.id, b.id, kind="causal", root=root)
    add_edge(b.id, a.id, kind="causal", root=root)
    update_selected_models(["cld"], root=root)
    store, _, _ = initialise_sections(root=root)
    answer = next(s for s in store.sections if s.section_type == "answer_to_question")
    update_prose(answer.id, "A drives B, which drives A.", source="ai", root=root)

    update_selected_models(["cld", "fcm"], root=root)
    initialise_sections(root=root)
    answers = [s for s in load_interpretation(root=root).sections if s.section_type == "answer_to_question"]
    assert len(answers) == 1 and answers[0].model_type == MODEL_WIDE
    assert answers[0].prose == "A drives B, which drives A."


def test_scoped_claims_describe_the_simulation_not_the_map(mixed_root):
    from latris.operations.interpret import extract_claims

    claims = extract_claims("structural_summary", "sd", root=mixed_root)
    assert claims[0].startswith("The simulation has 9 factors"), claims[0]
    gaps = " ".join(extract_claims("evidence_gaps", "sd", root=mixed_root))
    assert "simulation links" in gaps


# ── check before handing over ────────────────────────────────────────


def test_handover_checks_every_model_type(mixed_root):
    from latris.operations.handover import handover_check

    sd_ops.set_role("Treatment cost", "auxiliary", root=mixed_root)  # an SD gap
    report = handover_check(root=mixed_root)
    assert report.model_types == ["cld", "sd", "bn"]
    kinds = {i.kind: i for i in report.items}
    waiting = kinds["unapproved_findings"]
    assert waiting.count == 3  # one finding per type, not just the loop map's
    assert any(i.kind == "model_incomplete" and "System Dynamics" in i.message for i in report.items)


def test_handover_flags_findings_about_removed_factors(mixed_root):
    from latris.operations.handover import handover_check
    from latris.operations.nodes import remove_node

    remove_node("Bottom-water anoxia", root=mixed_root)
    kinds = {i.kind for i in handover_check(root=mixed_root).items}
    assert "findings_about_removed" in kinds


def test_handover_flags_an_unsaved_what_if_in_the_report(mixed_root):
    from latris.operations.handover import handover_check

    payload, runs = sd_ops.simulate_scenarios(assignments=["Release rate=0.3"], final_time=5, root=mixed_root)
    sd_ops.record_comparison(payload, runs, root=mixed_root)
    kinds = {i.kind for i in handover_check(root=mixed_root).items}
    assert "exploratory_results" in kinds


# ── addressing ───────────────────────────────────────────────────────


def test_a_link_can_be_removed_by_its_labels(mixed_root):
    from latris.operations.edges import remove_edge

    edge, _ = remove_edge("Catchment load -> Water-column phosphorus", root=mixed_root)
    assert edge.kind == "causal"


def test_records_about_a_removed_factor_are_listed(mixed_root):
    from latris.operations._cascade import records_about
    from latris.operations.nodes import remove_node

    entity, edges, _ = remove_node("Bottom-water anoxia", root=mixed_root)
    left = records_about(ProjectPaths(mixed_root), [entity.id, *edges])
    assert left == ["finding: Internal release and blooms reinforce each other (R1)."]


# ── report labelling ─────────────────────────────────────────────────


def test_result_headings_say_which_run_is_which(mixed_root):
    from latris.exporters.results import render_results
    from latris.operations import bn as bn_ops

    payload, runs = sd_ops.simulate_scenarios(assignments=["Release rate=0.3"], final_time=5, root=mixed_root)
    sd_ops.record_comparison(payload, runs, root=mixed_root)
    bn_ops.record_query(bn_ops.infer(root=mixed_root), root=mixed_root)
    bn_ops.record_query(bn_ops.infer(evidence={"Hot week": "yes"}, root=mixed_root), root=mixed_root)
    lines = render_results(ProjectPaths(mixed_root))
    headings = [line for line in lines if line.startswith("### ")]
    assert "### Simulation: baseline vs unsaved what-if (Release rate=0.3)" in headings
    assert "### Probabilities: no evidence (prior)" in headings
    assert "### Probabilities: given Hot week = yes" in headings
    assert any(line.startswith("_Run 20") for line in lines)


# ── network interventions ────────────────────────────────────────────


def test_setting_a_factor_differs_from_observing_it(mixed_root):
    from latris.operations import bn as bn_ops
    from latris.operations._resolve import resolve_entity
    from latris.repo.yaml_io import load_model
    from latris.schema import Substrate

    sub = load_model(Substrate, ProjectPaths(mixed_root).conceptual_yaml)
    hot = resolve_entity("Hot week", sub.entities).id
    exceed = resolve_entity("Customer exceedance", sub.entities).id

    seen = bn_ops.infer(evidence={"Bloom": "yes"}, root=mixed_root)
    made = bn_ops.infer(interventions={"Bloom": "yes"}, root=mixed_root)
    assert seen.marginals[hot]["yes"] > 0.3  # seeing a bloom says a hot week is likelier
    assert made.marginals[hot]["yes"] == pytest.approx(0.3)  # making one doesn't
    # P(exceedance | do(bloom)) = P(fail)·0.5 + P(no fail)·0.05
    assert made.marginals[exceed]["yes"] == pytest.approx(0.05 * 0.5 + 0.95 * 0.05)


def test_an_intervention_is_recorded_labelled_and_replayed(mixed_root):
    from latris.exporters.results import render_results
    from latris.operations import bn as bn_ops
    from latris.operations.analysis_replay import definitions

    bn_ops.record_query(bn_ops.infer(interventions={"Barrier fails": "no"}, root=mixed_root), root=mixed_root)
    headings = [h for h in render_results(ProjectPaths(mixed_root)) if h.startswith("### Probabilities")]
    assert headings == ["### Probabilities: given we set Barrier fails = no"]
    [spec] = [d for d in definitions(root=mixed_root) if d.kind == "bn_query"]
    assert spec.interventions == {"Barrier fails": "no"}


def test_a_factor_cant_be_set_and_observed(mixed_root):
    from latris.operations import bn as bn_ops

    with pytest.raises(ValueError, match="set or observed"):
        bn_ops.infer(evidence={"Bloom": "yes"}, interventions={"Bloom": "no"}, root=mixed_root)
