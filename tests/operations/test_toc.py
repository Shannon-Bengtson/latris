"""Theory of Change: levels, structure checks, pathway and evidence analysis."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations import toc
from latris.operations.analysis_results import report_results
from latris.operations.evidence import add_evidence
from latris.operations.init import init_project
from latris.operations.provenance import add_assumption
from latris.operations.readiness import assess_readiness
from latris.operations.references import add_reference


def _e(eid: str, a: str, b: str):
    return SimpleNamespace(id=eid, from_id=a, to_id=b)


def _ev(target: str, *, against: bool = False, checked: bool = False):
    return SimpleNamespace(target_id=target, is_against=against, support_verdict="supports" if checked else "unverified")


# ── kernel ──────────────────────────────────────────────────────────


CHAIN = {
    "train": "activity",
    "skills": "output",
    "jobs": "short_term_outcome",
    "income": "impact",
}
EDGES = [_e("e1", "train", "skills"), _e("e2", "skills", "jobs"), _e("e3", "jobs", "income")]


def test_single_pathway_weakest_link():
    res = toc.analyse(
        list(CHAIN), EDGES, CHAIN,
        evidence=[_ev("e1", checked=True), _ev("e2")],
        assumption_targets=["e1", None],
    )
    assert res.problems == []
    assert len(res.pathways) == 1
    pw = res.pathways[0]
    assert pw.node_ids == ["train", "skills", "jobs", "income"]
    assert pw.status == "untested"  # e3 has no source
    assert pw.weak_edge_ids == ["e2", "e3"]
    assert [res.link(x).status for x in ("e1", "e2", "e3")] == ["checked", "cited", "untested"]
    assert res.link("e1").assumptions == 1
    assert all(lk.on_pathway for lk in res.links)


def test_contested_beats_checked():
    res = toc.analyse(list(CHAIN), EDGES, CHAIN, evidence=[_ev("e1", checked=True), _ev("e1", against=True)])
    assert res.link("e1").status == "contested"
    assert res.pathways[0].status == "contested"


def test_missing_level_backward_link_and_dead_end():
    levels = {"train": "activity", "skills": "output", "income": "impact", "stray": "short_term_outcome"}
    edges = [_e("e1", "train", "skills"), _e("e2", "skills", "income"), _e("e3", "income", "skills"),
             _e("e4", "skills", "stray")]
    res = toc.analyse(["train", "skills", "income", "stray", "unset"], edges, levels)
    kinds = {(p.gap_type, p.target_id) for p in res.problems}
    assert ("toc_no_level", "unset") in kinds
    assert ("toc_backward_link", "e3") in kinds
    assert ("toc_dead_end", "stray") in kinds


def test_no_activity_or_impact_and_unreached_impact():
    res = toc.analyse(["a"], [], {"a": "output"})
    kinds = {p.gap_type for p in res.problems}
    assert {"toc_no_activity", "toc_no_impact"} <= kinds

    res = toc.analyse(["act", "imp", "imp2", "out"], [_e("e1", "act", "imp"), _e("e2", "out", "imp2")],
                      {"act": "activity", "imp": "impact", "imp2": "impact", "out": "output"})
    assert [p.target_id for p in res.problems if p.gap_type == "toc_unreached_impact"] == ["imp2"]


def test_leap_is_flagged_not_a_problem():
    res = toc.analyse(["act", "imp"], [_e("e1", "act", "imp")], {"act": "activity", "imp": "impact"})
    assert res.link("e1").leap is True
    assert res.problems == []


def test_branching_pathways_enumerated():
    levels = {"a": "activity", "o1": "output", "o2": "output", "i": "impact"}
    edges = [_e("e1", "a", "o1"), _e("e2", "a", "o2"), _e("e3", "o1", "i"), _e("e4", "o2", "i")]
    res = toc.analyse(list(levels), edges, levels)
    assert sorted(tuple(p.node_ids) for p in res.pathways) == [("a", "o1", "i"), ("a", "o2", "i")]


def test_pathway_cap(monkeypatch):
    monkeypatch.setattr(toc, "MAX_PATHWAYS", 1)
    levels = {"a": "activity", "o1": "output", "o2": "output", "i": "impact"}
    edges = [_e("e1", "a", "o1"), _e("e2", "a", "o2"), _e("e3", "o1", "i"), _e("e4", "o2", "i")]
    res = toc.analyse(list(levels), edges, levels)
    assert len(res.pathways) == 1 and res.pathways_truncated


def test_full_analysis_on_a_chain_with_a_loop_and_a_stray_link():
    """Every field of the analysis: links outside the chain are dropped, evidence for them is ignored, a loop
    doesn't repeat a pathway, and the counts, leaps and confidence carry through."""
    levels = {"a": "activity", "o": "output", "s": "short_term_outcome", "i": "impact"}
    edges = [_e("e1", "a", "o"), _e("e2", "o", "s"), _e("e3", "s", "o"), _e("e4", "s", "i"),
             _e("e5", "o", "i"), _e("x", "a", "elsewhere")]
    res = toc.analyse(list(levels), edges, levels, evidence=[_ev("x"), _ev("e4", checked=True), _ev("e5")],
                      assumption_targets=["e4", "e4", "gone"], confidence={"e1": "high"})
    assert [lk.edge_id for lk in res.links] == ["e1", "e2", "e3", "e4", "e5"]
    assert res.counts == {"input": 0, "activity": 1, "output": 1, "short_term_outcome": 1, "long_term_outcome": 0,
                          "impact": 1}
    assert [(p.gap_type, p.target_id) for p in res.problems] == [("toc_backward_link", "e3")]
    assert sorted(p.node_ids for p in res.pathways) == [["a", "o", "i"], ["a", "o", "s", "i"]]
    assert {tuple(p.edge_ids): p.status for p in res.pathways} == {("e1", "e5"): "untested",
                                                                   ("e1", "e2", "e4"): "untested"}
    lk = {x.edge_id: x for x in res.links}
    assert (lk["e1"].confidence, lk["e4"].assumptions, lk["e4"].sources_for_checked, lk["e5"].sources_for) == (
        "high", 2, 1, 1)
    assert not lk["e3"].on_pathway and lk["e5"].leap and not lk["e1"].leap
    assert res.dead_ends == [] and res.unreached_impacts == [] and not res.pathways_truncated


