"""Tests for interpretation operations — claim extraction, CRUD, versioning."""

from pathlib import Path

import pytest

from latris.operations.edges import add_edge
from latris.operations.findings import record_new_finding
from latris.operations.init import init_project
from latris.operations.interpret import (
    extract_claims,
    initialise_sections,
    load_interpretation,
    refresh_all_claims,
    refresh_claims,
    update_prose,
)
from latris.operations.interpret_registry import (
    INTERPRET_SECTION_REGISTRY,
    get_sections_for_model_types,
)
from latris.operations.nodes import add_node
from latris.operations.readiness import assess_interpret_readiness
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import dump_model, load_model
from latris.schema.project import ProjectFoundation


@pytest.fixture
def project(tmp_path: Path, git_identity):
    root = tmp_path / "proj"
    init_project(root, statement="What drives water quality decline?")
    # Select CLD model type and commit
    paths = ProjectPaths(root)
    foundation = load_model(ProjectFoundation, paths.project_yaml)
    foundation.selected_model_types = ["cld"]
    dump_model(foundation, paths.project_yaml)
    from latris.operations.commit import auto_commit

    auto_commit(root, subject="Select CLD model type", paths=[paths.project_yaml])
    # Add some structure — close a loop so the CLD readiness gate
    # (loops_present) is satisfied.
    add_node("Nutrient load", root=root)
    add_node("Algal bloom", root=root)
    add_edge("Nutrient load", "Algal bloom", root=root)
    add_edge("Algal bloom", "Nutrient load", root=root)
    return root


@pytest.fixture
def project_with_findings(project: Path):
    """Project with analysis runs and findings (ready for interpret)."""
    # Record findings to make interpret ready
    record_new_finding(
        "High connectivity in nutrient pathways",
        category="structure",
        model_type="cld",
        root=project,
    )
    record_new_finding(
        "Nutrient load is the most central node",
        category="sensitivity",
        model_type="cld",
        root=project,
    )
    record_new_finding(
        "Reducing nutrient load likely reduces algal bloom frequency",
        category="inference",
        model_type="cld",
        root=project,
    )
    # Create a dummy analysis run file so readiness passes
    from latris.repo.yaml_io import dump_jsonl_append
    from latris.schema.analysis import AnalysisRun
    from latris.schema.common import HumanActor
    from latris.schema.ids import new_id

    paths = ProjectPaths(project)
    run = AnalysisRun(
        id=new_id("analysis-run"),
        run_by=HumanActor(name="Test", email="t@t.com"),
        purpose="validation",
        algorithm="loop-detection",
        library_version="1.0",
    )
    dump_jsonl_append(run, paths.analysis_runs_jsonl)
    return project


class TestInterpretRegistry:
    def test_nine_sections_registered(self):
        assert len(INTERPRET_SECTION_REGISTRY) == 10

    def test_sections_for_cld(self):
        specs = get_sections_for_model_types(["cld"])
        assert len(specs) == 10

    def test_sections_for_unknown_type(self):
        specs = get_sections_for_model_types(["unknown"])
        assert len(specs) == 0


class TestInterpretReadiness:
    def test_not_ready_no_model_types(self, tmp_path: Path, git_identity):
        """No model types selected → cannot enter interpret."""
        root = tmp_path / "empty_proj"
        init_project(root, statement="Q?")
        result = assess_interpret_readiness(root=root)
        assert not result.can_enter
        assert result.score == 0
        assert len(result.missing) > 0

    def test_ready_when_model_type_ready(self, project: Path):
        """CLD selected + model ready → can enter interpret."""
        result = assess_interpret_readiness(root=project)
        assert result.can_enter
        assert result.score == 100


