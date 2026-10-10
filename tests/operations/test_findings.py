"""Tests for findings operations — CRUD, generators, staleness."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations.fcm_inference import FCMInferenceResult
from latris.operations.findings import (
    check_staleness,
    findings_from_adjustment_sets,
    findings_from_centrality,
    findings_from_dseparation,
    findings_from_fcm_inference,
    findings_from_loops,
    findings_from_propagation,
    get_finding,
    list_findings,
    record_finding,
    record_new_finding,
    set_finding_maturity,
    supersede_matching,
)
from latris.operations.graph_analysis import (
    CentralityResult,
    Loop,
    PropagationEffect,
)
from latris.operations.init import init_project
from latris.repo import git
from latris.schema import HumanActor
from latris.schema.findings import Finding
from latris.schema.ids import new_id

# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def project(tmp_path: Path, git_identity):
    root = tmp_path / "demo"
    init_project(root, statement="Q?")
    a, _ = node_ops.add_node("A", root=root)
    b, _ = node_ops.add_node("B", root=root)
    c, _ = node_ops.add_node("C", root=root)
    edge_ab, _ = edge_ops.add_edge(a.id, b.id, root=root)
    edge_bc, _ = edge_ops.add_edge(b.id, c.id, root=root)
    return root, a, b, c, edge_ab, edge_bc


# ── Schema round-trip ───────────────────────────────────────────────────


class TestSchemaRoundTrip:
    def test_finding_serialise_deserialise(self):
        f = Finding(
            id=new_id("finding"),
            category="structure",
            model_type="cld",
            statement="Found 3 loops.",
            detail="R1, B1, R2",
            payload={"loop_count": 3, "reinforcing": 2, "balancing": 1},
            origin="data-derived",
            source_type="analysis-run",
            target_ids=["node_abc", "node_def"],
        )
        data = f.model_dump(mode="json")
        roundtripped = Finding.model_validate(data)
        assert roundtripped.id == f.id
        assert roundtripped.category == "structure"
        assert roundtripped.payload["loop_count"] == 3
        assert roundtripped.target_ids == ["node_abc", "node_def"]
        assert roundtripped.maturity == "proposed"

    def test_finding_json_roundtrip(self):
        f = Finding(
            id=new_id("finding"),
            category="dynamics",
            model_type="fcm",
            statement="Converged.",
            payload={"converged": True},
        )
        json_str = f.model_dump_json()
        roundtripped = Finding.model_validate_json(json_str)
        assert roundtripped.id == f.id
        assert roundtripped.payload["converged"] is True


# ── CRUD operations ─────────────────────────────────────────────────────


class TestRecordFinding:
    def test_record_appends_to_jsonl(self, project):
        root, a, *_ = project
        finding = Finding(
            id=new_id("finding"),
            category="structure",
            model_type="cld",
            statement="Test finding.",
            model_commit=git.head_sha(root),
        )
        result, sha = record_finding(finding, root=root)
        assert result.id == finding.id
        assert sha

        jsonl = (root / "analysis" / "findings.jsonl").read_text(encoding="utf-8")
        lines = [line for line in jsonl.splitlines() if line]
        assert len(lines) == 1
        assert finding.id in lines[0]

    def test_record_creates_commit(self, project):
        root, *_ = project
        before = int(git.run_git(["rev-list", "--count", "HEAD"], cwd=root).stdout.strip())
        finding = Finding(
            id=new_id("finding"),
            category="inference",
            model_type="dag",
            statement="d-sep test.",
        )
        record_finding(finding, root=root)
        after = int(git.run_git(["rev-list", "--count", "HEAD"], cwd=root).stdout.strip())
        assert after == before + 1

    def test_record_new_finding_convenience(self, project):
        root, a, *_ = project
        finding, sha = record_new_finding(
            "A is important.",
            "sensitivity",
            "cld",
            target_ids=[a.id],
            root=root,
        )
        assert finding.id.startswith("finding_")
        assert finding.category == "sensitivity"
        assert finding.model_commit  # non-empty
        assert sha


class TestListFindings:
    def test_list_empty(self, project):
        root, *_ = project
        assert list_findings(root=root) == []

    def test_list_newest_first(self, project):
        root, *_ = project
        for i in range(3):
            record_new_finding(f"Finding {i}", "structure", "cld", root=root)
        results = list_findings(root=root)
        assert len(results) == 3
        assert results[0].statement == "Finding 2"
        assert results[2].statement == "Finding 0"

    def test_list_filter_by_category(self, project):
        root, *_ = project
        record_new_finding("Loops found.", "structure", "cld", root=root)
        record_new_finding("Central node.", "sensitivity", "cld", root=root)
        record_new_finding("Model valid.", "diagnostics", "cld", root=root)

        structure = list_findings(category="structure", root=root)
        assert len(structure) == 1
        assert structure[0].statement == "Loops found."

    def test_list_filter_by_model_type(self, project):
        root, *_ = project
        record_new_finding("CLD loops.", "structure", "cld", root=root)
        record_new_finding("DAG paths.", "structure", "dag", root=root)

        cld_only = list_findings(model_type="cld", root=root)
        assert len(cld_only) == 1
        assert "CLD" in cld_only[0].statement

    def test_list_filter_by_maturity(self, project):
        root, *_ = project
        f1, _ = record_new_finding("Draft one.", "structure", "cld", root=root)
        set_finding_maturity(f1.id, maturity="approved", root=root)
        record_new_finding("Draft two.", "structure", "cld", root=root)

        approved = list_findings(maturity="approved", root=root)
        assert len(approved) == 1
        assert approved[0].statement == "Draft one."

        proposed = list_findings(maturity="proposed", root=root)
        assert len(proposed) == 1

    def test_list_filter_by_target_id(self, project):
        root, a, b, *_ = project
        record_new_finding("About A.", "structure", "cld", target_ids=[a.id], root=root)
        record_new_finding("About B.", "structure", "cld", target_ids=[b.id], root=root)

        a_findings = list_findings(target_id=a.id, root=root)
        assert len(a_findings) == 1
        assert a_findings[0].statement == "About A."

    def test_list_with_limit(self, project):
        root, *_ = project
        for i in range(5):
            record_new_finding(f"F{i}", "structure", "cld", root=root)
        results = list_findings(limit=2, root=root)
        assert len(results) == 2


class TestGetFinding:
    def test_get_by_exact_id(self, project):
        root, *_ = project
        f, _ = record_new_finding("Test.", "structure", "cld", root=root)
        fetched = get_finding(f.id, root=root)
        assert fetched.id == f.id

    def test_get_by_prefix(self, project):
        root, *_ = project
        f, _ = record_new_finding("Test.", "structure", "cld", root=root)
        prefix = f.id[:20]
        fetched = get_finding(prefix, root=root)
        assert fetched.id == f.id

    def test_get_not_found(self, project):
        root, *_ = project
        with pytest.raises(ValueError, match="no finding matches"):
            get_finding("finding_NOPE", root=root)


class TestSetFindingMaturity:
    def test_approve_finding(self, project):
        root, *_ = project
        f, _ = record_new_finding("Draft.", "structure", "cld", root=root)
        reviewer = HumanActor(name="Reviewer")
        updated, sha = set_finding_maturity(f.id, maturity="approved", reviewed_by=reviewer, root=root)
        assert updated.maturity == "approved"
        assert updated.reviewed_by is not None
        assert updated.reviewed_by.name == "Reviewer"
        assert updated.reviewed_at is not None

        # Verify persistence
        reloaded = get_finding(f.id, root=root)
        assert reloaded.maturity == "approved"

    def test_review_finding(self, project):
        root, *_ = project
        f, _ = record_new_finding("Read me.", "structure", "cld", root=root)
        updated, _ = set_finding_maturity(f.id, maturity="reviewed", root=root)
        assert updated.maturity == "reviewed"


class TestSupersede:
    def test_supersede_matching_findings(self, project):
        root, a, b, *_ = project
        record_new_finding("Old loops.", "structure", "cld", target_ids=[a.id, b.id], root=root)
        record_new_finding("Also old.", "structure", "cld", target_ids=[a.id, b.id], root=root)
        new, _ = record_new_finding("New loops.", "structure", "cld", target_ids=[a.id, b.id], root=root)

        superseded = supersede_matching(
            model_type="cld",
            category="structure",
            target_ids=[a.id, b.id],
            new_finding_id=new.id,
            root=root,
        )
        # All three findings have matching keys; supersede_matching includes
        # the new one in its return list, but only the prior two should
        # carry the new finding's id in their `supersedes` pointer.
        assert len(superseded) == 3
        prior = [f for f in list_findings(root=root) if f.id != new.id]
        assert all(new.id in f.supersedes for f in prior)

    def test_supersede_does_not_affect_different_category(self, project):
        root, a, *_ = project
        record_new_finding("Loops.", "structure", "cld", target_ids=[a.id], root=root)
        record_new_finding("Central.", "sensitivity", "cld", target_ids=[a.id], root=root)

        new_struct, _ = record_new_finding("New loops.", "structure", "cld", target_ids=[a.id], root=root)
        superseded = supersede_matching(
            model_type="cld",
            category="structure",
            target_ids=[a.id],
            new_finding_id=new_struct.id,
            root=root,
        )
        # supersede_matching returns matching findings in the same category;
        # sensitivity findings are unaffected.
        assert len(superseded) == 2

        sensitivity = list_findings(category="sensitivity", root=root)
        assert len(sensitivity) == 1
        assert sensitivity[0].maturity == "proposed"
        assert sensitivity[0].supersedes == []


# ── Staleness ───────────────────────────────────────────────────────────


class TestStaleness:
    def test_not_stale_when_commit_matches(self, project):
        root, a, *_ = project
        f, _ = record_new_finding("About A.", "structure", "cld", target_ids=[a.id], root=root)
        assert not check_staleness(f, root=root)

    def test_stale_when_target_deleted(self, project):
        root, a, b, c, *_ = project
        f, _ = record_new_finding("About C.", "structure", "cld", target_ids=[c.id], root=root)
        # Delete node C
        node_ops.remove_node(c.id, root=root)
        assert check_staleness(f, root=root)

    def test_not_stale_when_target_still_exists(self, project):
        root, a, b, *_ = project
        f, _ = record_new_finding("About A.", "structure", "cld", target_ids=[a.id], root=root)
        # Add another node (changes HEAD) but don't touch A
        node_ops.add_node("D", root=root)
        assert not check_staleness(f, root=root)

    def test_not_stale_without_target_ids(self, project):
        root, *_ = project
        f, _ = record_new_finding("Global.", "diagnostics", "cld", root=root)
        node_ops.add_node("D", root=root)
        assert not check_staleness(f, root=root)

    def test_stale_when_target_edge_reclassified_to_non_causal(self, project):
        """Phase 3 (AI interrogation): reclassify a causal edge to a
        non-causal kind invalidates findings that depend on it. Loop
        and centrality findings rest on the causal-edge subgraph; once
        the edge is governance/decision_rule/etc. the claim no longer
        holds."""
        root, a, b, c, edge_ab, _ = project
        f, _ = record_new_finding(
            "Edge AB anchors a loop.",
            "structure",
            "cld",
            target_ids=[edge_ab.id],
            root=root,
        )
        # Reclassify the target edge from causal → governance.
        edge_ops.retype_edge(edge_ab.id, "governance", root=root)
        assert check_staleness(f, root=root)

    def test_not_stale_when_edge_reclassified_among_non_causal(self, project):
        """A reclassify between non-causal kinds shouldn't trip
        staleness — only the causal → non-causal transition matters
        for loop / centrality findings."""
        root, a, b, c, edge_ab, _ = project
        # First retype to governance and record a finding from there.
        edge_ops.retype_edge(edge_ab.id, "governance", root=root)
        f, _ = record_new_finding(
            "Edge AB note.",
            "structure",
            "cld",
            target_ids=[edge_ab.id],
            root=root,
        )
        # Now retype again, but only between non-causal kinds.
        edge_ops.retype_edge(edge_ab.id, "decision_rule", root=root)
        assert not check_staleness(f, root=root)


# ── Finding generators ──────────────────────────────────────────────────


class TestFindingsFromLoops:
    def test_no_loops(self):
        findings = findings_from_loops([], model_commit="abc123")
        assert len(findings) == 1
        assert "No feedback loops" in findings[0].statement

    def test_with_loops(self):
        loops = [
            Loop(node_ids=("a", "b", "c"), edge_ids=("e1", "e2", "e3"), classification="R"),
            Loop(node_ids=("b", "c", "d"), edge_ids=("e2", "e4", "e5"), classification="B"),
            Loop(node_ids=("x", "y"), edge_ids=("e6", "e7"), classification="R"),
        ]
        findings = findings_from_loops(loops, model_commit="abc123")
        assert len(findings) == 1
        f = findings[0]
        assert f.category == "structure"
        assert f.model_type == "cld"
        assert f.maturity == "proposed"
        assert "3 feedback loops" in f.statement
        assert "2 reinforcing" in f.statement
        assert "1 balancing" in f.statement
        assert f.payload["loop_count"] == 3
        assert f.payload["reinforcing_count"] == 2
        assert f.payload["balancing_count"] == 1
        assert f.origin == "data-derived"


class TestFindingsFromCentrality:
    def test_basic_centrality(self):
        results = [
            CentralityResult(entity_id="a", degree_in=2, degree_out=3, degree_total=5, betweenness=0.42),
            CentralityResult(entity_id="b", degree_in=1, degree_out=1, degree_total=2, betweenness=0.10),
            CentralityResult(entity_id="c", degree_in=3, degree_out=0, degree_total=3, betweenness=0.25),
        ]
        findings = findings_from_centrality(
            results,
            entity_labels={"a": "Demand", "b": "Price", "c": "Quality"},
        )
        assert len(findings) == 1
        f = findings[0]
        assert f.category == "sensitivity"
        assert "Demand" in f.statement
        assert "0.42" in f.statement
        assert len(f.payload["ranking"]) == 3
        assert f.payload["ranking"][0]["entity_id"] == "a"

    def test_empty_results(self):
        assert findings_from_centrality([]) == []


class TestFindingsFromPropagation:
    def test_basic_propagation(self):
        effects = [
            PropagationEffect(entity_id="b", effect="+", paths_positive=2, paths_negative=0),
            PropagationEffect(entity_id="c", effect="-", paths_positive=0, paths_negative=1),
            PropagationEffect(entity_id="d", effect="ambiguous", paths_positive=1, paths_negative=1),
        ]
        findings = findings_from_propagation(
            "a",
            effects,
            source_label="Price",
        )
        assert len(findings) == 1
        f = findings[0]
        assert f.category == "inference"
        assert f.model_type == "cld"
        assert "Price" in f.statement
        assert "1 increase" in f.statement
        assert "1 decrease" in f.statement
        assert "1 have ambiguous" in f.statement

    def test_empty_effects(self):
        assert findings_from_propagation("a", []) == []


class TestFindingsFromDSeparation:
    def test_d_separated(self):
        findings = findings_from_dseparation(
            ["a"],
            ["b"],
            ["c"],
            True,
            entity_labels={"a": "X", "b": "Y", "c": "Z"},
        )
        assert len(findings) == 1
        f = findings[0]
        assert f.category == "inference"
        assert f.model_type == "dag"
        assert "independent" in f.statement
        assert "X" in f.statement and "Y" in f.statement and "Z" in f.statement

    def test_not_d_separated(self):
        findings = findings_from_dseparation(["a"], ["b"], [], False)
        assert "dependent" in findings[0].statement

    def test_marginal_independence(self):
        findings = findings_from_dseparation(["a"], ["b"], [], True)
        assert "marginally independent" in findings[0].statement


class TestFindingsFromAdjustmentSets:
    def test_with_sets(self):
        findings = findings_from_adjustment_sets(
            "a",
            "b",
            [["c"], ["d", "e"]],
            entity_labels={"a": "Treatment", "b": "Outcome", "c": "Age", "d": "Sex", "e": "BMI"},
        )
        assert len(findings) == 1
        f = findings[0]
        assert "2 valid adjustment set" in f.statement
        assert "Treatment" in f.statement
        assert "Outcome" in f.statement
        assert f.payload["count"] == 2

    def test_no_sets(self):
        findings = findings_from_adjustment_sets("a", "b", [])
        assert "No valid adjustment set" in findings[0].statement

    def test_empty_set(self):
        findings = findings_from_adjustment_sets("a", "b", [[]])
        assert "empty adjustment set" in findings[0].statement


class TestFindingsFromFCMInference:
    def test_converged(self):
        result = FCMInferenceResult(
            activations={"a": 0.8, "b": 0.3, "c": 0.6},
            converged=True,
            iterations=15,
            history=(),
        )
        findings = findings_from_fcm_inference(
            result,
            entity_labels={"a": "Demand", "b": "Price", "c": "Quality"},
        )
        assert len(findings) == 1
        f = findings[0]
        assert f.category == "dynamics"
        assert f.model_type == "fcm"
        assert "converged after 15 iterations" in f.statement
        assert "Demand" in f.statement
        assert f.payload["converged"] is True

    def test_not_converged(self):
        result = FCMInferenceResult(
            activations={"a": 0.5},
            converged=False,
            iterations=100,
            history=(),
        )
        findings = findings_from_fcm_inference(result)
        assert "did not converge" in findings[0].statement

    def test_scenario_label(self):
        result = FCMInferenceResult(
            activations={"a": 0.9},
            converged=True,
            iterations=5,
            history=(),
        )
        findings = findings_from_fcm_inference(result, scenario_label="High demand")
        assert "Scenario 'High demand'" in findings[0].statement