# ── project ─────────────────────────────────────────────────────────


@pytest.fixture
def project(tmp_path: Path, git_identity, monkeypatch):
    root = tmp_path / "toc"
    init_project(root, statement="Does the training programme raise participants' income?")
    ids = {}
    for label in ["Training sessions", "Trained participants", "Job placements", "Household income"]:
        node, _ = node_ops.add_node(label, kind="variable", root=root)
        ids[label] = node.id
    labels = list(ids)
    for a, b in zip(labels, labels[1:], strict=False):
        edge_ops.add_edge(ids[a], ids[b], kind="causal", root=root)
    monkeypatch.chdir(root)
    return root, ids


def _level_all(root, ids):
    for label, level in zip(ids, ["activity", "output", "short_term_outcome", "impact"], strict=True):
        toc.set_level(label, level, root=root)


def test_readiness_needs_levels_then_passes(project):
    root, ids = project
    r = assess_readiness("theory_of_change", root=root)
    assert not r.can_switch
    assert {g.gap_type for g in r.gaps} >= {"toc_no_level"}
    _level_all(root, ids)
    r = assess_readiness("theory_of_change", root=root)
    assert r.can_switch, r.gaps


def test_bad_level_and_outcome_role_refused(project):
    root, _ = project
    with pytest.raises(ValueError, match="not a theory-of-change level"):
        toc.set_level("Training sessions", "goal", root=root)
    from latris.operations.view_roles import set_role

    with pytest.raises(ValueError, match="impact"):
        set_role("Household income", "theory_of_change", "outcome", root=root)


def test_check_records_result_and_goes_stale_on_new_evidence(project):
    root, ids = project
    _level_all(root, ids)
    payload, sha = toc.check(root=root)
    assert sha
    assert payload["pathways"][0]["path"] == list(ids)
    assert payload["pathways"][0]["status"] == "untested"
    results = report_results(model_types=["theory_of_change"], root=root)
    assert [r.run.result_kind for r in results] == ["toc-pathways"]
    assert not results[0].stale

    add_reference("card2018", "What works? A meta analysis of active labour market evaluations", year=2018,
                  root=root)
    add_evidence("Training sessions -> Trained participants", "description", "card2018", root=root)
    assert report_results(model_types=["theory_of_change"], root=root)[0].stale

    add_assumption("Participants attend most sessions.", target_id=None, root=root)
    payload, _ = toc.check(record=False, root=root)
    first = next(lk for lk in payload["links"] if lk["from"] == "Training sessions")
    assert first["status"] == "cited" and first["sources_for"] == 1
    assert "pathway(s) from activity to impact" in toc.describe(payload)


# ── surfaces ────────────────────────────────────────────────────────


SPEC = """
model_type: theory_of_change
outcome: Household income
factors:
  - label: Training sessions
  - label: Trained participants
  - label: Job placements
  - label: Household income
links:
  - {from: Training sessions, to: Trained participants, sources: [card2018]}
  - {from: Trained participants, to: Job placements}
  - {from: Job placements, to: Household income}
sources:
  - {key: card2018, title: What works? A meta analysis of active labour market evaluations, year: 2018}
assumptions:
  - {text: Placements pay more than participants earned before., target: "Job placements -> Household income"}
toc:
  levels:
    - {node: Training sessions, level: activity}
    - {node: Trained participants, level: output}
    - {node: Job placements, level: short_term_outcome}
analyses:
  - kind: toc_check
"""


@pytest.fixture
def built(tmp_path: Path, git_identity, monkeypatch):
    from latris.operations.build import build_from_spec, load_spec

    root = tmp_path / "built"
    init_project(root, statement="Does the training programme raise participants' income?")
    monkeypatch.chdir(root)
    result = build_from_spec(load_spec(SPEC), root=root)
    return root, result


