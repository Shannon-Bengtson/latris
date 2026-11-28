"""``latris replicate``: list, check and build, outside a project."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from latris.cli.app import app
from latris.operations import replications as ops

runner = CliRunner()


def test_list() -> None:
    result = runner.invoke(app, ["replicate", "list"])
    assert result.exit_code == 0, result.output
    assert "asia" in result.output and "pearl-backdoor" in result.output


def test_list_json() -> None:
    result = runner.invoke(app, ["--json", "replicate", "list"])
    assert result.exit_code == 0, result.output
    ids = [r["id"] for r in json.loads(result.output)["result"]]
    assert ids == sorted(ids) and "sir-epidemic" in ids


def test_check_one(git_identity: tuple[str, str]) -> None:
    result = runner.invoke(app, ["replicate", "check", "system-archetypes"])
    assert result.exit_code == 0, result.output
    assert "PASS" in result.output and "1 of 1" in result.output


def test_check_json_and_keep(tmp_path: Path, git_identity: tuple[str, str]) -> None:
    result = runner.invoke(app, ["--json", "replicate", "check", "pearl-backdoor", "--keep", str(tmp_path)])
    assert result.exit_code == 0, result.output
    [report] = json.loads(result.output)["result"]
    assert report["passed"] and report["root"] == str(tmp_path / "pearl-backdoor")
    assert {o["basis"] for o in report["outcomes"]} == {"published", "exact"}


def test_check_fails_with_exit_1(monkeypatch: pytest.MonkeyPatch, git_identity: tuple[str, str]) -> None:
    rep = ops.get_replication("system-archetypes")
    wrong = rep.model_copy(update={"checks": [rep.checks[0].model_copy(update={"expected": 5.0})]})
    monkeypatch.setattr(ops, "get_replication", lambda _id: wrong)
    result = runner.invoke(app, ["replicate", "check", "system-archetypes"])
    assert result.exit_code == 1
    assert "FAIL" in result.output and "differs" in result.output


def test_check_unknown() -> None:
    result = runner.invoke(app, ["replicate", "check", "nope"])
    assert result.exit_code != 0
    assert "no replication 'nope'" in result.output


def test_build(tmp_path: Path, git_identity: tuple[str, str]) -> None:
    result = runner.invoke(app, ["replicate", "build", "asia", str(tmp_path / "asia")])
    assert result.exit_code == 0, result.output
    assert "built" in result.output and (tmp_path / "asia" / "project.yaml").is_file()
    as_json = runner.invoke(app, ["--json", "replicate", "build", "system-archetypes", str(tmp_path / "arch")])
    assert json.loads(as_json.output)["result"] == {"id": "system-archetypes", "root": str(tmp_path / "arch")}
