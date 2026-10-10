"""CLI tests for the history commands: log, status, diff."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from latris.cli.app import app
from latris.operations import nodes as node_ops
from latris.repo import git

runner = CliRunner()


def test_log_shows_commits(two_node_project_root: Path, monkeypatch):
    monkeypatch.chdir(two_node_project_root)
    r = runner.invoke(app, ["log"])
    assert r.exit_code == 0, r.output
    # The initialise commit subject always shows.
    assert "Initialise latris project" in r.output


def test_log_respects_limit(two_node_project_root: Path, monkeypatch):
    monkeypatch.chdir(two_node_project_root)
    r = runner.invoke(app, ["log", "--limit", "1"])
    assert r.exit_code == 0, r.output
    # Only one commit line (each line starts with a 10-char short sha).
    lines = [ln for ln in r.output.splitlines() if ln.strip()]
    assert len(lines) == 1


def test_log_outside_project_errors(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["log"])
    assert r.exit_code == 1
    assert "error:" in r.output


def test_status_clean(two_node_project_root: Path, monkeypatch):
    monkeypatch.chdir(two_node_project_root)
    r = runner.invoke(app, ["status"])
    assert r.exit_code == 0, r.output
    assert "clean" in r.output


def test_status_dirty_shows_changes(two_node_project_root: Path, monkeypatch):
    monkeypatch.chdir(two_node_project_root)
    # Create a genuine *semantic* working-tree change: add a node (which commits)
    # then mixed-reset so the new node is left uncommitted against HEAD.
    node_ops.add_node("Supply", kind="variable", root=two_node_project_root)
    git.run_git(["reset", "--mixed", "HEAD~1"], cwd=two_node_project_root)

    r = runner.invoke(app, ["status"])
    assert r.exit_code == 0, r.output
    assert "uncommitted changes:" in r.output
    # The clean branch would not mention the new node.
    assert "Supply" in r.output


def test_status_outside_project_errors(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["status"])
    assert r.exit_code == 1
    assert "error:" in r.output


def test_diff_working_tree_clean(two_node_project_root: Path, monkeypatch):
    monkeypatch.chdir(two_node_project_root)
    r = runner.invoke(app, ["diff"])
    assert r.exit_code == 0, r.output
    assert "working tree vs HEAD" in r.output
    assert "no changes" in r.output


def test_diff_single_commit(two_node_project_root: Path, monkeypatch):
    monkeypatch.chdir(two_node_project_root)
    head = git.head_sha(two_node_project_root)
    r = runner.invoke(app, ["diff", head])
    assert r.exit_code == 0, r.output
    assert f"commit {head}" in r.output


def test_diff_range(two_node_project_root: Path, monkeypatch):
    monkeypatch.chdir(two_node_project_root)
    head = git.head_sha(two_node_project_root)
    # Advance HEAD with a new commit so the range has content.
    node_ops.add_node("Supply", kind="variable", root=two_node_project_root)
    new_head = git.head_sha(two_node_project_root)
    r = runner.invoke(app, ["diff", f"{head}..{new_head}"])
    assert r.exit_code == 0, r.output
    # Rich may wrap long lines; flatten newlines before matching the range.
    flat = r.output.replace("\n", "")
    assert f"{head}..{new_head}" in flat
    # The new node should surface as a semantic event.
    assert "Supply" in r.output
