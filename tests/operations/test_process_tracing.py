"""Process tracing on theory-of-change links: the update, Van Evera's tests, pathway confidence."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations import process_tracing as pt
from latris.operations import toc
from latris.operations.init import init_project

# ── kernel ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("p_true", "p_false", "kind"),
    [(0.9, 0.1, "doubly decisive"), (0.9, 0.6, "hoop"), (0.3, 0.05, "smoking gun"), (0.6, 0.4, "straw in the wind")],
)
def test_van_evera_classification(p_true, p_false, kind):
    assert pt.classify(p_true, p_false) == kind


def test_hoop_failure_sinks_smoking_gun_pass_lifts():
    # Hoop: passing helps little, failing hurts a lot.
    assert pt.posterior(0.5, [pt.likelihood_ratio(0.95, 0.6, True)]) == pytest.approx(0.95 / 1.55)
    assert pt.posterior(0.5, [pt.likelihood_ratio(0.95, 0.6, False)]) == pytest.approx(0.05 / 0.45)
    # Smoking gun: passing lifts a lot, failing hurts little.
    assert pt.posterior(0.5, [pt.likelihood_ratio(0.3, 0.03, True)]) == pytest.approx(10 / 11)
    assert pt.posterior(0.5, [pt.likelihood_ratio(0.3, 0.03, False)]) > 0.4


def test_posterior_is_order_independent_and_matches_bayes():
    r = [pt.likelihood_ratio(0.8, 0.3, True), pt.likelihood_ratio(0.6, 0.2, False)]
    p = pt.posterior(0.3, r)
    assert p == pytest.approx(pt.posterior(0.3, r[::-1]))
    # Direct Bayes: P(H|E1, not E2)
    num = 0.3 * 0.8 * 0.4
    den = num + 0.7 * 0.3 * 0.8
    assert p == pytest.approx(num / den)


# ── on a project ────────────────────────────────────────────────────


@pytest.fixture
def project(tmp_path: Path, git_identity, monkeypatch):
    root = tmp_path / "pt"
    init_project(root, statement="Does mentoring raise attainment?")
    labels = ["Mentoring", "Engagement", "Attainment"]
    for label in labels:
        node_ops.add_node(label, kind="variable", root=root)
    edge_ops.add_edge("Mentoring", "Engagement", kind="causal", root=root)
    edge_ops.add_edge("Engagement", "Attainment", kind="causal", root=root)
    for label, level in zip(labels, ["activity", "short_term_outcome", "impact"], strict=True):
        toc.set_level(label, level, root=root)
    monkeypatch.chdir(root)
    return root


def test_trace_updates_links_and_pathway(project):
    root = project
    pt.set_prior("Mentoring -> Engagement", 0.6, root=root)
    pt.set_test("Mentoring -> Engagement", "attendance rises", p_if_true=0.9, p_if_false=0.3, found=True, root=root)
    pt.set_test("Engagement -> Attainment", "grades track engagement", p_if_true=0.7, p_if_false=0.2, root=root)
    p, sha = pt.trace(record=False, root=root)
    assert sha is None
    first = next(lk for lk in p["links"] if lk["link"] == "Mentoring → Engagement")
    assert first["posterior"] == pytest.approx(pt.posterior(0.6, [3.0]))
    assert first["tests"][0]["type"] == "hoop"
    second = next(lk for lk in p["links"] if lk["link"] == "Engagement → Attainment")
    assert second["posterior"] == 0.5 and second["pending"][0]["if_found"] > 0.7
    assert p["untested"] == ["Engagement → Attainment"]
    (pw,) = p["pathways"]
    assert pw["confidence"] == pytest.approx(first["posterior"] * 0.5)
    assert pw["weakest"] == "Engagement → Attainment"
    assert p["next_test"]["test"] == "grades track engagement"
    assert "'attendance rises' on Mentoring → Engagement" in p["rests_on_unverified"]


def test_update_test_result_and_record(project):
    root = project
    pt.set_test("Engagement -> Attainment", "g", p_if_true=0.7, p_if_false=0.2, root=root)
    pt.set_test("Engagement -> Attainment", "g", found=False, root=root)
    (t,) = pt.get_tests(root=root).entries
    assert (t.p_if_true, t.found) == (0.7, False)
    p, sha = pt.trace(root=root)
    assert sha and p["run_id"]
    from latris.operations.analysis_results import report_results

    assert any(r.run.result_kind == "toc-process-trace" for r in report_results(root=root))
    pt.remove_test("Engagement -> Attainment", "g", root=root)
    assert not pt.get_tests(root=root).entries


def test_refusals(project):
    root = project
    with pytest.raises(ValueError, match="both probabilities"):
        pt.set_test("Mentoring -> Engagement", "x", p_if_true=0.5, root=root)
    with pytest.raises(ValueError, match="a link"):
        pt.set_prior("Mentoring", 0.5, root=root)
    node_ops.add_node("Funding", kind="variable", root=root)
    edge_ops.add_edge("Funding", "Mentoring", kind="causal", root=root)
    with pytest.raises(ValueError, match="give both ends a level"):
        pt.set_prior("Funding -> Mentoring", 0.5, root=root)


# ── surfaces ────────────────────────────────────────────────────────


SPEC = """
model_type: theory_of_change
outcome: Attainment
factors:
  - label: Mentoring
  - label: Engagement
  - label: Attainment
