from __future__ import annotations

from pathlib import Path

import pytest

from latris.exporters import markdown as md_exporter
from latris.exporters import mermaid
from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations import view_attributes as view_attr_ops
from latris.operations.init import init_project
from latris.repo.layout import ProjectPaths


@pytest.fixture
def project_with_graph(tmp_path: Path, git_identity):
    root = tmp_path / "demo"
    init_project(root, statement="Q?")
    a, _ = node_ops.add_node("Price", kind="variable", root=root)
    b, _ = node_ops.add_node("Demand", kind="variable", root=root)
    c, _ = node_ops.add_node('Policy "cap" <draft>', kind="decision", root=root)
    causal, _ = edge_ops.add_edge(a.id, b.id, kind="causal", root=root)
    view_attr_ops.set_view_attribute(causal.id, "cld", "polarity", "-", root=root)
    edge_ops.add_edge(c.id, a.id, kind="association", root=root)
    return root


def test_mermaid_renders_flowchart_with_polarity(project_with_graph) -> None:
    out = mermaid.render(ProjectPaths(project_with_graph))
    lines = out.splitlines()
    assert lines[0] == "flowchart LR"
    assert '    n0["Price"]' in lines
    assert '    n1["Demand"]' in lines
    assert '    n0 -->|"-"| n1' in lines
    # Non-mechanism edges draw dotted and are labelled with their kind.
    assert '    n2 -.->|"association"| n0' in lines


def test_mermaid_escapes_label_syntax(project_with_graph) -> None:
    out = mermaid.render(ProjectPaths(project_with_graph))
    assert '    n2["Policy #quot;cap#quot; #lt;draft#gt;"]' in out.splitlines()
    assert "<draft>" not in out


def test_mermaid_empty_model_returns_empty_string(tmp_path: Path, git_identity) -> None:
    root = tmp_path / "empty"
    init_project(root, statement="Q?")
    assert mermaid.render(ProjectPaths(root)) == ""


def test_markdown_report_embeds_mermaid_block(project_with_graph) -> None:
    paths = ProjectPaths(project_with_graph)
    client_md = md_exporter.render(paths, pack="client")
    assert "## Diagram" in client_md
    assert "```mermaid\nflowchart LR\n" in client_md
    # Sections can still exclude it.
    nodes_only = md_exporter.render(paths, sections=["nodes"])
    assert "```mermaid" not in nodes_only


def test_markdown_report_omits_diagram_for_empty_model(tmp_path: Path, git_identity) -> None:
    root = tmp_path / "empty"
    init_project(root, statement="Q?")
    assert "## Diagram" not in md_exporter.render(ProjectPaths(root), pack="client")


def test_markdown_footer_links_hosted_report(project_with_graph) -> None:
    paths = ProjectPaths(project_with_graph)
    out = md_exporter.render(paths, pack="client", report_url="https://app.latris.app/r/abc")
    assert "View this report online: https://app.latris.app/r/abc" in out
    assert "View this report online" not in md_exporter.render(paths, pack="client")


def test_markdown_without_ai_never_calls_the_narrative_ai(project_with_graph, monkeypatch) -> None:
    from latris.exporters import narrative

    def boom(*_a, **_k):
        raise AssertionError("AI narrative attempted")

    monkeypatch.setattr(narrative, "_try_ai_narrative", boom)
    out = md_exporter.render(ProjectPaths(project_with_graph), pack="client", ai=False)
    assert "## Nodes" in out
