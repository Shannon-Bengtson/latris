"""The report surface for plugin formalisms: chart markers and aggregate diagrams.

``latris-chart`` markers come from each formalism's ``ResultKind.charts`` hook
(legacy sd/bn kinds keep the hardcoded mapping until those types migrate). The
aggregate report (no ``--model-type``) composes one diagram per formalism in use.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from latris.exporters import markdown
from latris.operations import mcda
from latris.operations.init import init_project
from latris.operations.nodes import add_node
from latris.repo.layout import ProjectPaths

SCORES = {
    "Site A": {"Cost": 60, "Travel time": 30},
    "Site B": {"Cost": 40, "Travel time": 15},
}


@pytest.fixture
def mcda_root(tmp_path: Path, git_identity, monkeypatch):
    root = tmp_path / "site"
    init_project(root, statement="Which site should the new hospital go on?")
    for label in [*SCORES, "Cost", "Travel time"]:
        add_node(label, root=root)
    for o in SCORES:
        mcda.set_element(o, "option", root=root)
    for c, w, d in (("Cost", 60, "lower"), ("Travel time", 40, "lower")):
        mcda.set_element(c, "criterion", root=root)
        mcda.set_criterion(c, weight=w, direction=d, root=root)
    for o, row in SCORES.items():
        for c, x in row.items():
            mcda.set_score(o, c, x, root=root)
    monkeypatch.chdir(root)
    return root


def _chart_kinds(md: str) -> list[str]:
    fences = [block.split("\n", 1)[1].split("\n```")[0] for block in md.split("```latris-chart")[1:]]
    return [json.loads(f)["chart"] for f in fences]


def test_plugin_charts_hook_emits_markers(mcda_root):
    mcda.record(mcda.analyse(root=mcda_root), root=mcda_root)
    paths = ProjectPaths(mcda_root)

    plain = markdown.render(paths, model_type="mcda", ai=False)
    assert "latris-chart" not in plain  # plain Markdown stays clean

    md = markdown.render(paths, model_type="mcda", ai=False, chart_markers=True)
    kinds = _chart_kinds(md)
    assert "mcda-contributions" in kinds and "mcda-swing" in kinds
    assert all("-" in k for k in kinds)  # namespaced per formalism


def test_aggregate_report_composes_formalism_diagrams(mcda_root):
    md = markdown.render(ProjectPaths(mcda_root), ai=False)
    assert md.count("## Diagram") == 1
    assert "### Multi-Criteria Decision Analysis" in md
    assert "flowchart" in md
    # No edges anywhere: nothing falls outside a formalism's view, so no whole-model sketch.
    assert "### Whole model" not in md


def test_aggregate_report_keeps_whole_model_for_unmapped_edges(mcda_root):
    from latris.operations.edges import add_edge

    add_edge("Cost", "Travel time", root=mcda_root)  # no view claims this edge
    md = markdown.render(ProjectPaths(mcda_root), ai=False)
    assert "### Multi-Criteria Decision Analysis" in md
    assert "### Whole model" in md


def test_scoped_report_diagram_unchanged(mcda_root):
    md = markdown.render(ProjectPaths(mcda_root), model_type="mcda", ai=False)
    assert "## Diagram" in md and "### Multi-Criteria Decision Analysis" not in md


def test_empty_project_has_no_diagram(tmp_path: Path, git_identity, monkeypatch):
    root = tmp_path / "empty"
    init_project(root, statement="Q?")
    monkeypatch.chdir(root)
    md = markdown.render(ProjectPaths(root), ai=False)
    assert "## Diagram" not in md


def test_every_plugin_result_kind_with_charts_is_namespaced():
    from latris.operations import formalisms

    for r in formalisms.result_kinds():
        if r.charts is None:
            continue
        for chart, _ in _safe_charts(r):
            assert chart.startswith(("mcda-", "ach-", "dt-", "markov-", "impact-", "estimate-",
                                     "trace-", "ft-", "et-", "bt-", "mc-",
                                     # BN migrated with its chart kinds unchanged — they are the
                                     # app's existing renderer contract ("posterior" predates the
                                     # namespacing rule and stays so the app keeps working).
                                     "bn-", "posterior")), chart


def _safe_charts(r) -> list[tuple[str, dict]]:
    """Call a charts hook with the smallest payload its guard allows ([] if it needs data)."""
    for payload in ({}, {"rank_reversal": [], "options": [], "matrix": [], "incremental": [],
                         "links": [], "importance": [], "quantified": False, "outputs": [],
                         "method": "did", "series": []}):
        try:
            return r.charts(payload)
        except (KeyError, TypeError, IndexError):
            continue
    return []