links:
  - {from: Mentoring, to: Engagement}
  - {from: Engagement, to: Attainment}
toc:
  levels:
    - {node: Mentoring, level: activity}
    - {node: Engagement, level: short_term_outcome}
  priors:
    - {link: Mentoring -> Engagement, prior: 0.6}
  tests:
    - {link: Mentoring -> Engagement, name: attendance rises, p_if_true: 0.9, p_if_false: 0.3, found: true}
    - {link: Engagement -> Attainment, name: grades track engagement, p_if_true: 0.7, p_if_false: 0.2}
analyses:
  - kind: toc_trace
"""


@pytest.fixture
def built(tmp_path: Path, git_identity, monkeypatch):
    from latris.operations.build import build_from_spec, load_spec

    root = tmp_path / "built"
    init_project(root, statement="Does mentoring raise attainment?")
    monkeypatch.chdir(root)
    return root, build_from_spec(load_spec(SPEC), root=root)


def test_build_spec_report_claims_and_share_link(built):
    from latris.exporters.markdown import render
    from latris.operations.interpret import extract_claims
    from latris.operations.share_link import export_spec
    from latris.repo.layout import ProjectPaths

    root, result = built
    assert result.analyses and not result.notes
    assert len(pt.get_tests(root=root).entries) == 2
    md = render(ProjectPaths(root), model_type="theory_of_change", ai=False)
    assert "Theory of change: process tracing" in md and "Bayesian process tracing" in md
    assert "grades track engagement" in md
    answer = extract_claims("answer_to_question", "theory_of_change", root=root)
    assert any(c.startswith("Process tracing puts the pathway") for c in answer)
    _, spec = export_spec(model_type="theory_of_change", root=root)
    assert [p.link for p in spec.toc.priors] == ["Mentoring -> Engagement"]
    assert {t.name for t in spec.toc.tests} == {"attendance rises", "grades track engagement"}
    assert "toc_trace" in [a.kind for a in spec.analyses]


def test_spec_rejects_bad_links(tmp_path, git_identity):
    from latris.operations.build import build_from_spec, load_spec

    root = tmp_path / "bad"
    init_project(root, statement="Q?")
    bad = SPEC.replace("{link: Mentoring -> Engagement, prior: 0.6}", "{link: Nowhere -> Engagement, prior: 0.6}")
    bad = bad.replace("{link: Engagement -> Attainment,", "{link: Engagement,")
    with pytest.raises(ValueError) as exc:
        build_from_spec(load_spec(bad), root=root)
    assert "no factor named 'Nowhere'" in str(exc.value)
    assert "isn't a link" in str(exc.value)


def test_cli_and_routes(project):
    from fastapi.testclient import TestClient
    from typer.testing import CliRunner

    from latris.cli.app import app
    from latris.server.app import create_app

    runner = CliRunner()
    r = runner.invoke(app, ["toc", "test", "Mentoring -> Engagement", "records", "--if-true", "0.9",
                            "--if-false", "0.1", "--found"])
    assert r.exit_code == 0, r.output
    assert "doubly decisive" in r.output
    r = runner.invoke(app, ["toc", "prior", "Engagement -> Attainment", "0.4"])
    assert r.exit_code == 0, r.output
    r = runner.invoke(app, ["toc", "trace", "--no-record"])
    assert r.exit_code == 0 and "Pathways" in r.output, r.output

    client = TestClient(create_app(project_root=project))
    r = client.post("/api/toc/test", json={"link": "Engagement -> Attainment", "name": "x", "p_if_true": 0.5})
    assert r.status_code == 422
    r = client.post("/api/toc/test", json={"link": "Engagement -> Attainment", "name": "x", "p_if_true": 0.5,
                                           "p_if_false": 0.1, "found": False})
    assert r.status_code == 200 and r.json()["result"]["type"] == "smoking gun"
    r = client.post("/api/toc/test", json={"link": "Engagement -> Attainment", "name": "x", "clear_found": True})
    assert r.json()["result"]["found"] is None
    assert len(client.get("/api/toc/trace").json()["tests"]) == 2
    r = client.post("/api/toc/trace", json={"record": True})
    assert r.json()["commit_sha"] and r.json()["result"]["pathways"]