class TestClaimExtraction:
    def test_structural_summary_includes_topology(self, project_with_findings: Path):
        claims = extract_claims("structural_summary", "cld", root=project_with_findings)
        assert len(claims) >= 1
        # Should include entity/edge count
        assert any("entities" in c for c in claims)

    def test_structural_summary_from_structure(self, project: Path):
        """Even without findings, structural summary extracts from model graph."""
        claims = extract_claims("structural_summary", "cld", root=project)
        assert len(claims) >= 1
        assert any("2 entities" in c for c in claims)

    def test_sensitivity_from_centrality(self, project_with_findings: Path):
        claims = extract_claims("sensitivity", "cld", root=project_with_findings)
        assert len(claims) >= 1

    def test_answer_includes_modelling_question(self, project_with_findings: Path):
        claims = extract_claims("answer_to_question", "cld", root=project_with_findings)
        assert any("water quality" in c.lower() for c in claims)

    def test_key_findings_includes_centrality(self, project: Path):
        """Key findings should derive from model structure even without recorded findings."""
        claims = extract_claims("key_findings", "cld", root=project)
        assert len(claims) >= 1

    def test_dag_structural_summary_acyclic(self, tmp_path: Path, git_identity):
        """DAG StructuralSummary asserts the positive 'confirmed' claim
        when the substrate is acyclic."""
        from latris.operations.project import update_selected_models

        root = tmp_path / "dag_acyclic"
        init_project(root, statement="Q?")
        update_selected_models(["dag"], root=root)
        a, _ = add_node("A", root=root)
        b, _ = add_node("B", root=root)
        add_edge(a.id, b.id, root=root)

        claims = extract_claims("structural_summary", "dag", root=root)
        assert any("DAG structure confirmed" in c for c in claims)
        assert not any("FAILS" in c for c in claims)

    def test_loop_count_consistency_across_extractors(self, tmp_path: Path, git_identity):
        """Regression for the capability-run inflation bug.

        When a decision_rule edge creates extra cycles, the structural-summary,
        key-findings, and answer-to-question extractors must all report the
        same loop count — namely, the count over causal edges only.
        Including decision_rule edges in structural metrics produced the
        contradictory 5/0 vs 14/3 numbers in the 4DWW capability artefact.
        """
        from latris.operations.project import update_selected_models
        from latris.operations.view_attributes import set_view_attribute

        root = tmp_path / "loop_consistency"
        init_project(root, statement="Q?")
        update_selected_models(["cld"], root=root)
        a, _ = add_node("A", root=root)
        b, _ = add_node("B", root=root)
        c, _ = add_node("C", root=root)
        # One causal 2-cycle: A↔B with both edges positive → R loop.
        e_ab, _ = add_edge(a.id, b.id, root=root)
        e_ba, _ = add_edge(b.id, a.id, root=root)
        # Causal A→C and decision_rule C→A. If the decision_rule edge is
        # (incorrectly) included in loop-finding, a second cycle through C
        # appears and the count doubles.
        e_ac, _ = add_edge(a.id, c.id, root=root)
        add_edge(c.id, a.id, kind="decision_rule", root=root)
        for edge_id in (e_ab.id, e_ba.id, e_ac.id):
            set_view_attribute(edge_id, "cld", "polarity", "+", root=root)

        def _r_count(claims: list[str]) -> int:
            for claim in claims:
                # answer_to_question phrasing: "<N> reinforcing loop(s) may drive…"
                if claim.endswith("may drive escalation or growth."):
                    return int(claim.split()[0])
                # structural_summary phrasing: "<total> feedback loop(s) detected: <R> reinforcing, <B> balancing…"
                if "feedback loop(s) detected" in claim:
                    after = claim.split("detected:", 1)[1]
                    return int(after.split("reinforcing")[0].strip().rstrip(","))
            return 0

        structural = extract_claims("structural_summary", "cld", root=root)
        answer = extract_claims("answer_to_question", "cld", root=root)
        key = extract_claims("key_findings", "cld", root=root)

        # All three extractors must agree: 1 reinforcing loop (causal A↔B).
        # If decision_rule edges leaked in, structural would still see 1 (it
        # was already filtered) but answer would report 2.
        assert _r_count(structural) == 1, structural
        assert _r_count(answer) == 1, answer
        # key_findings should not mention C as a loop participant — C only
        # participates via the decision_rule edge.
        assert not any("C" in claim and "loop" in claim.lower() for claim in key), key

    def test_dag_structural_summary_cyclic(self, tmp_path: Path, git_identity):
        """When the substrate is cyclic, the DAG StructuralSummary
        reports the readiness-fail rather than the stale 'acyclic'
        claim. Defensive: this path is normally skipped by the
        Interpret-section filter, but the claim must still be correct
        if invoked directly."""
        from latris.operations.project import update_selected_models

        root = tmp_path / "dag_cyclic"
        init_project(root, statement="Q?")
        update_selected_models(["dag"], root=root)
        a, _ = add_node("A", root=root)
        b, _ = add_node("B", root=root)
        add_edge(a.id, b.id, root=root)
        add_edge(b.id, a.id, root=root)  # closes a 2-cycle

        claims = extract_claims("structural_summary", "dag", root=root)
        assert any("DAG readiness FAILS" in c for c in claims)
        assert any("cycle" in c.lower() for c in claims)
        assert not any("DAG structure confirmed" in c for c in claims)


