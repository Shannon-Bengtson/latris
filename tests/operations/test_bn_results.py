"""Soft evidence, explanations and BN Monte Carlo as recorded results: report, claims, link round trip."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from latris.exporters import markdown
from latris.operations import analysis_results as ar
from latris.operations import bn as bn_ops
from latris.operations import share_link, uncertainty
from latris.operations.build import build_from_spec
from latris.operations.init import init_project
from latris.operations.interpret import extract_claims
from latris.operations.project import update_selected_models
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model
from latris.schema import Substrate

pytest.importorskip("pgmpy")

FLOOD = {
    "Heavy Rain": ([], [0.3, 0.7]),
    "Levee Holds": ([], [0.9, 0.1]),
    "Flood": (["Heavy Rain", "Levee Holds"], [0.2, 0.8, 0.95, 0.05, 0.02, 0.98, 0.3, 0.7]),
    "Road Closed": (["Flood"], [0.9, 0.1, 0.05, 0.95]),
}


def _flood(root: Path) -> Path:
    from latris.operations import edges as edge_ops
    from latris.operations import nodes as node_ops

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


@pytest.fixture
def flood(tmp_path: Path, git_identity) -> Path:
    return _flood(tmp_path / "flood")


def _record_all(root: Path) -> None:
    bn_ops.record_query(bn_ops.infer(query=["Flood"], soft={"Heavy Rain": {"yes": 0.8}}, root=root), root=root)
    bn_ops.record_explanation(bn_ops.explain(evidence={"Road Closed": "yes"}, root=root), root=root)
    uncertainty.set_table_uncertainty("Flood", 10, reason="One engineer's estimate", origin="ai-proposed", root=root)
    bn_ops.record_monte_carlo(
        bn_ops.run_monte_carlo("Flood", evidence={"Heavy Rain": "yes"}, runs=120, seed=5, root=root), root=root
    )


def test_table_uncertainty_is_checked(flood: Path) -> None:
    with pytest.raises(ValueError, match="positive"):
        uncertainty.set_table_uncertainty("Flood", 0, root=flood)
    with pytest.raises(ValueError, match="not a parent"):
        uncertainty.set_table_uncertainty("Flood", 5, row="Road Closed=yes", root=flood)
    with pytest.raises(ValueError, match="missing Levee Holds"):
        uncertainty.set_table_uncertainty("Flood", 5, row="Heavy Rain=yes", root=flood)
    entry, _ = uncertainty.set_table_uncertainty("Flood", 5, row="Heavy Rain=yes,Levee Holds=no", root=flood)
    assert entry.parameter_cell_id.startswith("bn:cpt:") and entry.params == {"n": 5.0}


def test_reports_and_claims_show_the_new_results(flood: Path) -> None:
    _record_all(flood)
    md = markdown.render(ProjectPaths(flood), pack="client", ai=False, chart_markers=True)
    for heading in ("### Probabilities", "### Most likely explanation", "### How sure the probability is"):
        assert heading in md
    assert "Heavy Rain = yes (80% sure)" in md
    assert "worth about 10 observations — One engineer's estimate (AI-proposed, not yet reviewed)" in md
    assert '"chart": "bn-interval"' in md

    answer = extract_claims("answer_to_question", "bn", root=flood)
    assert any(c.startswith("Given Road Closed = yes, the most likely explanation is") for c in answer)
    sens = extract_claims("sensitivity", "bn", root=flood)
    assert any("in 95% of 120 draws of the uncertain probability tables" in c for c in sens)
    questions = extract_claims("open_questions", "bn", root=flood)
    assert any(c.startswith("How sure are we that Heavy Rain is yes?") for c in questions)
    assert any(c.startswith("How well is Flood's probability table known?") for c in questions)

    shown = {r.run.result_kind for r in ar.report_results(root=flood)}
    assert shown == {"bn-query", "bn-explanation", "bn-monte-carlo"}


def _comparable(root: Path) -> list:
    sub = load_model(Substrate, ProjectPaths(root).conceptual_yaml)
    names = {e.id: e.label for e in sub.entities}
    out = []
    for r in ar.report_results(root=root):
        text = json.dumps({k: v for k, v in r.payload.items() if k != "seconds"}, sort_keys=True)
        for i, label in names.items():
            text = text.replace(i, label)
        out.append((r.run.result_kind, json.loads(text)))
    return out


def test_the_new_analyses_travel_in_a_link(flood: Path, tmp_path: Path) -> None:
    _record_all(flood)
    link = share_link.make_link(root=flood)
    spec = share_link.decode_payload(link.url.split("#", 1)[1]).spec
    assert [a.kind for a in spec.analyses] == ["bn_query", "bn_explain", "bn_monte_carlo"]
    assert spec.bn and spec.bn.uncertainty[0].n == 10
    copy = tmp_path / "copy"
    init_project(copy, statement="How likely is a flood?")
    update_selected_models(["bn"], root=copy)
    result = build_from_spec(spec, verified_by="ai", root=copy)
    assert not result.notes and len(result.analyses) == 3
    assert _comparable(copy) == _comparable(flood)
