"""`latris version`: the version tree, its edits, and the sync commands' errors without a remote."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from latris.cli.app import app
from latris.operations.init import init_project
from latris.operations.nodes import add_node
from latris.repo import git

runner = CliRunner()


@pytest.fixture
def project(tmp_path: Path, git_identity, monkeypatch) -> Path:
    root = tmp_path / "proj"
    init_project(root, statement="What drives demand?")
    monkeypatch.chdir(root)
    return root


def _ok(*args: str) -> str:
    result = runner.invoke(app, ["version", *args])
    assert result.exit_code == 0, result.output
    return result.output


def test_tree_milestones_and_alternatives(project: Path) -> None:
    out = _ok("milestone", "Baseline", "--maturity", "reviewed", "--notes", "first cut")
    assert "'Baseline' (reviewed)" in out
    out = _ok("alternative", "What-if", "--from", "Baseline", "--notes", "try it")
    assert "created alternative" in out and "lineage/" in out
    add_node("Weather", root=project)
    _ok("milestone", "With weather")

    # The tree shows the current version's milestones.
    tree = _ok("tree")
    assert "├─ What-if (alternative, proposed) ← current" in tree
    assert "◆ With weather (proposed)" in tree

    assert "switched to 'What drives demand?'" in _ok("switch", "main")
    assert "◆ Baseline (reviewed)" in _ok("tree")
    out = _ok("compare", "Baseline", "What-if")
    assert "Added (1)" in out
    assert "Weather" in out


def test_compare_as_json_and_no_changes(project: Path) -> None:
    _ok("milestone", "A")
    _ok("milestone", "B")
    assert _ok("compare", "A", "B").strip() == "No changes."
    result = runner.invoke(app, ["--json", "version", "compare", "A", "B"])
    assert result.exit_code == 0
    assert json.loads(result.output)["result"] == []


def test_restore_preferred_update(project: Path) -> None:
    _ok("milestone", "Baseline")
    out = _ok("restore", "Baseline", "Restart", "--notes", "again")
    assert "restored" in out and "'Restart'" in out
    _ok("switch", "main")
    assert "preferred → " in _ok("preferred", "main")

    out = _ok("update", "--name", "Main line", "--maturity", "approved", "--notes", "done")
    assert "updated version 'Main line' (approved)" in out
    assert "no changes" in _ok("update", "--name", "Main line")


def test_unknown_versions_and_milestones(project: Path) -> None:
    for args in (
        ["switch", "nowhere"],
        ["preferred", "nowhere"],
        ["restore", "nowhere", "x"],
        ["alternative", "x", "--from", "nowhere"],
        ["compare", "nowhere", "main"],
    ):
        result = runner.invoke(app, ["version", *args])
        assert result.exit_code != 0, args
        assert result.output.strip(), args


def test_bad_maturity(project: Path) -> None:
    result = runner.invoke(app, ["version", "milestone", "X", "--maturity", "golden"])
    assert result.exit_code == 2
    assert "error" in result.output


def test_sync_status_when_not_shared(project: Path) -> None:
    out = _ok("sync-status")
    assert "project not shared" in out
    assert "local only" in out


@pytest.mark.parametrize(
    "args",
    [["publish", "main"], ["get-latest", "main"], ["add", "lineage/x"], ["reconcile", "main", "--keep", "mine"]],
)
def test_sync_commands_need_a_remote(project: Path, args: list[str]) -> None:
    result = runner.invoke(app, ["version", *args])
    assert result.exit_code != 0
    assert "error" in result.output


def test_reconcile_preview_without_divergence(project: Path) -> None:
    result = runner.invoke(app, ["version", "reconcile-preview", "main"])
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert result.output.strip()


def test_publish_and_status_with_a_remote(project: Path, tmp_path: Path) -> None:
    bare = tmp_path / "remote.git"
    git.init_bare(bare)
    assert runner.invoke(app, ["sync", "remote", str(bare)]).exit_code == 0
    git.set_config(project, "latris.projectid", "demo")
    _ok("alternative", "What-if")
    _ok("switch", "main")

    assert "published 'main'" in _ok("publish", "main")
    out = _ok("sync-status")
    assert "project not shared" not in out
    assert "in sync" in out
    assert "local only" in out  # the unpublished alternative
    assert "up to date on 'main'" in _ok("get-latest", "main")
    assert "no differences" in _ok("reconcile-preview", "main")