class TestInitialise:
    def test_initialise_creates_sections(self, project_with_findings: Path):
        store, sha, _skipped = initialise_sections(root=project_with_findings)
        # CLD selected by default → 9 sections for CLD
        assert len(store.sections) >= 9
        assert sha  # commit created

    def test_initialise_idempotent(self, project_with_findings: Path):
        store1, _, _ = initialise_sections(root=project_with_findings)
        # Second call should not add any new sections
        store2 = load_interpretation(root=project_with_findings)
        assert len(store1.sections) == len(store2.sections)

    def test_initialise_skips_dag_when_substrate_cyclic(self, tmp_path: Path, git_identity):
        """When CLD and DAG are both selected but the substrate has
        loops, DAG fails structural readiness — the Interpret filter
        skips DAG sections and lists DAG in the skipped reasons."""
        from latris.operations.project import update_selected_models

        root = tmp_path / "cld_with_dag_skip"
        init_project(root, statement="Q?")
        update_selected_models(["cld", "dag"], root=root)
        a, _ = add_node("A", root=root)
        b, _ = add_node("B", root=root)
        add_edge(a.id, b.id, root=root)
        add_edge(b.id, a.id, root=root)  # closes a 2-cycle

        store, _, skipped = initialise_sections(root=root)

        cld_sections = [s for s in store.sections if s.model_type == "cld"]
        dag_sections = [s for s in store.sections if s.model_type == "dag"]
        assert len(cld_sections) > 0  # CLD has loops → viable
        assert len(dag_sections) == 0  # DAG has cycle → skipped
        assert any(mid == "dag" for mid, _ in skipped)
        # The skip reason should mention the cycle.
        dag_reason = next(reason for mid, reason in skipped if mid == "dag")
        assert "cycle" in dag_reason.lower()

    def test_initialise_skips_cld_when_substrate_acyclic(self, tmp_path: Path, git_identity):
        """Symmetric case: CLD requires loops, so an acyclic substrate
        with both selected means CLD is skipped, DAG keeps sections."""
        from latris.operations.project import update_selected_models

        root = tmp_path / "dag_with_cld_skip"
        init_project(root, statement="Q?")
        update_selected_models(["cld", "dag"], root=root)
        a, _ = add_node("A", root=root)
        b, _ = add_node("B", root=root)
        add_edge(a.id, b.id, root=root)  # acyclic

        store, _, skipped = initialise_sections(root=root)

        cld_sections = [s for s in store.sections if s.model_type == "cld"]
        dag_sections = [s for s in store.sections if s.model_type == "dag"]
        assert len(cld_sections) == 0  # CLD has no loops → skipped
        assert len(dag_sections) > 0  # DAG is acyclic → viable
        assert any(mid == "cld" for mid, _ in skipped)


class TestRefreshClaims:
    def test_refresh_updates_claims(self, project_with_findings: Path):
        store, _, _ = initialise_sections(root=project_with_findings)
        section = store.sections[0]
        assert section.generation_state == "empty"

        updated, sha = refresh_claims(section.id, root=project_with_findings)
        assert updated.generation_state == "claims_only"
        assert len(updated.claims) > 0
        assert sha

    def test_refresh_all(self, project_with_findings: Path):
        initialise_sections(root=project_with_findings)
        store, sha = refresh_all_claims(root=project_with_findings)
        assert all(s.generation_state == "claims_only" for s in store.sections)
        assert sha


class TestProseManagement:
    def test_update_prose_human_edit(self, project_with_findings: Path):
        store, _, _ = initialise_sections(root=project_with_findings)
        section = store.sections[0]

        updated, sha = update_prose(section.id, "My interpretation.", root=project_with_findings)
        assert updated.prose == "My interpretation."
        assert updated.generation_state == "edited"
        assert len(updated.prose_versions) == 1
        assert updated.prose_versions[0].source == "human-edit"
        assert sha

    def test_update_prose_ai_source(self, project_with_findings: Path):
        store, _, _ = initialise_sections(root=project_with_findings)
        section = store.sections[0]
        # First refresh claims so claims_at_generation can be set
        refresh_claims(section.id, root=project_with_findings)

        updated, sha = update_prose(section.id, "AI generated prose.", source="ai", root=project_with_findings)
        assert updated.generation_state == "generated"
        assert updated.claims_at_generation == updated.claims
        assert len(updated.prose_versions) == 1
        assert updated.prose_versions[0].source == "ai"

    def test_multiple_versions_accumulate(self, project_with_findings: Path):
        store, _, _ = initialise_sections(root=project_with_findings)
        section = store.sections[0]

        update_prose(section.id, "Version 1.", root=project_with_findings)
        updated, _ = update_prose(section.id, "Version 2.", root=project_with_findings)
        assert len(updated.prose_versions) == 2
        assert updated.prose == "Version 2."