def test_build_spec_sets_levels_outcome_as_impact_and_runs_check(built):
    root, result = built
    assert result.analyses and not result.notes
    levels = toc.get_levels(root=root)
    assert sorted(levels.values()) == sorted(["activity", "output", "short_term_outcome", "impact"])
    assert assess_readiness("theory_of_change", root=root).can_switch
    payload, _ = toc.check(record=False, root=root)
    last = next(lk for lk in payload["links"] if lk["to"] == "Household income")
    assert last["assumptions"] == 1
    assert next(lk for lk in payload["links"] if lk["from"] == "Training sessions")["status"] == "cited"


def test_build_spec_rejects_unknown_level_node_and_conflicting_outcome(tmp_path, git_identity):
    from latris.operations.build import build_from_spec, load_spec

    root = tmp_path / "bad"
    init_project(root, statement="Q?")
    bad = SPEC.replace("- {node: Job placements, level: short_term_outcome}",
                       "- {node: Nowhere, level: output}\n    - {node: Household income, level: output}")
    with pytest.raises(ValueError) as exc:
        build_from_spec(load_spec(bad), root=root)
    assert "no factor named 'Nowhere'" in str(exc.value)
    assert "its level is impact" in str(exc.value)


def test_share_link_carries_levels_and_check(built):
    from latris.operations.share_link import export_spec

    root, _ = built
    _, spec = export_spec(model_type="theory_of_change", root=root)
    assert spec.toc is not None
    assert [lv.level for lv in spec.toc.levels] == ["activity", "output", "short_term_outcome", "impact"]
    assert [a.kind for a in spec.analyses] == ["toc_check"]


def test_report_renders_pathways(built):
    from latris.exporters.markdown import render
    from latris.repo.layout import ProjectPaths

    root, _ = built
    md = render(ProjectPaths(root), model_type="theory_of_change", ai=False)
    assert "Theory of change: pathways and their evidence" in md
    assert "Training sessions → Trained participants → Job placements → Household income" in md
    assert "Theory of change as a results chain" in md  # methods and foundations


def test_claims_name_links_to_test(built):
    from latris.operations.interpret import extract_claims

    root, _ = built
    answer = extract_claims("answer_to_question", "theory_of_change", root=root)
    assert any("pathway(s) from activity to impact" in c for c in answer)
    impl = extract_claims("implications", "theory_of_change", root=root)
    assert impl[0].startswith("Links to test first")
    assert not any("intervention points" in c for c in impl)
    gaps = extract_claims("evidence_gaps", "theory_of_change", root=root)
    assert any("Links on a pathway with no source" in c for c in gaps)


def test_server_routes(built):
    from fastapi.testclient import TestClient

    from latris.server.app import create_app

    root, _ = built
    client = TestClient(create_app(project_root=root))
    body = client.get("/api/toc/levels").json()
    assert body["count"] == 4 and body["order"][0] == "input"
    r = client.post("/api/toc/level", json={"node": "Training sessions", "level": "nonsense"})
    assert r.status_code == 422
    r = client.post("/api/toc/level", json={"node": "Training sessions", "level": "activity"})
    assert r.status_code == 200 and r.json()["commit_sha"]
    r = client.post("/api/toc/check", json={"record": False})
    assert r.json()["commit_sha"] is None and len(r.json()["result"]["pathways"]) == 1


def test_assumption_target_resolves_link_names(project):
    root, ids = project
    entry, _ = add_assumption("Trained people apply for jobs.", target_id="Trained participants -> Job placements",
                              root=root)
    assert entry.target_id.startswith("edge_")
    with pytest.raises(ValueError):
        add_assumption("x", target_id="No such factor", root=root)


def test_cli_level_levels_check(project):
    from typer.testing import CliRunner

    from latris.cli.app import app

    root, ids = project
    runner = CliRunner()
    for label, level in zip(ids, ["activity", "output", "short_term_outcome", "impact"], strict=True):
        assert runner.invoke(app, ["toc", "level", label, level]).exit_code == 0
    out = runner.invoke(app, ["toc", "levels"])
    assert out.exit_code == 0 and "Short-term outcome" in out.output
    out = runner.invoke(app, ["toc", "check"])
    assert out.exit_code == 0, out.output
    assert "1 pathway(s) from activity to impact" in out.output
    out = runner.invoke(app, ["toc", "level", "Job placements", "goal"])
    assert out.exit_code != 0


def test_mermaid_groups_by_level(built):
    from latris.exporters.mermaid import render
    from latris.repo.layout import ProjectPaths

    root, _ = built
    src = render(ProjectPaths(root), model_type="theory_of_change")
    assert 'subgraph L1["Activity"]' in src and 'subgraph L5["Impact"]' in src
    assert src.index("Activity") < src.index("Output") < src.index("Impact")
    assert "subgraph" not in render(ProjectPaths(root), model_type="cld")


def test_links_to_test_first_rank_untested_before_cited(built):
    from latris.operations.interpret import extract_claims

    root, _ = built
    # Training → Trained is cited; the other two are untested; one pathway, so all tie on count.
    impl = extract_claims("implications", "theory_of_change", root=root)
    assert "cited" in impl[-1] and "untested" in impl[1]
