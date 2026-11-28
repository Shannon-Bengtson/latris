"""`latris challenge`: open, turn, resolve, list, show — flags and error paths."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from latris.cli.app import app
from latris.operations import challenges as ch_ops
from latris.operations.init import init_project
from latris.operations.nodes import add_node

runner = CliRunner()


@pytest.fixture
def project(tmp_path: Path, git_identity, monkeypatch) -> Path:
    root = tmp_path / "proj"
    init_project(root, statement="What drives demand?")
    add_node("Price", root=root)
    monkeypatch.chdir(root)
    return root


def _open(*extra: str) -> str:
    result = runner.invoke(app, ["challenge", "open", "Price", "Price is set, not driven.", *extra])
    assert result.exit_code == 0, result.output
    return ch_ops.list_challenges()[-1].id


def test_list_empty(project: Path) -> None:
    result = runner.invoke(app, ["challenge", "list"])
    assert result.exit_code == 0
    assert "no challenges yet" in result.output


def test_open_unknown_target(project: Path) -> None:
    result = runner.invoke(app, ["challenge", "open", "Nothing", "x"])
    assert result.exit_code == 1
    assert "resolve error" in result.output


def test_lifecycle_and_show(project: Path) -> None:
    cid = _open("--attribute", "description")
    assert runner.invoke(app, ["challenge", "turn", cid, "First reply"]).exit_code == 0
    result = runner.invoke(app, ["challenge", "turn", cid, "Second reply"])
    assert "now 2 turn(s)" in result.output

    out = runner.invoke(app, ["challenge", "show", cid]).output
    assert "attribute: description" in out
    assert "resolved:" not in out
    assert "1. [" in out and "First reply" in out

    result = runner.invoke(app, ["challenge", "resolve", cid, "-s", "retained-unchanged", "-r", "evidence holds"])
    assert result.exit_code == 0, result.output
    assert "→ retained-unchanged" in result.output
    out = runner.invoke(app, ["challenge", "show", cid]).output
    assert "resolved:" in out
    assert "rationale: evidence holds" in out

    again = runner.invoke(app, ["challenge", "resolve", cid, "-s", "retained-unchanged"])
    assert again.exit_code == 2
    assert "already resolved" in again.output


def test_show_bare_challenge(project: Path) -> None:
    cid = _open()
    out = runner.invoke(app, ["challenge", "show", cid]).output
    assert "attribute:" not in out
    assert "conversation:" not in out


def test_resolve_without_rationale(project: Path) -> None:
    cid = _open()
    result = runner.invoke(app, ["challenge", "resolve", cid, "-s", "retained-unchanged"])
    assert result.exit_code == 0
    out = runner.invoke(app, ["challenge", "show", cid]).output
    assert "resolved:" in out
    assert "rationale:" not in out


@pytest.mark.parametrize(("state", "message"), [("open", "cannot resolve to 'open'"), ("maybe", "unknown state")])
def test_resolve_bad_state(project: Path, state: str, message: str) -> None:
    cid = _open()
    result = runner.invoke(app, ["challenge", "resolve", cid, "-s", state])
    assert result.exit_code == 2
    assert message in result.output


def test_resolve_by_an_agent_needs_the_person(project: Path, monkeypatch) -> None:
    cid = _open()
    monkeypatch.setenv("LATRIS_AGENT", "test-agent")
    result = runner.invoke(app, ["challenge", "resolve", cid, "-s", "retained-unchanged"])
    assert result.exit_code == 2
    assert "--confirmed-by-person" in result.output
    result = runner.invoke(app, ["challenge", "resolve", cid, "-s", "retained-unchanged", "--confirmed-by-person"])
    assert result.exit_code == 0, result.output


def test_unknown_challenge(project: Path) -> None:
    for args in (["show", "challenge_nope"], ["turn", "challenge_nope", "x"]):
        result = runner.invoke(app, ["challenge", *args])
        assert result.exit_code != 0
        assert result.output.strip()


def test_list_table_and_json(project: Path) -> None:
    _open()
    runner.invoke(app, ["challenge", "open", "Price", "A long argument " * 6])
    result = runner.invoke(app, ["challenge", "list"])
    assert result.exit_code == 0
    assert "open" in result.output
    assert "…" in result.output

    result = runner.invoke(app, ["--json", "challenge", "list"])
    assert result.exit_code == 0
    assert len(json.loads(result.output)["result"]) == 2
