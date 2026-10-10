"""CLI tests for the `sync` transport commands: remote, push, pull, fetch, status.

These exercise only the transport layer (git remote), which needs no control
plane or network — a local bare repository stands in for the remote.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from latris.cli.app import app
from latris.repo import git

runner = CliRunner()


@pytest.fixture
def bare_remote(tmp_path: Path) -> str:
    """A local bare repo usable as a git remote URL."""
    bare = tmp_path / "remote.git"
    git.run_git(["init", "--bare", str(bare)], cwd=tmp_path)
    return bare.as_posix()


# -- remote --------------------------------------------------------------------


def test_remote_show_none(two_node_project_root: Path, monkeypatch):
    monkeypatch.chdir(two_node_project_root)
    r = runner.invoke(app, ["sync", "remote"])
    assert r.exit_code == 0, r.output
    assert "no 'origin' remote" in r.output


def test_remote_set_then_show(two_node_project_root: Path, bare_remote, monkeypatch):
    monkeypatch.chdir(two_node_project_root)
    r = runner.invoke(app, ["sync", "remote", bare_remote])
    assert r.exit_code == 0, r.output
    assert "remote" in r.output
    # Rich may wrap the long path across lines; flatten before matching.
    assert bare_remote in r.output.replace("\n", "")

    r2 = runner.invoke(app, ["sync", "remote"])
    assert r2.exit_code == 0, r2.output
    assert bare_remote in r2.output.replace("\n", "")


def test_remote_outside_project_errors(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["sync", "remote"])
    assert r.exit_code == 1
    assert "error:" in r.output


# -- status --------------------------------------------------------------------


def test_status_no_remote(two_node_project_root: Path, monkeypatch):
    monkeypatch.chdir(two_node_project_root)
    r = runner.invoke(app, ["sync", "status"])
    assert r.exit_code == 0, r.output
    assert "no 'origin' remote configured" in r.output
    assert "branch:" in r.output


def test_status_with_remote_no_upstream(two_node_project_root: Path, bare_remote, monkeypatch):
    monkeypatch.chdir(two_node_project_root)
    runner.invoke(app, ["sync", "remote", bare_remote])
    r = runner.invoke(app, ["sync", "status"])
    assert r.exit_code == 0, r.output
    assert "remote origin:" in r.output
    assert "no upstream tracking yet" in r.output


def test_status_ahead_behind_after_push(two_node_project_root: Path, bare_remote, monkeypatch):
    monkeypatch.chdir(two_node_project_root)
    runner.invoke(app, ["sync", "remote", bare_remote])
    runner.invoke(app, ["sync", "push"])
    r = runner.invoke(app, ["sync", "status"])
    assert r.exit_code == 0, r.output
    assert "ahead" in r.output
    assert "behind" in r.output


def test_status_reports_uncommitted(two_node_project_root: Path, bare_remote, monkeypatch):
    monkeypatch.chdir(two_node_project_root)
    runner.invoke(app, ["sync", "remote", bare_remote])
    # Leave a genuine uncommitted change in the working tree.
    from latris.operations import nodes as node_ops

    node_ops.add_node("Supply", kind="variable", root=two_node_project_root)
    git.run_git(["reset", "--mixed", "HEAD~1"], cwd=two_node_project_root)

    r = runner.invoke(app, ["sync", "status"])
    assert r.exit_code == 0, r.output
    assert "uncommitted changes in the working tree" in r.output


# -- push / pull / fetch -------------------------------------------------------


def test_push_happy(two_node_project_root: Path, bare_remote, monkeypatch):
    monkeypatch.chdir(two_node_project_root)
    runner.invoke(app, ["sync", "remote", bare_remote])
    r = runner.invoke(app, ["sync", "push"])
    assert r.exit_code == 0, r.output
    assert "pushed" in r.output


def test_push_no_remote_errors(two_node_project_root: Path, monkeypatch):
    monkeypatch.chdir(two_node_project_root)
    r = runner.invoke(app, ["sync", "push"])
    assert r.exit_code == 1
    assert "sync error:" in r.output
    assert "no 'origin' remote" in r.output


def test_fetch_happy(two_node_project_root: Path, bare_remote, monkeypatch):
    monkeypatch.chdir(two_node_project_root)
    runner.invoke(app, ["sync", "remote", bare_remote])
    runner.invoke(app, ["sync", "push"])
    r = runner.invoke(app, ["sync", "fetch"])
    assert r.exit_code == 0, r.output
    assert "fetched" in r.output


def test_fetch_no_remote_errors(two_node_project_root: Path, monkeypatch):
    monkeypatch.chdir(two_node_project_root)
    r = runner.invoke(app, ["sync", "fetch"])
    assert r.exit_code == 1
    assert "sync error:" in r.output


def test_pull_happy(two_node_project_root: Path, bare_remote, monkeypatch):
    monkeypatch.chdir(two_node_project_root)
    runner.invoke(app, ["sync", "remote", bare_remote])
    runner.invoke(app, ["sync", "push"])
    r = runner.invoke(app, ["sync", "pull"])
    assert r.exit_code == 0, r.output
    assert "pulled" in r.output


def test_pull_no_remote_errors(two_node_project_root: Path, monkeypatch):
    monkeypatch.chdir(two_node_project_root)
    r = runner.invoke(app, ["sync", "pull"])
    assert r.exit_code == 1
    assert "sync error:" in r.output
