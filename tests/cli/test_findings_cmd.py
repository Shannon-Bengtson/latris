"""`latris finding`: filters, detail output, staleness and errors."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from latris.cli.app import app
from latris.operations import findings as find_ops
from latris.operations.init import init_project
from latris.operations.nodes import add_node, remove_node
from latris.schema import HumanActor
from latris.schema.findings import Finding
from latris.schema.ids import new_id

runner = CliRunner()


@pytest.fixture
def project(tmp_path: Path, git_identity, monkeypatch) -> Path:
    root = tmp_path / "proj"
    init_project(root, statement="What drives demand?")
    monkeypatch.chdir(root)
    return root


def test_add_refuses_an_unknown_category(project: Path) -> None:
    result = runner.invoke(app, ["finding", "add", "X", "--category", "vibes"])
    assert result.exit_code == 2
    assert "category must be one of" in result.output


def test_add_with_targets_and_detail(project: Path) -> None:
    node, _ = add_node("Price", root=project)
    result = runner.invoke(
        app, ["finding", "add", "Price drives demand.", "-c", "dynamics", "-m", "sd", "--detail", "why", "-t", "Price"]
    )
    assert result.exit_code == 0, result.output
    assert "recorded dynamics finding" in result.output
    (finding,) = find_ops.list_findings(root=project)
    assert finding.target_ids == [node.id]
    assert finding.model_type == "sd"


def test_add_with_an_unknown_target(project: Path) -> None:
    result = runner.invoke(app, ["finding", "add", "X", "-t", "Nothing"])
    assert result.exit_code == 1
    assert "resolve error" in result.output


def test_list_filters_and_limit(project: Path) -> None:
    assert runner.invoke(app, ["finding", "list"]).output.strip() == "(no findings match the filters)"
    find_ops.record_new_finding("A structure finding", "structure", "cld", root=project)
    find_ops.record_new_finding("B " + "long " * 20, "dynamics", "sd", root=project)

    result = runner.invoke(app, ["finding", "list"])
    assert "2 finding(s)." in result.output
    result = runner.invoke(app, ["finding", "list", "-c", "dynamics"])
    assert "1 finding(s)." in result.output
    assert "A structure finding" not in result.output
    result = runner.invoke(app, ["finding", "list", "-m", "cld", "--maturity", "proposed", "-n", "5"])
    assert "A structure finding" in result.output
    result = runner.invoke(app, ["finding", "list", "-t", "node_nothing"])
    assert "no findings match" in result.output
    result = runner.invoke(app, ["finding", "list", "-n", "1"])
    assert "1 finding(s)." in result.output


def test_list_as_json(project: Path) -> None:
    find_ops.record_new_finding("A", "structure", "cld", root=project)
    result = runner.invoke(app, ["--json", "finding", "list"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["result"][0]["statement"] == "A"


def test_show_every_field(project: Path) -> None:
    node, _ = add_node("Price", root=project)
    old, _ = find_ops.record_new_finding("Old", "structure", "cld", root=project)
    finding = Finding(
        id=new_id("finding"),
        category="structure",
        model_type="cld",
        statement="New",
        detail="the detail",
        payload={"loops": 2},
        supersedes=[old.id],
        target_ids=[node.id],
    )
    find_ops.record_finding(finding, root=project)
    find_ops.set_finding_maturity(
        finding.id, maturity="reviewed", reviewed_by=HumanActor(name="Rev", email="r@x"), root=project
    )

    result = runner.invoke(app, ["finding", "show", finding.id])
    assert result.exit_code == 0, result.output
    out = result.output
    assert "reviewed" in out
    assert "Reviewed:  Rev" in out
    assert f"Supersedes: {old.id}" in out
    assert "Detail:\nthe detail" in out
    assert f"Targets:  {node.id}" in out
    assert "Payload keys: loops" in out


def test_show_bare_finding(project: Path) -> None:
    finding, _ = find_ops.record_new_finding("Bare", "structure", "cld", root=project)
    out = runner.invoke(app, ["finding", "show", finding.id]).output
    assert "Statement: Bare" in out
    for absent in ("Reviewed:", "Supersedes:", "Detail:", "Targets:", "Payload keys:"):
        assert absent not in out


def test_show_unknown_and_ambiguous(project: Path) -> None:
    result = runner.invoke(app, ["finding", "show", "finding_nope"])
    assert result.exit_code == 2
    assert "no finding matches" in result.output
    find_ops.record_new_finding("A", "structure", "cld", root=project)
    find_ops.record_new_finding("B", "structure", "cld", root=project)
    result = runner.invoke(app, ["finding", "show", "finding_"])
    assert result.exit_code == 2
    assert "ambiguous" in result.output


def test_check_stale(project: Path) -> None:
    assert "no active findings" in runner.invoke(app, ["finding", "check-stale"]).output

    node, _ = add_node("Price", root=project)
    find_ops.record_new_finding("About price", "structure", "cld", target_ids=[node.id], root=project)
    result = runner.invoke(app, ["finding", "check-stale"])
    assert "All 1 active finding(s) are current." in result.output

    remove_node(node.id, root=project)
    result = runner.invoke(app, ["finding", "check-stale"])
    assert result.exit_code == 0
    assert "1 finding(s) may be stale" in result.output
    assert "About price" in result.output
