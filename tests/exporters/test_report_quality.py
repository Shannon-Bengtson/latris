"""Report fixes from a real agent run (Claude.ai building a CLD with the CLI).

The client pack is what a shared report link shows, so it must read well to
someone outside the modelling work: no internal IDs, the reason behind each
link, sources by name, and a short history rather than the whole log.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from latris.cli.app import app
from latris.exporters import markdown as md_exporter
from latris.exporters import narrative
from latris.operations import edges as edge_ops
from latris.operations import evidence as evidence_ops
from latris.operations import nodes as node_ops
from latris.operations import references as ref_ops
from latris.operations import view_attributes as view_attr_ops
from latris.operations.init import init_project
from latris.repo.layout import ProjectPaths


@pytest.fixture
def project(tmp_path: Path, git_identity) -> Path:
    root = tmp_path / "vol"
    init_project(root, statement="Why do volunteers leave?")
    a, _ = node_ops.add_node("Workload", kind="variable", root=root)
    b, _ = node_ops.add_node("Burnout", kind="state", root=root)
    e, _ = edge_ops.add_edge(a.id, b.id, kind="causal", root=root)
    view_attr_ops.set_view_attribute(e.id, "cld", "polarity", "+", rationale="More hours, more exhaustion.", root=root)
    ref_ops.add_reference("smith2021", "Volunteer burnout", authors=["Smith, J", "Lee, K"], year=2021, root=root)
    evidence_ops.add_evidence(e.id, "polarity", "smith2021", root=root)
    return root


def test_client_pack_reads_without_internal_ids(project: Path) -> None:
    out = md_exporter.render(ProjectPaths(project), pack="client", ai=False)
    assert "`node_" not in out and "`edge_" not in out
    assert "| Kind | Label | Description |" in out
    # The reason behind a link is shown.
    assert "More hours, more exhaustion." in out
    # Evidence names the link and the source, and the sources are listed.
    assert "Workload → Burnout" in out
    assert "### `smith2021` — Smith & Lee (2021), *Volunteer burnout*" in out
    assert "## References" in out


def test_full_report_keeps_ids_for_agents(project: Path) -> None:
    out = md_exporter.render(ProjectPaths(project), ai=False)
    assert "| `node_" in out and "| `edge_" in out


def test_history_is_summarised_not_dumped(project: Path) -> None:
    for i in range(12):
        node_ops.add_node(f"Factor {i}", root=project)
    out = md_exporter.render(ProjectPaths(project), pack="client", ai=False)
    history = out.split("## Model History", 1)[1].split("\n## ", 1)[0]
    assert "recorded changes" in history
    assert history.count("\n- **") == narrative._HISTORY_SHOWN


def test_rationale_updates_when_polarity_is_set_again(project: Path) -> None:
    edge = edge_ops.list_edges(root=project)[0]
    view_attr_ops.set_view_attribute(edge.id, "cld", "polarity", "+", rationale="Reworded reason.", root=project)
    out = md_exporter.render(ProjectPaths(project), pack="client", ai=False)
    assert "Reworded reason." in out
    assert "More hours, more exhaustion." not in out


def test_report_skips_ai_quietly_without_a_key(project: Path, monkeypatch) -> None:
    monkeypatch.delenv("LATRIS_AI_MOCK", raising=False)
    monkeypatch.delenv("GRAPH_TOOLING_AI_MOCK", raising=False)
    monkeypatch.setattr("latris.ai.credentials.get_key", lambda provider: None)

    def boom(*_a, **_k):
        raise AssertionError("an AI call was attempted without a key")

    monkeypatch.setattr("latris.ai.adapters.get_adapter", boom)
    out = md_exporter.render(ProjectPaths(project), pack="client")
    assert "## Model Structure" in out


def test_finding_add(project: Path, monkeypatch) -> None:
    monkeypatch.chdir(project)
    result = CliRunner().invoke(
        app,
        ["--json", "finding", "add", "Workload drives burnout in a reinforcing loop.",
         "--category", "structure", "--target", "Workload", "--detail", "From `latris analyse loops`."],
    )
    assert result.exit_code == 0, result.output
    finding = json.loads(result.stdout.strip().splitlines()[-1])["result"]
    assert finding["category"] == "structure"
    out = md_exporter.render(ProjectPaths(project), pack="client", ai=False)
    assert "Workload drives burnout in a reinforcing loop." in out

    bad = CliRunner().invoke(app, ["finding", "add", "x", "--category", "vibes"])
    assert bad.exit_code == 2


def test_history_names_things_instead_of_ids(project: Path) -> None:
    out = md_exporter.render(ProjectPaths(project), pack="client", ai=False)
    history = out.split("## Model History", 1)[1].split("\n## ", 1)[0]
    assert "edge_" not in history and "node_" not in history
    assert "Workload → Burnout" in history
