"""`latris elicit`: flags and error paths of the elicitation commands."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from latris.cli.app import app
from latris.operations import elicitation as elicit_ops
from latris.operations.init import init_project
from latris.operations.nodes import add_node

runner = CliRunner()


@pytest.fixture
def project(tmp_path: Path, git_identity, monkeypatch) -> Path:
    root = tmp_path / "proj"
    init_project(root, statement="What drives demand?")
    monkeypatch.chdir(root)
    return root


def _start(*extra: str):
    return runner.invoke(app, ["elicit", "start", "-p", "delphi", "-f", "Alice", *extra])


def _only_session(root: Path) -> str:
    (entry,) = elicit_ops.list_sessions(root=root)
    return entry.id


def test_list_empty(project: Path) -> None:
    result = runner.invoke(app, ["elicit", "list"])
    assert result.exit_code == 0
    assert "no elicitation sessions" in result.output


def test_start_rejects_a_target_without_attribute(project: Path) -> None:
    result = _start("--target", "node_only")
    assert result.exit_code == 2
    assert "expected 'target_id/attribute'" in result.output
    assert elicit_ops.list_sessions(root=project) == []


def test_start_rejects_a_bad_date(project: Path) -> None:
    result = _start("--date", "not-a-date")
    assert result.exit_code == 2
    assert "error" in result.output


def test_full_session(project: Path) -> None:
    node, _ = add_node("Price", root=project)
    result = _start("-e", "Dr A", "-e", "Dr B", "-t", f"{node.id}/confidence", "--date", "2026-01-02")
    assert result.exit_code == 0, result.output
    assert "(delphi)" in result.output
    sid = _only_session(project)

    result = runner.invoke(app, ["elicit", "round", sid, "-e", "Dr A", "-i", "high", "-r", "data", "-n", "2"])
    assert result.exit_code == 0, result.output
    assert "Added round 2 from Dr A" in result.output

    # Text that isn't JSON is stored as {"value": ...}.
    result = runner.invoke(app, ["elicit", "aggregate", sid, "-r", "high", "-c", "both agree"])
    assert result.exit_code == 0, result.output
    assert elicit_ops.get_session(sid, root=project).aggregated_result == {"value": "high"}

    result = runner.invoke(app, ["elicit", "show", sid])
    assert result.exit_code == 0
    assert "held_at: 2026-01-02" in result.output
    assert "experts: Dr A, Dr B" in result.output
    assert f"{node.id}/confidence" in result.output
    assert "responses: 1" in result.output
    assert "aggregated:" in result.output
    assert "confidence: both agree" in result.output

    assert runner.invoke(app, ["elicit", "finalise", sid]).exit_code == 0
    again = runner.invoke(app, ["elicit", "finalise", sid])
    assert again.exit_code == 2
    assert "already finalised" in again.output

    listed = runner.invoke(app, ["elicit", "list"])
    assert sid[:25] in listed.output


def test_show_without_aggregate(project: Path) -> None:
    assert _start().exit_code == 0
    result = runner.invoke(app, ["elicit", "show", _only_session(project)])
    assert result.exit_code == 0
    assert "phase:" in result.output
    assert "aggregated" not in result.output
    assert "confidence:" not in result.output


def test_aggregate_parses_json(project: Path) -> None:
    assert _start().exit_code == 0
    sid = _only_session(project)
    result = runner.invoke(app, ["elicit", "aggregate", sid, "-r", '{"p": 0.7}'])
    assert result.exit_code == 0
    assert elicit_ops.get_session(sid, root=project).aggregated_result == {"p": 0.7}


def test_a_prefix_finds_the_session(project: Path) -> None:
    assert _start().exit_code == 0
    sid = _only_session(project)
    result = runner.invoke(app, ["elicit", "show", sid[:16]])
    assert result.exit_code == 0
    assert sid in result.output


@pytest.mark.parametrize("command", ["show", "round", "aggregate", "finalise"])
def test_unknown_session_is_refused(project: Path, command: str) -> None:
    assert _start().exit_code == 0
    extra = {"round": ["-e", "x", "-i", "y"], "aggregate": ["-r", "z"]}.get(command, [])
    # Shares the type prefix with the real session but names none.
    result = runner.invoke(app, ["elicit", command, "elicitation_00000000000000000000000000", *extra])
    assert result.exit_code == 2
    assert "not found" in result.output