class TestPersistence:
    def test_load_after_save(self, project_with_findings: Path):
        initialise_sections(root=project_with_findings)
        store = load_interpretation(root=project_with_findings)
        assert len(store.sections) >= 9


# ── AI interrogation Phase 2b: hedge mode helpers ──────────────────────


class TestCoverageRatio:
    def test_empty_model_returns_full_coverage(self, tmp_path: Path, git_identity):
        """A model with no entities/edges has nothing to cite — ratio == 1.0."""
        from latris.operations.interpret import coverage_ratio

        root = tmp_path / "empty"
        init_project(root, statement="Q?")
        cited, total, ratio = coverage_ratio("cld", ProjectPaths(root))
        assert (cited, total) == (0, 0)
        assert ratio == 1.0

    def test_partial_coverage(self, project: Path):
        from latris.operations.evidence import add_evidence
        from latris.operations.interpret import coverage_ratio
        from latris.operations.references import add_reference

        # Project fixture has 2 entities + 2 edges = 4 elements.
        add_reference("smith2024", title="T", root=project)
        add_evidence("Nutrient load", "description", "smith2024", root=project)
        cited, total, ratio = coverage_ratio("cld", ProjectPaths(project))
        assert total == 4
        assert cited == 1
        assert abs(ratio - 0.25) < 1e-9


class TestHedgeMode:
    def test_active_below_threshold_with_no_findings(self, project: Path):
        from latris.operations.interpret import hedge_mode_active

        # No evidence + no findings → coverage == 0 < 0.5, accepted == 0.
        assert hedge_mode_active("cld", ProjectPaths(project)) is True

    def test_inactive_with_accepted_findings(self, project: Path):
        """Even at zero coverage, approved findings suppress hedge mode."""
        from latris.operations.findings import record_new_finding, set_finding_maturity
        from latris.operations.interpret import hedge_mode_active

        finding, _ = record_new_finding(
            "High connectivity in nutrient pathways",
            category="structure",
            model_type="cld",
            root=project,
        )
        set_finding_maturity(finding.id, maturity="approved", root=project)
        assert hedge_mode_active("cld", ProjectPaths(project)) is False

    def test_inactive_above_threshold(self, tmp_path: Path, git_identity):
        from latris.operations.evidence import add_evidence
        from latris.operations.interpret import hedge_mode_active
        from latris.operations.references import add_reference

        root = tmp_path / "covered"
        init_project(root, statement="Q?")
        # Two entities, evidence on both → coverage 100%.
        n1, _ = add_node("A", root=root)
        n2, _ = add_node("B", root=root)
        add_reference("r", title="t", root=root)
        add_evidence(n1.id, "description", "r", root=root)
        add_evidence(n2.id, "description", "r", root=root)
        assert hedge_mode_active("cld", ProjectPaths(root)) is False


class TestHedgeInstructionInContext:
    def test_hedge_block_appears_when_active(self, project: Path):
        from latris.ai.context import build_context

        pack = build_context(
            "InterpretKeyFindings",
            {
                "section_type": "key_findings",
                "model_type": "cld",
                "claims": ["Nutrient load is central"],
                "_prompt_name": "InterpretKeyFindings",
            },
            ProjectPaths(project),
        )
        assert "HEDGE MODE" in pack.user
        assert "Do NOT report centrality values to >1 decimal place" in pack.user

    def test_hedge_block_absent_when_inactive(self, tmp_path: Path, git_identity):
        from latris.ai.context import build_context
        from latris.operations.evidence import add_evidence
        from latris.operations.references import add_reference

        root = tmp_path / "no_hedge"
        init_project(root, statement="Q?")
        n1, _ = add_node("A", root=root)
        add_reference("r", title="t", root=root)
        add_evidence(n1.id, "description", "r", root=root)

        pack = build_context(
            "InterpretKeyFindings",
            {
                "section_type": "key_findings",
                "model_type": "cld",
                "claims": ["Some claim"],
                "_prompt_name": "InterpretKeyFindings",
            },
            ProjectPaths(root),
        )
        assert "HEDGE MODE" not in pack.user
