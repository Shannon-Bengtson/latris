"""A link carries dataset-based results as the sender's, and every model type the project uses."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.exporters.markdown import render
from latris.operations.analysis_results import get_result, report_results
from latris.operations.build import build_from_spec
from latris.operations.init import init_project
from latris.operations.project import update_selected_models
from latris.operations.share_link import decode_payload, export_spec, make_link
from latris.repo.layout import ProjectPaths
from latris.testing import build_example


def _open(link_url: str, dest: Path) -> Path:
    """What opening a link does: a new project, every model type the link names, the spec built."""
    payload = decode_payload(link_url.split("#", 1)[1])
    init_project(dest, statement=payload.question)
    update_selected_models(payload.model_types or [payload.model_type], root=dest)
    build_from_spec(payload.spec, verified_by="ai", root=dest)
    return dest


@pytest.mark.parametrize("name", ["effect_estimate", "toc_impact"])
def test_dataset_results_travel_as_the_senders(name, tmp_path, git_identity):
    src = build_example(name, tmp_path / "src")
    _, spec = export_spec(root=src)
    assert spec.carried_results and not any(a.kind in ("dag_estimate", "toc_impact") for a in spec.analyses)
    assert all("node_" not in str(c.payload) for c in spec.carried_results)  # labels, not the sender's ids

    dest = _open(make_link(root=src).url, tmp_path / "dest")
    sent = sorted((r.run.result_kind, r.run.output_summary) for r in report_results(root=src))
    got = sorted((r.run.result_kind, r.run.output_summary) for r in report_results(root=dest) if not r.stale)
    assert got == sent  # nothing less than the sender's report

    md = render(ProjectPaths(dest), ai=False)
    assert "Computed by the sender" in md and spec.carried_results[0].datasets[0]["name"] in md
    assert "Computed by the sender" not in render(ProjectPaths(src), ai=False)

    # Ids point at this project's factors, so labels resolve in the report and claims.
    dest_nodes = {r.run.id: get_result(r.run.id, root=dest)[1] for r in report_results(root=dest)}
    assert all("{{node:" not in str(p) for p in dest_nodes.values())

    # Re-sharing the opened model carries the same result again.
    _, again = export_spec(root=dest)
    assert [c.kind for c in again.carried_results] == [c.kind for c in spec.carried_results]


def test_a_link_selects_every_model_type(tmp_path, git_identity):
    src = build_example("bow_tie", tmp_path / "src")
    payload = decode_payload(make_link(root=src).url.split("#", 1)[1])
    assert payload.model_types == ["bow_tie", "event_tree"]
    single = decode_payload(make_link(root=build_example("mcda", tmp_path / "m")).url.split("#", 1)[1])
    assert single.model_types == []  # single-type links unchanged


def test_links_made_before_model_types_still_open():
    from latris.operations.share_link import LinkPayload

    old = LinkPayload.model_validate({"name": "n", "question": "q", "model_type": "cld", "spec": {}})
    assert old.model_types == []
