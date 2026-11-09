"""The report's Methods and foundations section, generated from the foundations registry.

Cites only the methods the report actually relies on: core entries for model
types the project genuinely uses (selected in project.yaml, mapped, or holding
view-attribute content — and the scoped type outright on a scoped export),
analysis entries only when the Results section shows that kind of result, and
nothing at all for a project with no formalism use.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.exporters import markdown
from latris.operations import mappings as mapping_ops
from latris.operations import sd as sd_ops
from latris.operations.edges import add_edge
from latris.operations.init import init_project
from latris.operations.nodes import add_node
from latris.operations.project import update_selected_models
from latris.operations.view_attributes import set_view_attribute
from latris.repo.project import require_project

pytest.importorskip("scipy")

SETTINGS = {"final_time": 10, "dt": 0.25, "saveper": 1, "method": "euler"}


def _bare_root(tmp_path: Path, git_identity) -> Path:
    """Substrate only: no selection, no mappings, no view attributes."""
    root = tmp_path / "proj"
    init_project(root, statement="Does X cause Y?")
    a, _ = add_node("A", kind="variable", root=root)
    b, _ = add_node("B", kind="variable", root=root)
    add_edge(a.id, b.id, kind="causal", root=root)
    return root


def _cld_only_root(tmp_path: Path, git_identity) -> Path:
    """A project whose substrate is mapped to the CLD view only."""
    root = tmp_path / "proj"
    init_project(root, statement="Does X cause Y?")
    a, _ = add_node("A", kind="variable", root=root)
    b, _ = add_node("B", kind="variable", root=root)
    e, _ = add_edge(a.id, b.id, kind="causal", root=root)
    for element in (a, b, e):
        mapping_ops.map_to_view(element.id, "cld", root=root)
    return root


def test_cld_only_report_cites_sterman_not_schoenberg(tmp_path, git_identity):
    root = _cld_only_root(tmp_path, git_identity)
    md = markdown.render(require_project(root), ai=False)
    assert "## Methods and foundations" in md
    assert "Sterman (2000)" in md
    # No SD content and no SD analyses: SD methods stay uncited.
    assert "Schoenberg" not in md
    assert "Forrester" not in md
    assert "McKay" not in md

    scoped = markdown.render(require_project(root), model_type="cld", ai=False)
    assert "## Methods and foundations" in scoped and "Sterman (2000)" in scoped


def test_select_models_alone_triggers_cld_entry(tmp_path, git_identity):
    """The README quickstart flow: select-models, then node/edge/view set — no
    mapping registry entries at any point. The CLD citation must still fire."""
    root = tmp_path / "proj"
    init_project(root, statement="Does X cause Y?")
    update_selected_models(["cld"], root=root)
    a, _ = add_node("A", kind="variable", root=root)
    b, _ = add_node("B", kind="variable", root=root)
    e, _ = add_edge(a.id, b.id, kind="causal", root=root)
    set_view_attribute(e.id, "cld", "polarity", "+", root=root)

    md = markdown.render(require_project(root), ai=False)
    assert "## Methods and foundations" in md
    assert "Sterman (2000)" in md


def test_view_attributes_alone_trigger_core_entry(tmp_path, git_identity):
    """No selection and no mappings, but `latris view set cld <edge> polarity +`
    has stored view-attribute content — that alone is CLD use."""
    root = _bare_root(tmp_path, git_identity)
    md = markdown.render(require_project(root), ai=False)
    assert "## Methods and foundations" not in md

    from latris.operations.edges import list_edges

    edge = list_edges(root)[0]
    set_view_attribute(edge.id, "cld", "polarity", "+", root=root)
    md = markdown.render(require_project(root), ai=False)
    assert "## Methods and foundations" in md
    assert "Sterman (2000)" in md


def test_scoped_export_includes_cld_without_selection_or_mappings(tmp_path, git_identity):
    root = _bare_root(tmp_path, git_identity)
    md = markdown.render(require_project(root), model_type="cld", ai=False)
    assert "## Methods and foundations" in md
    assert "Sterman (2000)" in md


def test_aggregate_without_formalism_use_has_no_core_entries(tmp_path, git_identity):
    """Substrate alone is not formalism use: no core entries, and no section at
    all until a reference makes the evidence entry fire."""
    root = _bare_root(tmp_path, git_identity)
    md = markdown.render(require_project(root), ai=False)
    assert "## Methods and foundations" not in md

    from latris.operations import references as ref_ops

    ref_ops.add_reference("ster2000", "Business Dynamics",
                          authors=["Sterman, John"], year=2000, root=root)
    md = markdown.render(require_project(root), ai=False)
    assert "## Methods and foundations" in md
    assert "Bradford Hill" in md
    assert "Sterman (2000), *Business Dynamics*" not in md  # core entry still excluded


def test_sd_loop_dominance_adds_schoenberg_and_keeps_base_entry_once(sd_bathtub_root):
    root = sd_bathtub_root
    for label in ("Water", "Inflow", "Outflow"):
        from latris.operations.nodes import list_nodes

        node = next(n for n in list_nodes(root) if n.label == label)
        mapping_ops.map_to_view(node.id, "sd", root=root)

    md = markdown.render(require_project(root), ai=False)
    assert "## Methods and foundations" in md
    assert "Forrester (1961)" in md
    assert "Schoenberg" not in md

    sd_ops.record_loops(sd_ops.run_loops(settings=SETTINGS, root=root), root=root)
    md = markdown.render(require_project(root), ai=False)
    assert "Schoenberg, Davidsen & Eberlein (2020)" in md
    # The base simulation entry still appears exactly once alongside the analysis entry.
    assert md.count("**Stock-and-flow simulation with dimensional analysis**") == 1


def test_methods_section_hidden_when_results_are_hidden(sd_bathtub_root):
    """The section never cites an analysis the Results section doesn't show."""
    from latris.operations import analysis_results as ar

    root = sd_bathtub_root
    _, run_id = sd_ops.record_loops(sd_ops.run_loops(settings=SETTINGS, root=root), root=root)
    md = markdown.render(require_project(root), ai=False)
    assert "Schoenberg" in md

    ar.set_hidden(run_id, True, root=root)
    md = markdown.render(require_project(root), ai=False)
    assert "Schoenberg" not in md


def test_empty_project_renders_no_methods_section(empty_project_root):
    md = markdown.render(require_project(empty_project_root), ai=False)
    assert "## Methods and foundations" not in md
