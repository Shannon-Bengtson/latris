"""CLI smoke tests — error paths, --version, doctor, and outside-project guard."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from latris import __version__
from latris.cli.app import app
from latris.operations.init import init_project

runner = CliRunner()


def test_version_flag():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_no_args_shows_help():
    result = runner.invoke(app, [])
    # click 8.2+ / typer 0.26: a group invoked with no subcommand shows help
    # and exits 2 (was 0 on older click).
    assert result.exit_code == 2
    assert "Usage" in result.stdout


def test_node_add_outside_project(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["node", "add", "Price"])
    assert result.exit_code == 1
    assert "error" in result.stdout.lower()


def test_edge_add_outside_project(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["edge", "add", "a", "b"])
    assert result.exit_code == 1


def test_node_add_bad_reference(tmp_path: Path, git_identity, monkeypatch):
    root = tmp_path / "proj"
    init_project(root, statement="X")
    monkeypatch.chdir(root)
    result = runner.invoke(app, ["node", "rename", "nonexistent", "NewLabel"])
    assert result.exit_code == 1
    assert "resolve" in result.stdout.lower() or "error" in result.stdout.lower()


def test_doctor_with_identity(git_identity):
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "ok" in result.stdout.lower() or "ready" in result.stdout.lower()


def test_init_creates_project(tmp_path: Path, git_identity, monkeypatch):
    target = tmp_path / "new_proj"
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        [
            "init",
            str(target),
            "--question",
            "Why?",
        ],
    )
    assert result.exit_code == 0
    assert (target / ".graph-tooling" / "version").exists()


def test_node_add_in_project(tmp_path: Path, git_identity, monkeypatch):
    root = tmp_path / "proj"
    init_project(root, statement="X")
    monkeypatch.chdir(root)
    result = runner.invoke(app, ["node", "add", "Price", "--kind", "variable"])
    assert result.exit_code == 0
    assert "Price" in result.stdout


def test_attr_set_outside_project(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["attr", "set", "someId", "description", "text"])
    assert result.exit_code == 1


def test_status_outside_project(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 1
